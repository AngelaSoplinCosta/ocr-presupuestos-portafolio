from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.domain.enums import JobStatus
from backend.app.infrastructure.database import Base, build_engine
from backend.app.main import create_app


def local_client(settings, adapter):
    settings = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(settings=settings, engine=engine, adapter=adapter)
    return TestClient(app, client=("127.0.0.1", 8000))


def test_local_endpoint_is_disabled_by_default(client, synthetic_pdf):
    response = client.post(
        "/api/v1/local/jobs",
        headers={"X-Local-Pilot": "1"},
        data={"document_type": "budget"},
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "LOCAL_MODE_DISABLED"


def test_local_content_length_is_rejected_before_storage(
    settings, adapter, synthetic_pdf, monkeypatch
):
    settings = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(settings=settings, engine=engine, adapter=adapter)
    monkeypatch.setattr(
        app.state.job_service.storage,
        "store_upload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("storage must not be reached")
        ),
    )

    with TestClient(app, client=("127.0.0.1", 8000)) as client:
        response = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1", "Content-Length": str(50 * 1024 * 1024 + 1)},
            content=synthetic_pdf,
        )

    assert response.status_code == 413
    assert response.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_local_endpoint_requires_marker_and_budget(settings, adapter, synthetic_pdf):
    with local_client(settings, adapter) as client:
        missing_header = client.post(
            "/api/v1/local/jobs",
            data={"document_type": "budget"},
            files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
        )
        unsupported_type = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1"},
            data={"document_type": "invoice"},
            files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
        )

    assert missing_header.status_code == 403
    assert missing_header.json()["error_code"] == "LOCAL_HEADER_REQUIRED"
    assert unsupported_type.status_code == 422
    assert unsupported_type.json()["error_code"] == "INVALID_DOCUMENT_TYPE"
    assert adapter.calls == 0


def test_local_endpoint_reuses_job_for_identical_uploads(
    settings, adapter, synthetic_pdf
):
    with local_client(settings, adapter) as client:
        responses = [
            client.post(
                "/api/v1/local/jobs",
                headers={"X-Local-Pilot": "1"},
                data={"document_type": "budget"},
                files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
            )
            for _ in range(2)
        ]

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["job_id"] == responses[1].json()["job_id"]
    assert adapter.calls == 1


def test_local_endpoint_rejects_non_loopback_client(settings, adapter, synthetic_pdf):
    settings = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(settings=settings, engine=engine, adapter=adapter)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1"},
            data={"document_type": "budget"},
            files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "LOCAL_ONLY"
    assert adapter.calls == 0


def test_local_endpoint_uses_internal_identity_and_shared_processor(
    settings, adapter, synthetic_pdf
):
    with local_client(settings, adapter) as client:
        response = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1"},
            data={"document_type": "budget"},
            files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["document_type"] == "budget"
    assert payload["original_filename"] == "presupuesto.pdf"
    assert payload["status"] == "COMPLETADO"
    assert payload["result_available"] is True
    assert adapter.calls == 1


def test_local_path_never_uses_real_ocr_adapter(settings, adapter, synthetic_pdf, monkeypatch):
    from backend.app.adapters.motor_presupuestos import MotorPresupuestosAdapter

    monkeypatch.setattr(
        MotorPresupuestosAdapter,
        "process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("real OCR adapter must not be invoked")
        ),
    )
    with local_client(settings, adapter) as client:
        response = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1"},
            data={"document_type": "budget"},
            files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
        )

    assert response.status_code == 200
    assert adapter.calls == 1


