import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ...domain.enums import JobStatus
from ...domain.errors import StaleTransition
from ...domain.models import JobView
from ..database import JobRecord, utc_now

HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class SqlAlchemyJobRepository:
    _ALLOWED_TRANSITIONS = {
        JobStatus.RECIBIDO: {JobStatus.PROCESANDO},
        JobStatus.PROCESANDO: {
            JobStatus.COMPLETADO,
            JobStatus.REVISAR,
            JobStatus.ERROR,
        },
        JobStatus.COMPLETADO: {JobStatus.RECIBIDO},
        JobStatus.REVISAR: {JobStatus.RECIBIDO},
        JobStatus.ERROR: {JobStatus.RECIBIDO},
    }

    def __init__(self, session_factory: sessionmaker[Session]):
        self._sessions = session_factory

    def create_or_get(
        self,
        *,
        job_id: UUID,
        tenant_id: str,
        drive_file_hmac: str,
        content_sha256: str,
        drive_revision: str | None,
        safe_original_name: str,
    ) -> tuple[JobView, bool]:
        if not tenant_id or len(tenant_id) > 128:
            raise ValueError("INVALID_TENANT_ID")
        if HEX_64.fullmatch(drive_file_hmac) is None:
            raise ValueError("INVALID_DRIVE_HMAC")
        if HEX_64.fullmatch(content_sha256) is None:
            raise ValueError("INVALID_CONTENT_SHA256")
        if not safe_original_name or len(safe_original_name) > 255:
            raise ValueError("INVALID_ORIGINAL_NAME")
        if drive_revision is not None and len(drive_revision) > 255:
            raise ValueError("INVALID_DRIVE_REVISION")
        now = utc_now()
        with self._sessions() as session:
            if session.get_bind().dialect.name == "postgresql":
                lock_key = int(drive_file_hmac[:16], 16)
                if lock_key >= 2**63:
                    lock_key -= 2**64
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            previous = session.scalars(
                select(JobRecord)
                .where(
                    JobRecord.tenant_id == tenant_id,
                    JobRecord.drive_file_hmac == drive_file_hmac,
                )
                .order_by(JobRecord.created_at.desc())
                .limit(1)
            ).first()
            record = JobRecord(
                id=str(job_id),
                tenant_id=tenant_id,
                drive_file_hmac=drive_file_hmac,
                content_sha256=content_sha256,
                drive_revision=drive_revision,
                safe_original_name=safe_original_name,
                previous_job_id=(
                    previous.id
                    if previous is not None and previous.content_sha256 != content_sha256
                    else None
                ),
                status=JobStatus.RECIBIDO.value,
                attempt_count=0,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            try:
                session.commit()
                return record.to_view(), True
            except IntegrityError:
                session.rollback()
                existing = session.scalars(
                    select(JobRecord).where(
                        JobRecord.tenant_id == tenant_id,
                        JobRecord.drive_file_hmac == drive_file_hmac,
                        JobRecord.content_sha256 == content_sha256,
                    )
                ).one_or_none()
                if existing is None:
                    raise
                return existing.to_view(), False

    def get_for_tenant(self, job_id: UUID, tenant_id: str) -> JobView | None:
        with self._sessions() as session:
            record = session.scalar(
                select(JobRecord).where(
                    JobRecord.id == str(job_id), JobRecord.tenant_id == tenant_id
                )
            )
            return record.to_view() if record else None

    def get_internal(self, job_id: UUID) -> JobRecord | None:
        with self._sessions() as session:
            record = session.get(JobRecord, str(job_id))
            if record is not None:
                session.expunge(record)
            return record

    def transition(
        self,
        job_id: UUID,
        expected_status: JobStatus,
        status: JobStatus,
        error_code: str | None = None,
        *,
        result_storage_key: str | None = None,
        result_expires_at: datetime | None = None,
        increment_attempt: bool = False,
    ) -> JobView:
        if status not in self._ALLOWED_TRANSITIONS.get(expected_status, set()):
            raise ValueError("INVALID_STATE_TRANSITION")
        values: dict[str, object] = {
            "status": status.value,
            "error_code": error_code,
            "result_storage_key": result_storage_key,
            "result_expires_at": result_expires_at,
            "updated_at": utc_now(),
            "processing_started_at": (
                utc_now() if status == JobStatus.PROCESANDO else None
            ),
        }
        if increment_attempt:
            values["attempt_count"] = JobRecord.attempt_count + 1
        with self._sessions() as session:
            result = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == str(job_id),
                    JobRecord.status == expected_status.value,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                session.rollback()
                raise StaleTransition("STALE_JOB_TRANSITION")
            session.commit()
            record = session.get(JobRecord, str(job_id))
            if record is None:
                raise LookupError("JOB_NOT_FOUND")
            return record.to_view()

    def prepare_retry(
        self, job_id: UUID, expected_status: JobStatus
    ) -> JobView:
        return self.transition(job_id, expected_status, JobStatus.RECIBIDO)

    def recover_interrupted_processing(self) -> list[UUID]:
        now = utc_now()
        with self._sessions() as session:
            records = session.scalars(
                select(JobRecord).where(
                    JobRecord.status == JobStatus.PROCESANDO.value
                )
            ).all()
            identifiers = [UUID(record.id) for record in records]
            for record in records:
                record.status = JobStatus.ERROR.value
                record.error_code = "PROCESS_INTERRUPTED"
                record.processing_started_at = None
                record.result_storage_key = None
                record.result_expires_at = None
                record.updated_at = now
            session.commit()
            return identifiers

    def expired_terminal_jobs(
        self, cutoff: datetime
    ) -> list[tuple[UUID, JobStatus]]:
        with self._sessions() as session:
            rows = session.execute(
                select(JobRecord.id, JobRecord.status).where(
                    JobRecord.status.in_(
                        [JobStatus.COMPLETADO.value, JobStatus.REVISAR.value]
                    ),
                    JobRecord.result_expires_at.is_not(None),
                    JobRecord.result_expires_at < cutoff,
                )
            ).all()
            return [(UUID(identifier), JobStatus(status)) for identifier, status in rows]

    def mark_result_expired(
        self, job_id: UUID, expected_status: JobStatus
    ) -> None:
        with self._sessions() as session:
            result = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == str(job_id),
                    JobRecord.status == expected_status.value,
                )
                .values(
                    error_code="RESULT_EXPIRED",
                    result_storage_key=None,
                    processing_started_at=None,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                session.rollback()
                raise StaleTransition("STALE_JOB_TRANSITION")
            session.commit()

    def schema_is_current(self) -> bool:
        required_columns = {
            "id",
            "tenant_id",
            "drive_file_hmac",
            "content_sha256",
            "status",
            "processing_started_at",
            "attempt_count",
        }
        required_checks = {
            "ck_jobs_status",
            "ck_jobs_drive_hmac_length",
            "ck_jobs_drive_hmac_lowercase",
            "ck_jobs_content_sha_length",
            "ck_jobs_content_sha_lowercase",
            "ck_jobs_attempt_count",
            "ck_jobs_processing_started",
        }
        with self._sessions() as session:
            session.execute(select(1))
            inspector = inspect(session.get_bind())
            if not inspector.has_table(JobRecord.__tablename__):
                return False
            columns = {
                column["name"]
                for column in inspector.get_columns(JobRecord.__tablename__)
            }
            unique_constraints = {
                constraint.get("name")
                for constraint in inspector.get_unique_constraints(
                    JobRecord.__tablename__
                )
            }
            checks = {
                constraint.get("name")
                for constraint in inspector.get_check_constraints(
                    JobRecord.__tablename__
                )
            }
            return (
                required_columns.issubset(columns)
                and "uq_jobs_tenant_drive_content" in unique_constraints
                and required_checks.issubset(checks)
            )
