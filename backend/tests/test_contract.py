from datetime import UTC, datetime
from uuid import uuid4

from backend.app.domain.enums import JobErrorCode, JobStatus
from backend.app.domain.models import JobView
from backend.app.schemas.jobs import JobResponse


def test_shared_job_states_and_error_codes_are_fixed():
    assert [status.value for status in JobStatus] == [
        "RECIBIDO",
        "PROCESANDO",
        "COMPLETADO",
        "REVISAR",
        "ERROR",
    ]
    assert {code.value for code in JobErrorCode} == {
        "INVALID_PDF",
        "FILE_TOO_LARGE",
        "UNSUPPORTED_DOCUMENT_TYPE",
        "PROCESSING_CAPACITY_BUSY",
        "PROCESS_INTERRUPTED",
        "RESULT_EXPIRED",
        "INTERNAL_ERROR",
    }


def test_job_response_exposes_the_shared_contract_fields():
    now = datetime.now(UTC)
    job = JobView(
        id=uuid4(),
        tenant_id="tenant-a",
        status=JobStatus.REVISAR,
        original_filename="presupuesto.pdf",
        previous_job_id=None,
        error_code=None,
        result_expires_at=now,
        processing_started_at=now,
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )

    response = JobResponse.from_view(job, result_available=True)

    assert response.model_dump().keys() >= {
        "job_id",
        "document_type",
        "original_filename",
        "status",
        "error_code",
        "requires_review",
        "result_available",
        "result_expires_at",
        "created_at",
        "updated_at",
    }
    assert response.document_type == "budget"
    assert response.original_filename == "presupuesto.pdf"
    assert response.requires_review is True


def test_job_response_sanitizes_internal_error_codes():
    now = datetime.now(UTC)
    job = JobView(
        id=uuid4(),
        tenant_id="tenant-a",
        status=JobStatus.ERROR,
        original_filename="presupuesto.pdf",
        previous_job_id=None,
        error_code="ENGINE_PROCESSING_FAILED",
        result_expires_at=None,
        processing_started_at=None,
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )

    response = JobResponse.from_view(job, result_available=False)

    assert response.error_code == JobErrorCode.INTERNAL_ERROR