def test_local_endpoint_reuses_upload_validation(settings, adapter):
    with local_client(settings, adapter) as client:
        response = client.post(
            "/api/v1/local/jobs",
            headers={"X-Local-Pilot": "1"},
            data={"document_type": "budget"},
            files={"file": ("presupuesto.pdf", b"not a pdf", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_PDF"
    assert adapter.calls == 0


def create_local_job(client, synthetic_pdf):
    return client.post(
        "/api/v1/local/jobs",
        headers={"X-Local-Pilot": "1"},
        data={"document_type": "budget"},
        files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
    )


def test_local_status_returns_public_job(settings, adapter, synthetic_pdf):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}",
            headers={"X-Local-Pilot": "1"},
        )

    assert response.status_code == 200
    assert response.json() == created
    assert "tenant_id" not in response.json()


def test_local_result_has_safe_xlsx_headers(settings, adapter, synthetic_pdf):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}/result",
            headers={"X-Local-Pilot": "1"},
        )

    assert response.status_code == 200
    assert response.content == b"SYNTHETIC_XLSX_TEST_ONLY"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="resultado.xlsx"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_local_source_remains_available_for_review_with_safe_pdf_headers(
    settings, adapter, synthetic_pdf
):
    adapter.review = True
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        job_id = UUID(created["job_id"])
        response = client.get(
            f"/api/v1/local/jobs/{job_id}/source",
            headers={"X-Local-Pilot": "1"},
        )

    assert created["status"] == "REVISAR"
    assert client.app.state.job_service.storage.input_path(job_id).is_file()
    assert response.status_code == 200
    assert response.content == synthetic_pdf
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="source.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_local_review_decisions_rejects_batches_over_50(
    settings, adapter, synthetic_pdf
):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        review = client.get(
            f"/api/v1/local/jobs/{created['job_id']}/review",
            headers={"X-Local-Pilot": "1"},
        ).json()
        response = client.put(
            f"/api/v1/local/jobs/{created['job_id']}/review/decisions",
            headers={"X-Local-Pilot": "1"},
            json={
                "review_revision": review["review_revision"],
                "decisions": [
                    {"observation_id": f"observation-{index}", "action": "keep_original"}
                    for index in range(51)
                ],
            },
        )

    assert response.status_code == 422


def test_local_reads_keep_all_boundary_protections(settings, adapter, synthetic_pdf):
    settings = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(settings=settings, engine=engine, adapter=adapter)
    unknown = uuid4()

    with TestClient(app, client=("127.0.0.1", 8000)) as loopback:
        missing_header = loopback.get(f"/api/v1/local/jobs/{unknown}")
    with TestClient(app) as non_loopback:
        remote = non_loopback.get(
            f"/api/v1/local/jobs/{unknown}", headers={"X-Local-Pilot": "1"}
        )

    disabled_settings = settings.model_copy(update={"local_mode_enabled": False})
    disabled_app = create_app(
        settings=disabled_settings, engine=engine, adapter=adapter
    )
    with TestClient(disabled_app, client=("127.0.0.1", 8000)) as disabled_client:
        disabled = disabled_client.get(
            f"/api/v1/local/jobs/{unknown}", headers={"X-Local-Pilot": "1"}
        )

    assert (missing_header.status_code, missing_header.json()["error_code"]) == (
        403,
        "LOCAL_HEADER_REQUIRED",
    )
    assert (remote.status_code, remote.json()["error_code"]) == (403, "LOCAL_ONLY")
    assert (disabled.status_code, disabled.json()["error_code"]) == (
        404,
        "LOCAL_MODE_DISABLED",
    )


@pytest.mark.parametrize("path_suffix", ["", "/result", "/source"])
def test_local_routes_require_enabled_mode_loopback_and_marker(
    settings, adapter, path_suffix
):
    settings = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(settings=settings, engine=engine, adapter=adapter)
    path = f"/api/v1/local/jobs/{uuid4()}{path_suffix}"

    with TestClient(app, client=("127.0.0.1", 8000)) as loopback:
        missing_header = loopback.get(path)
    with TestClient(app) as non_loopback:
        remote = non_loopback.get(path, headers={"X-Local-Pilot": "1"})

    disabled_settings = settings.model_copy(update={"local_mode_enabled": False})
    disabled_app = create_app(
        settings=disabled_settings, engine=engine, adapter=adapter
    )
    with TestClient(disabled_app, client=("127.0.0.1", 8000)) as disabled_client:
        disabled = disabled_client.get(path, headers={"X-Local-Pilot": "1"})

    assert (missing_header.status_code, missing_header.json()["error_code"]) == (
        403,
        "LOCAL_HEADER_REQUIRED",
    )
    assert (remote.status_code, remote.json()["error_code"]) == (403, "LOCAL_ONLY")
    assert (disabled.status_code, disabled.json()["error_code"]) == (
        404,
        "LOCAL_MODE_DISABLED",
    )


