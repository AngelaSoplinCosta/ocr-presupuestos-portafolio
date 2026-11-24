from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, Field

from ..domain.enums import JobErrorCode, JobStatus
from ..domain.models import JobView


class JobResponse(BaseModel):
    job_id: UUID
    document_type: Literal["budget"]
    original_filename: str
    status: JobStatus
    previous_job_id: UUID | None
    result_available: bool
    requires_review: bool
    error_code: JobErrorCode | None
    result_expires_at: datetime | None
    processing_started_at: datetime | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(
        cls, job: JobView, *, result_available: bool
    ) -> "JobResponse":
        public_error_code = None
        if job.error_code is not None:
            try:
                public_error_code = JobErrorCode(job.error_code)
            except ValueError:
                public_error_code = JobErrorCode.INTERNAL_ERROR
        return cls(
            job_id=job.id,
            document_type="budget",
            original_filename=job.original_filename,
            status=job.status,
            previous_job_id=job.previous_job_id,
            result_available=result_available,
            requires_review=job.status == JobStatus.REVISAR,
            error_code=public_error_code,
            result_expires_at=job.result_expires_at,
            processing_started_at=job.processing_started_at,
            attempt_count=job.attempt_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class HealthResponse(BaseModel):
    status: str
    error_code: str | None = None


class ReviewRowResponse(BaseModel):
    order: int | None
    type: str
    label: str


class ReviewSuggestionResponse(BaseModel):
    value: str
    confidence: str


class ReviewObservationResponse(BaseModel):
    id: str
    state: str
    kind: str
    page: int | None
    row: ReviewRowResponse
    field: str
    extracted_value: str
    suggestion: ReviewSuggestionResponse | None
    reason: str
    evidence: list[str]
    allowed_actions: list[str]
    requires_decision: bool
    target: dict[str, str] | None = None
    decision: dict[str, str] | None = None
    resolved_value: str | None = None


class ReviewResponse(BaseModel):
    schema_version: str
    job_id: UUID
    status: Literal["REVISAR", "COMPLETADO"]
    review_revision: int
    total_count: int
    requires_decision_count: int
    pending_decision_count: int
    offset: int
    limit: int
    result_expires_at: datetime
    observations: list[ReviewObservationResponse]


class ReviewDecisionInput(BaseModel):
    observation_id: str
    action: Literal["accept_suggestion", "keep_original", "keep_provisional", "set_value", "confirm_provisional_row"]
    field: Literal["item", "description", "unit", "quantity", "unit_price", "amount"] | None = None
    value: str | None = None


class ReviewDecisionRequest(BaseModel):
    review_revision: int
    decisions: list[ReviewDecisionInput] = Field(max_length=50)


class ReviewDecisionResponse(BaseModel):
    review_revision: int
    pending_decision_count: int


class StructuredReviewFieldResponse(BaseModel):
    key: Literal["item", "description", "unit", "quantity", "unit_price", "amount"]
    label: str
    ocr_value: str | None = None
    provisional_value: str
    suggestion: ReviewSuggestionResponse | None = None
    differs_from_ocr: bool | None = None
    state: Literal["PENDING", "RESOLVED"]
    decision: dict[str, str] | None = None
    can_confirm_provisional: bool
    manual_only: bool


class StructuredReviewResponse(BaseModel):
    observation_id: str
    raw_ocr_line: str
    fields: list[StructuredReviewFieldResponse]
    confirmed_field_count: int
    pending_field_count: int
    legacy_row_decision: dict[str, str] | None = None


class ReviewTableRowResponse(BaseModel):
    row_key: str
    page: int | None
    order: int | None
    cells: dict[str, str]
    observations: list[ReviewObservationResponse]
    structured_review: StructuredReviewResponse | None = None


class ReviewTableResponse(BaseModel):
    schema_version: str
    job_id: UUID
    review_revision: int
    pending_decision_count: int
    filter: Literal["pending", "resolved", "all"]
    offset: int
    limit: int
    total_count: int
    columns: list["ExportColumnInput"]
    rows: list[ReviewTableRowResponse]


class ExportColumnInput(BaseModel):
    key: str
    label: str
    data_type: Literal["text", "decimal", "currency"] = "text"
    source_header: str | None = None
    included: bool
    position: int
    origin: Literal["standard", "candidate"] = "standard"


class ExportConfigRequest(BaseModel):
    export_revision: int
    columns: list[ExportColumnInput]


class ExportResponse(BaseModel):
    export_revision: int
    source_review_revision: int
    columns: list[ExportColumnInput]
    pending_decision_count: int
    simple_result_available: bool
