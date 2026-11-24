from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from ..domain.enums import JobStatus
from ..domain.models import JobView


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "drive_file_hmac",
            "content_sha256",
            name="uq_jobs_tenant_drive_content",
        ),
        Index("ix_jobs_tenant_drive_created", "tenant_id", "drive_file_hmac", "created_at"),
        Index("ix_jobs_tenant_id", "tenant_id", "id"),
        CheckConstraint(
            "status IN ('RECIBIDO', 'PROCESANDO', 'COMPLETADO', 'REVISAR', 'ERROR')",
            name="ck_jobs_status",
        ),
        CheckConstraint(
            "length(drive_file_hmac) = 64", name="ck_jobs_drive_hmac_length"
        ),
        CheckConstraint(
            "drive_file_hmac = lower(drive_file_hmac)",
            name="ck_jobs_drive_hmac_lowercase",
        ),
        CheckConstraint(
            "length(content_sha256) = 64", name="ck_jobs_content_sha_length"
        ),
        CheckConstraint(
            "content_sha256 = lower(content_sha256)",
            name="ck_jobs_content_sha_lowercase",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count"),
        CheckConstraint(
            "status != 'PROCESANDO' OR processing_started_at IS NOT NULL",
            name="ck_jobs_processing_started",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    drive_file_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    drive_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    safe_original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_view(self) -> JobView:
        created_at = self.created_at
        updated_at = self.updated_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        else:
            created_at = created_at.astimezone(UTC)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        else:
            updated_at = updated_at.astimezone(UTC)
        result_expires_at = self.result_expires_at
        if result_expires_at is not None and result_expires_at.tzinfo is None:
            result_expires_at = result_expires_at.replace(tzinfo=UTC)
        elif result_expires_at is not None:
            result_expires_at = result_expires_at.astimezone(UTC)
        processing_started_at = self.processing_started_at
        if processing_started_at is not None and processing_started_at.tzinfo is None:
            processing_started_at = processing_started_at.replace(tzinfo=UTC)
        elif processing_started_at is not None:
            processing_started_at = processing_started_at.astimezone(UTC)
        return JobView(
            id=UUID(self.id),
            tenant_id=self.tenant_id,
            status=JobStatus(self.status),
            original_filename=self.safe_original_name,
            previous_job_id=UUID(self.previous_job_id) if self.previous_job_id else None,
            error_code=self.error_code,
            result_expires_at=result_expires_at,
            processing_started_at=processing_started_at,
            attempt_count=self.attempt_count,
            created_at=created_at,
            updated_at=updated_at,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_engine(database_url: str) -> Engine:
    options: dict[str, object] = {"pool_pre_ping": True, "echo": False}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **options)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
