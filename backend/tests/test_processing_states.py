import hashlib
import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.app.domain.enums import JobStatus
from backend.app.domain.models import EngineOutcome, TenantPrincipal
from backend.app.logging_config import SafeFieldsFilter
from backend.app.security import protect_drive_file_id


class ControlledAdapter:
    def __init__(self, *, review=False, fail_names=()):
        self.review = review
        self.fail_names = set(fail_names)
        self.calls = 0
        self.active = 0
        self.maximum_active = 0
        self._state_lock = threading.Lock()

    def process(self, *, result_path, display_name, **_kwargs):
        with self._state_lock:
            self.calls += 1
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            time.sleep(0.05)
            if display_name in self.fail_names:
                raise RuntimeError("CLIENTE_SECRETO ruta/privada valor=999")
            result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
            return EngineOutcome(requires_review=self.review)
        finally:
            with self._state_lock:
                self.active -= 1


def safe_logger():
    stream = io.StringIO()
    logger = logging.getLogger(f"test-safe-worker-{uuid4()}")
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.addFilter(SafeFieldsFilter())
    logger.addHandler(handler)
    return logger, stream


def prepare_received_job(service, *, display_name, drive_hmac):
    job_id = uuid4()
    job, created = service.repository.create_or_get(
        job_id=job_id,
        tenant_id="tenant-a",
        drive_file_hmac=drive_hmac,
        content_sha256=hashlib.sha256(str(job_id).encode()).hexdigest(),
        drive_revision=None,
        safe_original_name=display_name,
    )
    assert created is True
    input_path = service.storage.input_path(job_id)
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(b"%PDF-1.4\nSYNTHETIC_TEST_ONLY")
    service.storage.work_directory(job_id).mkdir(parents=True, exist_ok=True)
    service.storage.result_path(job_id).parent.mkdir(parents=True, exist_ok=True)
    return job


def test_one_document_at_a_time_inside_instance(app):
    service = app.state.job_service
    adapter = ControlledAdapter()
    service.processor.adapter = adapter
    first = prepare_received_job(service, display_name="first.pdf", drive_hmac="a" * 64)
    second = prepare_received_job(service, display_name="second.pdf", drive_hmac="b" * 64)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(service.processor.process, [first.id, second.id]))

    assert [result.status for result in results] == [
        JobStatus.COMPLETADO,
        JobStatus.COMPLETADO,
    ]
    assert adapter.maximum_active == 1


def test_processing_lock_is_released_after_engine_exception(app):
    service = app.state.job_service
    adapter = ControlledAdapter(fail_names={"fail.pdf"})
    service.processor.adapter = adapter
    failed = prepare_received_job(service, display_name="fail.pdf", drive_hmac="c" * 64)
    following = prepare_received_job(service, display_name="following.pdf", drive_hmac="d" * 64)

    failed_result = service.processor.process(failed.id)
    following_result = service.processor.process(following.id)

    assert failed_result.status == JobStatus.ERROR
    assert following_result.status == JobStatus.COMPLETADO
    assert adapter.calls == 2
    assert adapter.maximum_active == 1


def test_existing_processing_job_is_not_started_again(
    app, settings, synthetic_pdf
):
    service = app.state.job_service
    adapter = ControlledAdapter()
    service.processor.adapter = adapter
    drive_id = "drive-file-sintetico"
    drive_hmac = protect_drive_file_id(
        "tenant-a", drive_id, settings.require_hmac_secret()
    )
    existing, created = service.repository.create_or_get(
        job_id=uuid4(),
        tenant_id="tenant-a",
        drive_file_hmac=drive_hmac,
        content_sha256=hashlib.sha256(synthetic_pdf).hexdigest(),
        drive_revision=None,
        safe_original_name="documento.pdf",
    )
    assert created is True
    service.repository.transition(
        existing.id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    upload = UploadFile(
        file=io.BytesIO(synthetic_pdf),
        filename="documento.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )

    returned = service.create_job(
        principal=TenantPrincipal("tenant-a"),
        drive_file_id=drive_id,
        drive_revision=None,
        upload=upload,
    )
    assert returned.id == existing.id
    assert returned.status == JobStatus.PROCESANDO
    assert adapter.calls == 0


def test_previous_error_is_terminal_and_not_retried(app, settings, synthetic_pdf):
    service = app.state.job_service
    adapter = ControlledAdapter()
    service.processor.adapter = adapter
    drive_id = "drive-file-error"
    drive_hmac = protect_drive_file_id(
        "tenant-a", drive_id, settings.require_hmac_secret()
    )
    existing, _created = service.repository.create_or_get(
        job_id=uuid4(),
        tenant_id="tenant-a",
        drive_file_hmac=drive_hmac,
        content_sha256=hashlib.sha256(synthetic_pdf).hexdigest(),
        drive_revision=None,
        safe_original_name="documento.pdf",
    )
    service.repository.transition(
        existing.id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    service.repository.transition(
        existing.id,
        JobStatus.PROCESANDO,
        JobStatus.ERROR,
        "ENGINE_PROCESSING_FAILED",
    )
    upload = UploadFile(
        file=io.BytesIO(synthetic_pdf),
        filename="documento.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    returned = service.create_job(
        principal=TenantPrincipal("tenant-a"),
        drive_file_id=drive_id,
        drive_revision=None,
        upload=upload,
    )
    assert returned.status == JobStatus.ERROR
    assert adapter.calls == 0


@pytest.mark.parametrize(
    ("review", "expected"),
    [(False, JobStatus.COMPLETADO), (True, JobStatus.REVISAR)],
)
def test_post_returns_terminal_success_state(
    client, app, auth_headers, synthetic_pdf, review, expected
):
    app.state.job_service.processor.adapter = ControlledAdapter(review=review)
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == expected.value
    assert response.json()["result_available"] is True


def test_post_returns_sanitized_error_and_get_recovers_it(
    client, app, auth_headers, synthetic_pdf
):
    adapter = ControlledAdapter(fail_names={"documento.pdf"})
    app.state.job_service.processor.adapter = adapter
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    payload = response.json()
    recovered = client.get(
        f"/v1/jobs/{payload['job_id']}", headers=auth_headers
    ).json()
    assert payload["status"] == JobStatus.ERROR.value
    assert payload["error_code"] == "INTERNAL_ERROR"
    assert recovered == payload


def test_processor_does_not_log_sensitive_exception(
    client, app, auth_headers, synthetic_pdf
):
    logger, stream = safe_logger()
    app.state.job_service.processor.logger = logger
    app.state.job_service.processor.adapter = ControlledAdapter(
        fail_names={"documento.pdf"}
    )
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )
    output = stream.getvalue()
    assert response.json()["status"] == JobStatus.ERROR.value
    assert "CLIENTE_SECRETO" not in output
    assert "ruta/privada" not in output
    assert "999" not in output
    assert "ENGINE_PROCESSING_FAILED" in output
