import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.domain.enums import JobStatus
from backend.app.domain.errors import StaleTransition
from backend.app.domain.models import EngineOutcome
from backend.app.infrastructure.database import Base, build_engine, build_session_factory
from backend.app.infrastructure.repositories.jobs import SqlAlchemyJobRepository
from backend.app.main import create_app
from backend.app.security import protect_drive_file_id


class RecoveryAdapter:
    def __init__(self):
        self.calls = 0

    def process(self, *, result_path, **_kwargs):
        self.calls += 1
        result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
        return EngineOutcome(requires_review=False)


def test_startup_marks_interrupted_job_and_explicit_upload_retries_it(
    settings, api_token, synthetic_pdf
):
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    repository = SqlAlchemyJobRepository(build_session_factory(engine))
    drive_id = "drive-recovery"
    job, created = repository.create_or_get(
        job_id=uuid4(),
        tenant_id="tenant-a",
        drive_file_hmac=protect_drive_file_id(
            "tenant-a", drive_id, settings.require_hmac_secret()
        ),
        content_sha256=hashlib.sha256(synthetic_pdf).hexdigest(),
        drive_revision=None,
        safe_original_name="documento.pdf",
    )
    assert created is True
    processing = repository.transition(
        job.id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    assert processing.processing_started_at is not None
    assert processing.attempt_count == 1

    adapter = RecoveryAdapter()
    app = create_app(settings=settings, engine=engine, adapter=adapter)
    headers = {"X-API-Key": api_token, "X-Drive-File-Id": drive_id}
    with TestClient(app) as client:
        interrupted = client.get(f"/v1/jobs/{job.id}", headers=headers).json()
        assert interrupted["status"] == "ERROR"
        assert interrupted["error_code"] == "PROCESS_INTERRUPTED"
        assert interrupted["processing_started_at"] is None

        retried = client.post(
            "/v1/jobs",
            headers=headers,
            files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
        ).json()
        assert retried["job_id"] == str(job.id)
        assert retried["status"] == "COMPLETADO"
        assert retried["attempt_count"] == 2
        assert adapter.calls == 1


def test_stale_transition_does_not_overwrite_newer_state(app):
    service = app.state.job_service
    job, _created = service.repository.create_or_get(
        job_id=uuid4(),
        tenant_id="tenant-a",
        drive_file_hmac="f" * 64,
        content_sha256="a" * 64,
        drive_revision=None,
        safe_original_name="documento.pdf",
    )
    service.repository.transition(
        job.id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    with pytest.raises(StaleTransition):
        service.repository.transition(
            job.id,
            JobStatus.RECIBIDO,
            JobStatus.PROCESANDO,
            increment_attempt=True,
        )
    current = service.repository.get_internal(job.id)
    assert current is not None
    assert current.status == JobStatus.PROCESANDO.value
    assert current.attempt_count == 1


def test_explicit_upload_resumes_job_left_received(
    client, app, settings, auth_headers, synthetic_pdf, adapter
):
    service = app.state.job_service
    drive_id = "drive-left-received"
    received, created = service.repository.create_or_get(
        job_id=uuid4(),
        tenant_id="tenant-a",
        drive_file_hmac=protect_drive_file_id(
            "tenant-a", drive_id, settings.require_hmac_secret()
        ),
        content_sha256=hashlib.sha256(synthetic_pdf).hexdigest(),
        drive_revision=None,
        safe_original_name="documento.pdf",
    )
    assert created is True

    response = client.post(
        "/v1/jobs",
        headers={**auth_headers, "X-Drive-File-Id": drive_id},
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["job_id"] == str(received.id)
    assert payload["status"] == "COMPLETADO"
    assert payload["attempt_count"] == 1
    assert adapter.calls == 1
