import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ..infrastructure.repositories.jobs import SqlAlchemyJobRepository
from ..infrastructure.storage.base import JobStorage
from ..logging_config import log_job_event


@dataclass(frozen=True)
class RetentionResult:
    removed: int
    failed: int
    query_failed: bool = False


class RetentionService:
    def __init__(
        self,
        *,
        repository: SqlAlchemyJobRepository,
        storage: JobStorage,
        logger: logging.Logger,
    ):
        self.repository = repository
        self.storage = storage
        self.logger = logger

    def cleanup_expired_results(
        self, *, now: datetime | None = None
    ) -> RetentionResult:
        cutoff = now or datetime.now(UTC)
        try:
            expired = self.repository.expired_terminal_jobs(cutoff)
        except Exception:
            log_job_event(
                self.logger,
                status="RESULT_CLEANUP_ERROR",
                error_code="RETENTION_QUERY_FAILED",
                metric="retention_cleanup",
                count=0,
            )
            return RetentionResult(removed=0, failed=0, query_failed=True)

        removed = 0
        failed = 0
        for job_id, status in expired:
            try:
                self.storage.remove_job(job_id)
                self.repository.mark_result_expired(job_id, status)
                removed += 1
            except Exception:
                failed += 1
        log_job_event(
            self.logger,
            status="RESULT_REMOVED",
            metric="retention_cleanup",
            count=removed,
        )
        if failed:
            log_job_event(
                self.logger,
                status="RESULT_CLEANUP_ERROR",
                error_code="RETENTION_CLEANUP_FAILED",
                metric="retention_cleanup",
                count=failed,
            )
        return RetentionResult(removed=removed, failed=failed)
