def test_create_job_processes_synchronously(
    client, auth_headers, synthetic_pdf, adapter
):
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETADO"
    assert response.json()["result_available"] is True
    assert adapter.calls == 1


def test_tenant_is_not_accepted_from_client(client, auth_headers, synthetic_pdf):
    response = client.post(
        "/v1/jobs?tenant_id=tenant-b",
        headers={**auth_headers, "X-Tenant-Id": "tenant-b"},
        data={"tenant_id": "tenant-b"},
        files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 200


def test_missing_or_invalid_token_is_generic(client, auth_headers, synthetic_pdf):
    headers = {"X-Drive-File-Id": auth_headers["X-Drive-File-Id"]}
    response = client.post(
        "/v1/jobs",
        headers=headers,
        files={"file": ("presupuesto.pdf", synthetic_pdf, "application/pdf")},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTHENTICATION_FAILED"
    assert set(response.json()) == {"request_id", "error_code", "message"}
