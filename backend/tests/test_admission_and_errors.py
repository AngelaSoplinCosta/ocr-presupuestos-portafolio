import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.middleware import RequestBoundaryMiddleware
from backend.app.domain.errors import ConfigurationError
from backend.app.domain.models import EngineOutcome
from backend.app.logging_config import SafeFieldsFilter


LOGGER_NAMES = (
    "ocr_orchestration",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "starlette",
    "fastapi",
    "sqlalchemy",
    "sqlalchemy.engine",
)


class BlockingAdapter:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def process(self, *, result_path, **_kwargs):
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("TEST_TIMEOUT")
        result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
        return EngineOutcome(requires_review=False)


def _capture_all_safe_loggers():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SafeFieldsFilter())
    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
    return stream


def test_invalid_token_is_rejected_before_storage(
    client, app, auth_headers, synthetic_pdf, monkeypatch
):
    store = Mock(side_effect=AssertionError("storage must not be reached"))
    monkeypatch.setattr(app.state.job_service.storage, "store_upload", store)
    response = client.post(
        "/v1/jobs",
        headers={**auth_headers, "X-API-Key": "incorrecto"},
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTHENTICATION_FAILED"
    store.assert_not_called()


def test_request_content_length_is_rejected_before_storage(
    client, app, auth_headers, synthetic_pdf, monkeypatch
):
    store = Mock(side_effect=AssertionError("storage must not be reached"))
    monkeypatch.setattr(app.state.job_service.storage, "store_upload", store)
    response = client.post(
        "/v1/jobs",
        headers={**auth_headers, "Content-Length": "999999999"},
        content=synthetic_pdf,
    )
    assert response.status_code == 413
    assert response.json()["error_code"] == "REQUEST_TOO_LARGE"
    store.assert_not_called()


@pytest.mark.asyncio
async def test_missing_content_length_is_rejected(settings, api_token):
    reached = False

    async def downstream(_scope, _receive, _send):
        nonlocal reached
        reached = True

    middleware = RequestBoundaryMiddleware(
        downstream,
        settings=settings,
        preflight=lambda: None,
        logger=logging.getLogger("ocr_orchestration"),
    )
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/jobs",
            "headers": [(b"x-api-key", api_token.encode())],
        },
        receive,
        send,
    )
    assert reached is False
    assert sent[0]["status"] == 411
    assert b"CONTENT_LENGTH_REQUIRED" in sent[1]["body"]


def test_second_active_creation_is_rejected(client, app, auth_headers, synthetic_pdf):
    adapter = BlockingAdapter()
    app.state.job_service.processor.adapter = adapter

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            client.post,
            "/v1/jobs",
            headers={**auth_headers, "X-Drive-File-Id": "first"},
            files={"file": ("first.pdf", synthetic_pdf, "application/pdf")},
        )
        assert adapter.started.wait(timeout=5)
        second = client.post(
            "/v1/jobs",
            headers={**auth_headers, "X-Drive-File-Id": "second"},
            files={"file": ("second.pdf", synthetic_pdf, "application/pdf")},
        )
        adapter.release.set()
        first_response = first.result(timeout=5)

    assert first_response.status_code == 200
    assert second.status_code == 503
    assert second.json()["error_code"] == "PROCESSING_CAPACITY_BUSY"


@pytest.mark.parametrize(
    ("target", "failure", "expected_code"),
    [
        ("storage", OSError("CLIENTE_PRIVADO /ruta/privada"), "STORAGE_ERROR"),
        (
            "repository",
            SQLAlchemyError("SQL parametros nombre_cliente.pdf"),
            "PERSISTENCE_ERROR",
        ),
    ],
)
def test_unexpected_infrastructure_errors_are_sanitized_in_all_loggers(
    client,
    app,
    auth_headers,
    synthetic_pdf,
    monkeypatch,
    target,
    failure,
    expected_code,
):
    stream = _capture_all_safe_loggers()
    if target == "storage":
        monkeypatch.setattr(
            app.state.job_service.storage, "store_upload", Mock(side_effect=failure)
        )
    else:
        monkeypatch.setattr(
            app.state.job_service.repository,
            "create_or_get",
            Mock(side_effect=failure),
        )
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("nombre_cliente.pdf", synthetic_pdf, "application/pdf")},
    )
    payload = response.json()
    assert response.status_code == 500
    assert payload["error_code"] == expected_code
    assert set(payload) == {"request_id", "error_code", "message"}
    output = stream.getvalue()
    assert expected_code in output
    assert "CLIENTE_PRIVADO" not in output
    assert "ruta/privada" not in output
    assert "nombre_cliente.pdf" not in output
    assert "parametros" not in output
    assert list(app.state.job_service.storage.root.iterdir()) == []


def test_migration_failure_is_rejected_before_storage(
    client, app, auth_headers, synthetic_pdf, monkeypatch
):
    store = Mock(side_effect=AssertionError("storage must not be reached"))
    monkeypatch.setattr(app.state.job_service.storage, "store_upload", store)
    monkeypatch.setattr(app.state.job_service.repository, "schema_is_current", lambda: False)
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "DATABASE_SCHEMA_NOT_READY"
    store.assert_not_called()


def test_hmac_failure_compensates_provisional_upload(
    client, app, auth_headers, synthetic_pdf, monkeypatch
):
    monkeypatch.setattr(
        "backend.app.services.job_service.protect_drive_file_id",
        Mock(side_effect=ConfigurationError("ID_HMAC_SECRET_INVALID")),
    )
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "ID_HMAC_SECRET_INVALID"
    assert list(app.state.job_service.storage.root.iterdir()) == []


def test_cleanup_failure_is_reported_with_its_own_safe_code(
    client, app, auth_headers, synthetic_pdf, monkeypatch
):
    monkeypatch.setattr(
        app.state.job_service.storage,
        "store_upload",
        Mock(side_effect=OSError("fallo privado de almacenamiento")),
    )
    monkeypatch.setattr(
        app.state.job_service.storage,
        "remove_job",
        Mock(side_effect=OSError("fallo privado de limpieza")),
    )
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "UPLOAD_CLEANUP_FAILED"


def test_safe_filter_rejects_arbitrary_message_even_with_safe_keys():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SafeFieldsFilter())
    logger = logging.getLogger("safe-filter-arbitrary-message")
    logger.handlers = [handler]
    logger.propagate = False
    logger.warning(
        "CLIENTE_PRIVADO",
        extra={"safe_fields": {"error_code": "INTERNAL_ERROR"}},
    )
    assert stream.getvalue() == ""
