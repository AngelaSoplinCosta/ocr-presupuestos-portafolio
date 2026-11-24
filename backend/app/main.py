from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from .adapters.motor_presupuestos import MotorPresupuestosAdapter
from .api.middleware import RequestBoundaryMiddleware
from .api.routes.jobs import router as jobs_router
from .api.routes.local_jobs import router as local_jobs_router
from .config import Settings
from .domain.errors import (
    AuthenticationFailed,
    ConfigurationError,
    InvalidUpload,
    JobNotFound,
    ResultNotReady,
    StaleTransition,
    StorageCleanupFailed,
)
from .infrastructure.database import build_engine, build_session_factory
from .infrastructure.repositories.jobs import SqlAlchemyJobRepository
from .infrastructure.storage.local import LocalJobStorage
from .logging_config import SafeFieldsFilter, configure_safe_logging, log_job_event
from .schemas.jobs import HealthResponse
from .services.concurrency import SingleInstanceProcessingGate
from .services.job_service import JobService
from .services.process_job import JobProcessor
from .services.retention import RetentionService


def create_app(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    adapter: MotorPresupuestosAdapter | None = None,
    gate: SingleInstanceProcessingGate | None = None,
) -> FastAPI:
    chosen_settings = settings or Settings()
    chosen_engine = engine or build_engine(chosen_settings.database_url)
    repository = SqlAlchemyJobRepository(build_session_factory(chosen_engine))
    logger = configure_safe_logging()
    storage = LocalJobStorage(
        chosen_settings.job_storage_root,
        chosen_settings.max_upload_bytes,
        chosen_settings.upload_chunk_bytes,
    )
    processor = JobProcessor(
        settings=chosen_settings,
        repository=repository,
        storage=storage,
        adapter=adapter or MotorPresupuestosAdapter(),
        logger=logger,
        gate=gate or SingleInstanceProcessingGate(),
    )
    service = JobService(
        settings=chosen_settings,
        repository=repository,
        storage=storage,
        processor=processor,
    )
    retention = RetentionService(
        repository=repository,
        storage=storage,
        logger=logger,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.startup_error_code = None
        try:
            service.preflight()
            interrupted_count = service.recover_interrupted_jobs()
            if interrupted_count:
                log_job_event(
                    logger,
                    status="PROCESS_INTERRUPTED",
                    error_code="PROCESS_INTERRUPTED",
                    metric="startup_recovery",
                    count=interrupted_count,
                )
            retention.cleanup_expired_results()
        except Exception as exc:
            candidate = str(exc)
            error_code = (
                candidate
                if SafeFieldsFilter.SAFE_CODE.fullmatch(candidate)
                else "STARTUP_READINESS_FAILED"
            )
            application.state.startup_error_code = error_code
            log_job_event(
                logger,
                status="STARTUP_FAILED",
                error_code=error_code,
            )
        yield

    application = FastAPI(
        title="OCR Orchestration API",
        version="1.0.0",
        docs_url="/docs" if chosen_settings.docs_enabled else None,
        redoc_url="/redoc" if chosen_settings.docs_enabled else None,
        openapi_url="/openapi.json" if chosen_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = chosen_settings
    application.state.job_service = service
    application.include_router(jobs_router)
    application.include_router(local_jobs_router)

    application.state.retention_service = retention

    def safe_error(request: Request, status_code: int, error_code: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        if status_code >= 500 and request_id is not None:
            log_job_event(
                logger,
                request_id=request_id,
                status="REQUEST_FAILED",
                error_code=error_code,
            )
        content = {
            "request_id": request_id,
            "error_code": error_code,
            "message": "No se pudo procesar la solicitud",
        }
        return JSONResponse(status_code=status_code, content=content)

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    def live() -> HealthResponse:
        return HealthResponse(status="live")

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    def ready():
        startup_error = application.state.startup_error_code
        if startup_error:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "error_code": startup_error},
            )
        try:
            service.preflight()
        except Exception as exc:
            candidate = str(exc)
            error_code = (
                candidate
                if SafeFieldsFilter.SAFE_CODE.fullmatch(candidate)
                else "READINESS_CHECK_FAILED"
            )
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "error_code": error_code},
            )
        return HealthResponse(status="ready")

    @application.exception_handler(AuthenticationFailed)
    async def authentication_error(_request: Request, _exc: AuthenticationFailed):
        return safe_error(_request, 401, "AUTHENTICATION_FAILED")

    @application.exception_handler(InvalidUpload)
    async def upload_error(_request: Request, exc: InvalidUpload):
        status_code = 413 if str(exc) == "FILE_TOO_LARGE" else 422
        return safe_error(_request, status_code, str(exc))

    @application.exception_handler(ConfigurationError)
    async def configuration_error(_request: Request, exc: ConfigurationError):
        return safe_error(_request, 503, str(exc))

    @application.exception_handler(JobNotFound)
    async def not_found(_request: Request, _exc: JobNotFound):
        error_code = str(_exc)
        if SafeFieldsFilter.SAFE_CODE.fullmatch(error_code) is None:
            error_code = "JOB_NOT_FOUND"
        return safe_error(_request, 404, error_code)

    @application.exception_handler(ResultNotReady)
    async def result_not_ready(_request: Request, _exc: ResultNotReady):
        return safe_error(_request, 409, "RESULT_NOT_READY")

    @application.exception_handler(StaleTransition)
    async def stale_transition(_request: Request, _exc: StaleTransition):
        return safe_error(_request, 409, "STALE_JOB_TRANSITION")

    @application.exception_handler(StorageCleanupFailed)
    async def cleanup_error(_request: Request, exc: StorageCleanupFailed):
        return safe_error(_request, 500, str(exc))

    application.add_middleware(
        RequestBoundaryMiddleware,
        settings=chosen_settings,
        preflight=service.preflight,
        logger=logger,
    )

    return application


app = create_app()
