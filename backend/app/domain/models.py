from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .enums import JobStatus


@dataclass(frozen=True)
class TenantPrincipal:
    tenant_id: str


@dataclass(frozen=True)
class StoredUpload:
    job_id: UUID
    content_sha256: str
    safe_original_name: str


@dataclass(frozen=True)
class JobView:
    id: UUID
    tenant_id: str
    status: JobStatus
    original_filename: str
    previous_job_id: UUID | None
    error_code: str | None
    result_expires_at: datetime | None
    processing_started_at: datetime | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EngineOutcome:
    requires_review: bool
    observations: tuple["ReviewObservation", ...] = ()
    export_snapshot: dict[str, object] | None = None


@dataclass(frozen=True)
class ReviewSuggestion:
    value: str
    confidence: str


@dataclass(frozen=True)
class ReviewObservation:
    id: str
    state: str
    kind: str
    page: int | None
    row_order: int | None
    row_type: str
    row_label: str
    field: str
    extracted_value: str
    suggestion: ReviewSuggestion | None
    reason: str
    evidence: tuple[str, ...]
    allowed_actions: tuple[str, ...] = ()
    requires_decision: bool = False
