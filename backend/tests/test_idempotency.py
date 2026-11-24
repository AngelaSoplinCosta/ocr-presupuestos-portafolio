from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from backend.app.infrastructure.database import JobRecord


def create(client, headers, content):
    return client.post(
        "/v1/jobs",
        headers=headers,
        files={"file": ("documento.pdf", content, "application/pdf")},
    )


def test_same_drive_file_and_content_returns_existing(
    client, auth_headers, synthetic_pdf, adapter
):
    first = create(client, auth_headers, synthetic_pdf)
    second = create(client, auth_headers, synthetic_pdf)
    assert first.json()["job_id"] == second.json()["job_id"]
    assert adapter.calls == 1


def test_new_content_creates_linked_job(client, auth_headers, synthetic_pdf, adapter):
    first = create(client, auth_headers, synthetic_pdf)
    changed = synthetic_pdf + b"changed"
    second = create(client, auth_headers, changed)
    assert first.json()["job_id"] != second.json()["job_id"]
    assert second.json()["previous_job_id"] == first.json()["job_id"]
    assert adapter.calls == 2


def test_completed_job_without_retained_result_is_regenerated_on_explicit_upload(
    client, app, auth_headers, synthetic_pdf, adapter
):
    first = create(client, auth_headers, synthetic_pdf)
    result = app.state.job_service.storage.result_path(UUID(first.json()["job_id"]))
    result.unlink()
    repeated = create(client, auth_headers, synthetic_pdf)
    assert repeated.json()["job_id"] == first.json()["job_id"]
    assert repeated.json()["status"] == "COMPLETADO"
    assert repeated.json()["result_available"] is True
    assert repeated.json()["attempt_count"] == 2
    assert adapter.calls == 2


def test_model_declares_unique_identity_constraint():
    constraints = [
        constraint
        for constraint in JobRecord.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    identity = next(
        constraint
        for constraint in constraints
        if constraint.name == "uq_jobs_tenant_drive_content"
    )
    assert [column.name for column in identity.columns] == [
        "tenant_id",
        "drive_file_hmac",
        "content_sha256",
    ]


def test_model_declares_state_hash_and_attempt_checks():
    checks = {
        constraint.name
        for constraint in JobRecord.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_jobs_status",
        "ck_jobs_drive_hmac_length",
        "ck_jobs_drive_hmac_lowercase",
        "ck_jobs_content_sha_length",
        "ck_jobs_content_sha_lowercase",
        "ck_jobs_attempt_count",
        "ck_jobs_processing_started",
    }.issubset(checks)


def test_repository_rejects_non_hex_identity(app):
    service = app.state.job_service
    with pytest.raises(ValueError, match="INVALID_DRIVE_HMAC"):
        service.repository.create_or_get(
            job_id=UUID("00000000-0000-4000-8000-000000000001"),
            tenant_id="tenant-a",
            drive_file_hmac="z" * 64,
            content_sha256="a" * 64,
            drive_revision=None,
            safe_original_name="documento.pdf",
        )
