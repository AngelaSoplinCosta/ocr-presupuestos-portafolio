def test_cross_tenant_status_and_result_are_hidden(
    client, auth_headers, second_api_token, synthetic_pdf
):
    created = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
    ).json()
    other_headers = {"X-API-Key": second_api_token}

    status_response = client.get(f"/v1/jobs/{created['job_id']}", headers=other_headers)
    result_response = client.get(
        f"/v1/jobs/{created['job_id']}/result", headers=other_headers
    )
    assert status_response.status_code == 404
    assert result_response.status_code == 404
    assert status_response.json()["error_code"] == "JOB_NOT_FOUND"
