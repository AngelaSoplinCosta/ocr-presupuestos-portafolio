from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from backend.app.domain.enums import JobStatus


def _create(client, headers, content):
    return client.post(
        "/v1/jobs",
        headers=headers,
        files={"file": ("documento.pdf", content, "application/pdf")},
    ).json()


def test_result_is_unavailable_before_terminal_state(
    client, app, auth_headers, synthetic_pdf
):
    job = _create(client, auth_headers, synthetic_pdf)
    job_id = UUID(job["job_id"])
    service = app.state.job_service
    service.repository.prepare_retry(job_id, JobStatus.COMPLETADO)
    service.repository.transition(
        job_id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    response = client.get(f"/v1/jobs/{job['job_id']}/result", headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["error_code"] == "RESULT_NOT_READY"


@pytest.mark.parametrize("terminal_status", [JobStatus.COMPLETADO, JobStatus.REVISAR])
def test_result_is_available_for_success_and_review(
    client, app, adapter, auth_headers, synthetic_pdf, terminal_status
):
    adapter.review = terminal_status == JobStatus.REVISAR
    job = _create(client, auth_headers, synthetic_pdf)
    job_id = UUID(job["job_id"])
    service = app.state.job_service
    assert job["status"] == terminal_status.value

    response = client.get(f"/v1/jobs/{job_id}/result", headers=auth_headers)
    assert response.status_code == 200
    assert response.content == b"SYNTHETIC_XLSX_TEST_ONLY"
    status_response = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    assert status_response.json()["result_available"] is True


def test_expired_result_is_not_downloadable(
    client, app, auth_headers, synthetic_pdf
):
    job = _create(client, auth_headers, synthetic_pdf)
    job_id = UUID(job["job_id"])
    service = app.state.job_service
    service.repository.prepare_retry(job_id, JobStatus.COMPLETADO)
    service.repository.transition(
        job_id,
        JobStatus.RECIBIDO,
        JobStatus.PROCESANDO,
        increment_attempt=True,
    )
    service.repository.transition(
        job_id,
        JobStatus.PROCESANDO,
        JobStatus.COMPLETADO,
        result_storage_key=service.storage.result_storage_key(job_id),
        result_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    status_response = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
    result_response = client.get(
        f"/v1/jobs/{job_id}/result", headers=auth_headers
    )
    assert status_response.json()["result_available"] is False
    assert status_response.json()["error_code"] == "RESULT_EXPIRED"
    assert result_response.status_code == 404
    assert result_response.json()["error_code"] == "RESULT_NOT_FOUND"
