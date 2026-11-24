import ipaddress
import logging
import threading
from collections.abc import Callable
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from ..config import Settings
from ..domain.errors import ConfigurationError, ReadinessFailed, StorageCleanupFailed
from ..logging_config import SafeFieldsFilter, log_job_event
from ..security import authenticate_token


class RequestBoundaryMiddleware:
    """Protege autenticación, admisión y errores antes de consumir multipart."""

    def __init__(
        self,
        app,
        *,
        settings: Settings,
        preflight: Callable[[], None],
        logger: logging.Logger,
    ):
        self.app = app
        self.settings = settings
        self.preflight = preflight
        self.logger = logger
        self._capacity = threading.BoundedSemaphore(settings.max_active_requests)

    @staticmethod
    def _error_response(request_id: str, error_code: str, status_code: int):
        return JSONResponse(
            status_code=status_code,
            content={
                "request_id": request_id,
                "error_code": error_code,
                "message": "No se pudo procesar la solicitud",
            },
        )

    async def _send_error(
        self, scope, receive, send, request_id: str, error_code: str, status_code: int
    ) -> None:
        response = self._error_response(request_id, error_code, status_code)
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = Headers(scope=scope)
        protected = scope.get("path", "").startswith("/v1/jobs")
        local_path = scope.get("path", "").startswith("/api/v1/local/jobs")
        is_creation = (protected or local_path) and scope.get("method") == "POST"
        acquired = False
        response_started = False

        async def guarded_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            if local_path:
                if not self.settings.local_mode_enabled:
                    await self._send_error(
                        scope, receive, send, request_id, "LOCAL_MODE_DISABLED", 404
                    )
                    return
                client = scope.get("client")
                client_host = client[0] if client else ""
                try:
                    is_loopback = ipaddress.ip_address(client_host).is_loopback
                except ValueError:
                    is_loopback = False
                if not is_loopback:
                    await self._send_error(
                        scope,
                        receive,
                        send,
                        request_id,
                        "LOCAL_ONLY",
                        403,
                    )
                    return
                if headers.get("X-Local-Pilot") != "1":
                    await self._send_error(
                        scope,
                        receive,
                        send,
                        request_id,
                        "LOCAL_HEADER_REQUIRED",
                        403,
                    )
                    return
            if protected:
                try:
                    principal = await run_in_threadpool(
                        authenticate_token,
                        headers.get("X-API-Key"),
                        self.settings,
                    )
                except ConfigurationError:
                    raise
                except Exception:
                    await self._send_error(
                        scope,
                        receive,
                        send,
                        request_id,
                        "AUTHENTICATION_FAILED",
                        401,
                    )
                    return
                scope["state"]["principal"] = principal

            if is_creation:
                content_length = headers.get("content-length")
                if content_length is None:
                    await self._send_error(
                        scope, receive, send, request_id, "CONTENT_LENGTH_REQUIRED", 411
                    )
                    return
                try:
                    request_bytes = int(content_length)
                except ValueError:
                    await self._send_error(
                        scope, receive, send, request_id, "CONTENT_LENGTH_INVALID", 400
                    )
                    return
                if request_bytes < 0:
                    await self._send_error(
                        scope, receive, send, request_id, "CONTENT_LENGTH_INVALID", 400
                    )
                    return
                request_limit = (
                    self.settings.max_upload_bytes
                    if local_path
                    else self.settings.max_request_bytes
                )
                if request_bytes > request_limit:
                    await self._send_error(
                        scope,
                        receive,
                        send,
                        request_id,
                        "PAYLOAD_TOO_LARGE" if local_path else "REQUEST_TOO_LARGE",
                        413,
                    )
                    return
                acquired = self._capacity.acquire(blocking=False)
                if not acquired:
                    await self._send_error(
                        scope, receive, send, request_id, "PROCESSING_CAPACITY_BUSY", 503
                    )
                    return
                await run_in_threadpool(self.preflight)

            await self.app(scope, receive, guarded_send)
        except Exception as exc:
            if isinstance(exc, (ConfigurationError, ReadinessFailed)):
                error_code = str(exc)
                status_code = 503
            elif isinstance(exc, StorageCleanupFailed):
                error_code = str(exc)
                status_code = 500
            elif isinstance(exc, SQLAlchemyError):
                error_code = "PERSISTENCE_ERROR"
                status_code = 500
            elif isinstance(exc, OSError):
                error_code = "STORAGE_ERROR"
                status_code = 500
            else:
                error_code = "INTERNAL_ERROR"
                status_code = 500
            if SafeFieldsFilter.SAFE_CODE.fullmatch(error_code) is None:
                error_code = "INTERNAL_ERROR"
            log_job_event(
                self.logger,
                request_id=request_id,
                status="REQUEST_FAILED",
                error_code=error_code,
            )
            if not response_started:
                await self._send_error(
                    scope, receive, send, request_id, error_code, status_code
                )
        finally:
            if acquired:
                self._capacity.release()
