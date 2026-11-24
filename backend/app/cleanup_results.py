from .config import Settings
from .infrastructure.database import build_engine, build_session_factory
from .infrastructure.repositories.jobs import SqlAlchemyJobRepository
from .infrastructure.storage.local import LocalJobStorage
from .logging_config import configure_safe_logging, log_job_event
from .services.retention import RetentionService


def main() -> int:
    logger = configure_safe_logging()
    try:
        settings = Settings()
        settings.validate_runtime()
        repository = SqlAlchemyJobRepository(
            build_session_factory(build_engine(settings.database_url))
        )
        storage = LocalJobStorage(
            settings.job_storage_root,
            settings.max_upload_bytes,
            settings.upload_chunk_bytes,
        )
        if not repository.schema_is_current() or not storage.check_writable():
            raise RuntimeError("RETENTION_NOT_READY")
        result = RetentionService(
            repository=repository,
            storage=storage,
            logger=logger,
        ).cleanup_expired_results()
        return 1 if result.query_failed or result.failed else 0
    except Exception:
        log_job_event(
            logger,
            status="RESULT_CLEANUP_ERROR",
            error_code="RETENTION_COMMAND_FAILED",
            metric="retention_cleanup",
            count=0,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
