from datetime import UTC, datetime, timedelta
from uuid import UUID


def test_retention_uses_controlled_clock_and_marks_result_expired(
    client, app, auth_headers, synthetic_pdf
):
    created = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    ).json()
    job_id = UUID(created["job_id"])
    result = app.state.retention_service.cleanup_expired_results(
        now=datetime.now(UTC) + timedelta(hours=25)
    )
    assert result.removed == 1
    assert result.failed == 0
    assert not app.state.job_service.storage.result_path(job_id).exists()
    assert not app.state.job_service.storage.input_path(job_id).exists()
    recovered = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
    assert recovered["result_available"] is False
    assert recovered["error_code"] == "RESULT_EXPIRED"


def test_retention_query_failure_is_fully_isolated(app, monkeypatch):
    monkeypatch.setattr(
        app.state.job_service.repository,
        "expired_terminal_jobs",
        lambda _cutoff: (_ for _ in ()).throw(RuntimeError("sensitive")),
    )
    result = app.state.retention_service.cleanup_expired_results()
    assert result.query_failed is True
    assert result.removed == 0
