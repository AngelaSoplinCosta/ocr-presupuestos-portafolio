"""Crea trabajos OCR con idempotencia aislada por tenant."""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("drive_file_hmac", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("drive_revision", sa.String(length=255), nullable=True),
        sa.Column("safe_original_name", sa.String(length=255), nullable=False),
        sa.Column("previous_job_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("result_storage_key", sa.String(length=255), nullable=True),
        sa.Column("result_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["previous_job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('RECIBIDO', 'PROCESANDO', 'COMPLETADO', 'REVISAR', 'ERROR')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "length(drive_file_hmac) = 64", name="ck_jobs_drive_hmac_length"
        ),
        sa.CheckConstraint(
            "drive_file_hmac = lower(drive_file_hmac)",
            name="ck_jobs_drive_hmac_lowercase",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_jobs_content_sha_length"
        ),
        sa.CheckConstraint(
            "content_sha256 = lower(content_sha256)",
            name="ck_jobs_content_sha_lowercase",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count"),
        sa.CheckConstraint(
            "status != 'PROCESANDO' OR processing_started_at IS NOT NULL",
            name="ck_jobs_processing_started",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "drive_file_hmac",
            "content_sha256",
            name="uq_jobs_tenant_drive_content",
        ),
    )
    op.create_index(
        "ix_jobs_tenant_drive_created",
        "jobs",
        ["tenant_id", "drive_file_hmac", "created_at"],
    )
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_tenant_id", table_name="jobs")
    op.drop_index("ix_jobs_tenant_drive_created", table_name="jobs")
    op.drop_table("jobs")