def test_local_routes_cannot_access_another_tenant_job(
    settings, adapter, synthetic_pdf, auth_headers
):
    with local_client(settings, adapter) as client:
        created = client.post(
            "/v1/jobs",
            headers=auth_headers,
            files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
        ).json()
        headers = {"X-Local-Pilot": "1"}
        status_response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}", headers=headers
        )
        result_response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}/result", headers=headers
        )
        source_response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}/source", headers=headers
        )

    assert status_response.status_code == 404
    assert status_response.json()["error_code"] == "JOB_NOT_FOUND"
    assert result_response.status_code == 404
    assert result_response.json()["error_code"] == "JOB_NOT_FOUND"
    assert source_response.status_code == 404
    assert source_response.json()["error_code"] == "JOB_NOT_FOUND"


def test_local_status_returns_404_for_unknown_job(settings, adapter):
    with local_client(settings, adapter) as client:
        response = client.get(
            f"/api/v1/local/jobs/{uuid4()}", headers={"X-Local-Pilot": "1"}
        )

    assert response.status_code == 404
    assert response.json()["error_code"] == "JOB_NOT_FOUND"


def test_local_result_returns_409_before_terminal_state(
    settings, adapter, synthetic_pdf
):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        job_id = UUID(created["job_id"])
        service = client.app.state.job_service
        service.repository.prepare_retry(job_id, JobStatus.COMPLETADO)
        service.repository.transition(
            job_id,
            JobStatus.RECIBIDO,
            JobStatus.PROCESANDO,
            increment_attempt=True,
        )
        response = client.get(
            f"/api/v1/local/jobs/{job_id}/result",
            headers={"X-Local-Pilot": "1"},
        )

    assert response.status_code == 409
    assert response.json()["error_code"] == "RESULT_NOT_READY"


def test_local_result_returns_404_when_missing_or_expired(
    settings, adapter, synthetic_pdf
):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        job_id = UUID(created["job_id"])
        service = client.app.state.job_service
        service.storage.result_path(job_id).unlink()
        missing = client.get(
            f"/api/v1/local/jobs/{job_id}/result",
            headers={"X-Local-Pilot": "1"},
        )

        service.storage.result_path(job_id).parent.mkdir(parents=True, exist_ok=True)
        service.storage.result_path(job_id).write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
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
        expired = client.get(
            f"/api/v1/local/jobs/{job_id}/result",
            headers={"X-Local-Pilot": "1"},
        )

    assert missing.status_code == 404
    assert missing.json()["error_code"] == "RESULT_NOT_FOUND"
    assert expired.status_code == 404
    assert expired.json()["error_code"] == "RESULT_NOT_FOUND"


def test_local_read_error_does_not_leak_internal_details(
    settings, adapter, synthetic_pdf, monkeypatch
):
    with local_client(settings, adapter) as client:
        created = create_local_job(client, synthetic_pdf).json()
        secret = "/private/customer/acme/result.xlsx HMAC=secret"
        monkeypatch.setattr(
            client.app.state.job_service.storage,
            "result_path",
            lambda *_args: (_ for _ in ()).throw(OSError(secret)),
        )
        response = client.get(
            f"/api/v1/local/jobs/{created['job_id']}",
            headers={"X-Local-Pilot": "1"},
        )

    assert response.status_code == 500
    assert response.json()["error_code"] == "STORAGE_ERROR"
    assert secret not in response.text
    assert set(response.json()) == {"request_id", "error_code", "message"}
