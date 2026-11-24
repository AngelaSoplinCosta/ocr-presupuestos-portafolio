from datetime import UTC, datetime
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.adapters.motor_presupuestos import MotorPresupuestosAdapter
from backend.app.domain.models import EngineOutcome, ReviewObservation, ReviewSuggestion
from backend.app.infrastructure.database import Base, build_engine
from backend.app.main import create_app


class ReviewAdapter:
    def __init__(self, general_only: bool = False, manual_only: bool = False, row_only: bool = False):
        self.general_only = general_only
        self.manual_only = manual_only
        self.row_only = row_only

    def process(self, *, result_path, job_id, **_kwargs):
        result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
        observations = () if self.general_only else (
            ReviewObservation(
                id=str(uuid4()), state="PENDING", kind="row" if self.row_only else "code", page=2,
                row_order=4, row_type="partida", row_label="Excavación",
                field="row" if self.row_only else "code", extracted_value="" if self.row_only else ("" if self.manual_only else "A.O1"),
                suggestion=None if self.manual_only or self.row_only else ReviewSuggestion("A.01", "MEDIA"),
                reason="Código ambiguo", evidence=("Confirmar contra el PDF",),
                allowed_actions=("keep_original", "set_value") if self.row_only else (("set_value",) if self.manual_only else ("accept_suggestion", "keep_original", "set_value")),
                requires_decision=True,
            ),
        )
        return EngineOutcome(
            requires_review=True,
            observations=observations,
            export_snapshot={"rows": [{"row_key": "2:4", "values": {"item": "A.O1", "description": "Excavación", "unit": "m3", "quantity": "12", "unit_price": "10.00", "amount": "120.00"}}]},
        )


class StructuredRowAdapter:
    def __init__(self, *, raw_line: str = "701.4 MATERIAL SINTETICO DE PRUEBA kg 24,680.25 12.40 306,035.10", candidate: bool = True, rows: int = 1, values: dict[str, str] | None = None):
        self.raw_line = raw_line
        self.candidate = candidate
        self.rows = rows
        self.values = values or {}

    def process(self, *, result_path, job_id, **_kwargs):
        result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
        observations = tuple(
            ReviewObservation(
                id=str(uuid4()), state="PENDING", kind="row", page=2, row_order=index,
                row_type="partida", row_label="Insumo ficticio", field="row", extracted_value=self.raw_line,
                suggestion=None, reason="candidato: 701.A" if self.candidate else "Fila OCR unida",
                evidence=("Línea OCR original",), allowed_actions=("keep_original", "set_value"),
                requires_decision=True,
            )
            for index in range(1, self.rows + 1)
        )
        snapshot_rows = [
            {"row_key": f"2:{index}", "values": {"item": "701.A", "description": "MATERIAL SINTETICO DE PRUEBA", "unit": "kg", "quantity": "24680.25", "unit_price": "12.40", "amount": "306035.10", **self.values}}
            for index in range(1, self.rows + 1)
        ]
        return EngineOutcome(requires_review=True, observations=observations, export_snapshot={"rows": snapshot_rows})


def _client(settings, adapter):
    enabled = settings.model_copy(update={"local_mode_enabled": True})
    engine = build_engine(enabled.database_url)
    Base.metadata.create_all(engine)
    return TestClient(create_app(settings=enabled, engine=engine, adapter=adapter), client=("127.0.0.1", 8000))


def _create(client, synthetic_pdf):
    return client.post("/api/v1/local/jobs", headers={"X-Local-Pilot": "1"}, data={"document_type": "budget"}, files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")}).json()


def _make_legacy_decision(client, job_id, observation_id, *, field=None):
    storage = client.app.state.job_service.storage
    payload = json.loads(storage.review_path(UUID(job_id)).read_text(encoding="utf-8"))
    decision = payload["decisions"][observation_id]
    decision.pop("target_scope", None)
    if field is not None:
        decision["field"] = field
    storage.store_review(UUID(job_id), json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def test_local_review_is_sanitized_and_no_store(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter()) as client:
        job = _create(client, synthetic_pdf)
        response = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers={"X-Local-Pilot": "1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["pending_decision_count"] == 1
    assert payload["observations"][0]["allowed_actions"] == ["accept_suggestion", "keep_original", "set_value"]
    assert payload["observations"][0]["row"]["label"] == "Excavación"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert not {"path", "hash", "hmac", "secret"}.intersection(str(payload).casefold().split())


def test_motor_observation_actions_depend_on_available_values():
    reviews = [
        SimpleNamespace(original_value="A.O1", suggested_value="A.01", observed_field="code"),
        SimpleNamespace(original_value="A.O1", suggested_value="", observed_field="code"),
        SimpleNamespace(original_value="", suggested_value="A.01", observed_field="code"),
        SimpleNamespace(original_value="", suggested_value="", observed_field="code"),
    ]

    observations = MotorPresupuestosAdapter._public_observations(UUID(int=0), reviews, object())

    assert [item.allowed_actions for item in observations] == [
        ("accept_suggestion", "keep_original", "set_value"),
        ("keep_original", "set_value"),
        ("accept_suggestion", "set_value"),
        ("set_value",),
    ]
    assert all(item.requires_decision for item in observations)


def test_manual_only_review_rejects_automatic_actions_and_accepts_value(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter(manual_only=True)) as client:
        job = _create(client, synthetic_pdf)
        review_url = f"/api/v1/local/jobs/{job['job_id']}/review"
        decisions_url = f"/api/v1/local/jobs/{job['job_id']}/review/decisions"
        headers = {"X-Local-Pilot": "1"}
        review = client.get(review_url, headers=headers).json()
        observation = review["observations"][0]

        assert observation["allowed_actions"] == ["set_value"]
        for action in ("keep_original", "accept_suggestion"):
            rejected = client.put(decisions_url, headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": action}]})
            assert rejected.status_code == 422

        saved = client.put(decisions_url, headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "set_value", "value": "A.01"}]})
        assert saved.status_code == 200
        assert saved.json()["pending_decision_count"] == 0
        assert client.get(f"/api/v1/local/jobs/{job['job_id']}/export", headers=headers).json()["pending_decision_count"] == 0


def test_review_table_projects_resolved_cell_decision(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter()) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        table_url = f"/api/v1/local/jobs/{job['job_id']}/review/table"
        pending = client.get(f"{table_url}?filter=pending", headers=headers)
        assert pending.status_code == 200
        payload = pending.json()
        assert [column["key"] for column in payload["columns"]] == ["item", "description", "unit", "quantity", "unit_price", "amount"]
        assert payload["rows"][0]["cells"]["description"] == "Excavación"
        observation = payload["rows"][0]["observations"][0]
        assert observation["target"] == {"scope": "cell", "column_key": "item"}
        assert observation["state"] == "PENDING"
        saved = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": payload["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "accept_suggestion"}]})
        assert saved.status_code == 200
        resolved = client.get(f"{table_url}?filter=resolved", headers=headers).json()
        projected = resolved["rows"][0]["observations"][0]
        assert projected["state"] == "RESOLVED"
        assert projected["decision"]["action"] == "accept_suggestion"
        assert projected["resolved_value"] == "A.01"


def test_new_row_decision_preserves_simple_export_values(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter(row_only=True)) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        review_url = f"/api/v1/local/jobs/{job['job_id']}/review"
        review = client.get(review_url, headers=headers).json()
        observation = review["observations"][0]
        assert observation["field"] == "row"
        rejected = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "keep_original"}]})
        assert rejected.status_code == 422
        saved = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "set_value", "value": "Evidencia de fila"}]})
        assert saved.status_code == 200
        config_url = f"/api/v1/local/jobs/{job['job_id']}/export"
        config = client.get(config_url, headers=headers).json()
        assert client.put(f"{config_url}/config", headers=headers, json={"export_revision": config["export_revision"], "columns": config["columns"]}).status_code == 200
        assert client.post(config_url, headers=headers).status_code == 200
        workbook = load_workbook(BytesIO(client.get(f"{config_url}/result", headers=headers).content))
        assert workbook["Partidas"][2][1].value == "Excavación"


def test_legacy_row_decision_without_target_scope_preserves_simple_export_values(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter(row_only=True)) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        review = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers=headers).json()
        observation = review["observations"][0]
        assert client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "set_value", "value": "Evidencia de fila"}]}).status_code == 200
        _make_legacy_decision(client, job["job_id"], observation["id"], field="description")
        config_url = f"/api/v1/local/jobs/{job['job_id']}/export"
        config = client.get(config_url, headers=headers).json()
        assert client.put(f"{config_url}/config", headers=headers, json={"export_revision": config["export_revision"], "columns": config["columns"]}).status_code == 200
        assert client.post(config_url, headers=headers).status_code == 200
        workbook = load_workbook(BytesIO(client.get(f"{config_url}/result", headers=headers).content))
        assert workbook["Partidas"][2][1].value == "Excavación"


def test_legacy_cell_decision_without_target_scope_updates_simple_export(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter()) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        review = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers=headers).json()
        observation = review["observations"][0]
        assert client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": observation["id"], "action": "accept_suggestion"}]}).status_code == 200
        _make_legacy_decision(client, job["job_id"], observation["id"])
        config_url = f"/api/v1/local/jobs/{job['job_id']}/export"
        config = client.get(config_url, headers=headers).json()
        assert client.put(f"{config_url}/config", headers=headers, json={"export_revision": config["export_revision"], "columns": config["columns"]}).status_code == 200
        assert client.post(config_url, headers=headers).status_code == 200
        workbook = load_workbook(BytesIO(client.get(f"{config_url}/result", headers=headers).content))
        assert [cell.value for cell in workbook["Partidas"][2][:2]] == ["A.01", "Excavación"]


def test_local_review_allows_completed_jobs_and_export_config(settings, synthetic_pdf, adapter):
    with _client(settings, adapter) as client:
        job = _create(client, synthetic_pdf)
        response = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers={"X-Local-Pilot": "1"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETADO"
    export = client.get(f"/api/v1/local/jobs/{job['job_id']}/export", headers={"X-Local-Pilot": "1"})
    assert export.status_code == 200
    assert export.json()["pending_decision_count"] == 0


def test_decision_invalidates_simple_export_until_regenerated(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter()) as client:
        job = _create(client, synthetic_pdf)
        review = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers={"X-Local-Pilot": "1"}).json()
        config = client.get(f"/api/v1/local/jobs/{job['job_id']}/export", headers={"X-Local-Pilot": "1"}).json()
        decision = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers={"X-Local-Pilot": "1"}, json={"review_revision": review["review_revision"], "decisions": [{"observation_id": review["observations"][0]["id"], "action": "accept_suggestion"}]})
        assert decision.status_code == 200
        saved = client.put(f"/api/v1/local/jobs/{job['job_id']}/export/config", headers={"X-Local-Pilot": "1"}, json={"export_revision": config["export_revision"], "columns": config["columns"]})
        assert saved.status_code == 200
        assert client.post(f"/api/v1/local/jobs/{job['job_id']}/export", headers={"X-Local-Pilot": "1"}).status_code == 200
        result = f"/api/v1/local/jobs/{job['job_id']}/export/result"
        generated = client.get(result, headers={"X-Local-Pilot": "1"})
        assert generated.status_code == 200
        workbook = load_workbook(BytesIO(generated.content))
        assert [cell.value for cell in workbook["Partidas"][2][:2]] == ["A.01", "Excavación"]

        changed = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers={"X-Local-Pilot": "1"}, json={"review_revision": decision.json()["review_revision"], "decisions": [{"observation_id": review["observations"][0]["id"], "action": "keep_original"}]})
        assert changed.status_code == 200
        stale = client.get(f"/api/v1/local/jobs/{job['job_id']}/export", headers={"X-Local-Pilot": "1"})
        assert stale.json()["simple_result_available"] is False
        assert client.get(result, headers={"X-Local-Pilot": "1"}).status_code == 409

        regenerated = client.put(f"/api/v1/local/jobs/{job['job_id']}/export/config", headers={"X-Local-Pilot": "1"}, json={"export_revision": saved.json()["export_revision"], "columns": saved.json()["columns"]})
        assert regenerated.status_code == 200
        assert client.post(f"/api/v1/local/jobs/{job['job_id']}/export", headers={"X-Local-Pilot": "1"}).status_code == 200
        assert client.get(result, headers={"X-Local-Pilot": "1"}).status_code == 200


def test_structured_row_confirms_only_safe_fields_and_projects_them(settings, synthetic_pdf):
    with _client(settings, StructuredRowAdapter()) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        table_url = f"/api/v1/local/jobs/{job['job_id']}/review/table"
        table = client.get(table_url, headers=headers).json()
        structured = table["rows"][0]["structured_review"]
        observation_id = structured["observation_id"]
        fields = {field["key"]: field for field in structured["fields"]}

        assert structured["raw_ocr_line"].startswith("701.4")
        assert fields["item"]["suggestion"]["value"] == "701.A"
        assert fields["item"]["differs_from_ocr"] is True
        assert fields["item"]["can_confirm_provisional"] is False
        assert sum(field["can_confirm_provisional"] for field in fields.values()) == 5

        confirmed = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "confirm_provisional_row"}]})
        assert confirmed.status_code == 200
        assert confirmed.json()["pending_decision_count"] == 1
        storage = client.app.state.job_service.storage
        persisted = json.loads(storage.review_path(UUID(job["job_id"])).read_text(encoding="utf-8"))
        assert set(persisted["structured_row_decisions"][observation_id]) == {"description", "unit", "quantity", "unit_price", "amount"}
        assert observation_id not in persisted["decisions"]

        stale = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "accept_suggestion", "field": "item"}]})
        assert stale.status_code == 409
        assert json.loads(storage.review_path(UUID(job["job_id"])).read_text(encoding="utf-8")) == persisted

        accepted = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": confirmed.json()["review_revision"], "decisions": [{"observation_id": observation_id, "action": "accept_suggestion", "field": "item"}]})
        assert accepted.status_code == 200
        assert accepted.json()["pending_decision_count"] == 0
        reloaded = client.get(f"{table_url}?filter=resolved", headers=headers).json()["rows"][0]["structured_review"]
        assert reloaded["confirmed_field_count"] == 6
        assert reloaded["fields"][0]["decision"] == {"action": "accept_suggestion", "value": "701.A"}

        export_url = f"/api/v1/local/jobs/{job['job_id']}/export"
        config = client.get(export_url, headers=headers).json()
        assert client.put(f"{export_url}/config", headers=headers, json={"export_revision": config["export_revision"], "columns": config["columns"]}).status_code == 200
        assert client.post(export_url, headers=headers).status_code == 200
        workbook = load_workbook(BytesIO(client.get(f"{export_url}/result", headers=headers).content))
        assert [cell.value for cell in workbook["Partidas"][2][:6]] == ["701.A", "MATERIAL SINTETICO DE PRUEBA", "kg", 24680.25, 12.40, 306035.1]


def test_structured_row_without_separable_ocr_requires_manual_value(settings, synthetic_pdf):
    with _client(settings, StructuredRowAdapter(raw_line="Texto OCR unido")) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        table = client.get(f"/api/v1/local/jobs/{job['job_id']}/review/table", headers=headers).json()
        structured = table["rows"][0]["structured_review"]
        observation_id = structured["observation_id"]
        assert all(field["manual_only"] for field in structured["fields"])
        assert client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "confirm_provisional_row"}]}).status_code == 422
        assert client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "keep_provisional", "field": "unit"}]}).status_code == 422
        assert client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "set_value", "field": "quantity", "value": "no numérico"}]}).status_code == 422
        manual = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": observation_id, "action": "set_value", "field": "quantity", "value": "12.50"}]})
        assert manual.status_code == 200
        assert manual.json()["pending_decision_count"] == 5


def test_structured_high_precision_values_are_not_auto_confirmed_when_distinct(settings, synthetic_pdf):
    raw_line = "701.A MATERIAL SINTETICO DE PRUEBA kg 1234567890123.01 12.40 306,035.10"
    with _client(settings, StructuredRowAdapter(raw_line=raw_line, candidate=False, values={"item": "701.A", "quantity": "1234567890123.02"})) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        table = client.get(f"/api/v1/local/jobs/{job['job_id']}/review/table", headers=headers).json()
        structured = table["rows"][0]["structured_review"]
        quantity = next(field for field in structured["fields"] if field["key"] == "quantity")

        assert quantity["differs_from_ocr"] is True
        assert quantity["can_confirm_provisional"] is False
        saved = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": table["review_revision"], "decisions": [{"observation_id": structured["observation_id"], "action": "confirm_provisional_row"}]})
        assert saved.status_code == 200
        persisted = json.loads(client.app.state.job_service.storage.review_path(UUID(job["job_id"])).read_text(encoding="utf-8"))
        assert "quantity" not in persisted["structured_row_decisions"][structured["observation_id"]]


def test_structured_confirmation_rejects_effective_expansion_over_fifty(settings, synthetic_pdf):
    with _client(settings, StructuredRowAdapter(candidate=False, rows=11)) as client:
        job = _create(client, synthetic_pdf)
        headers = {"X-Local-Pilot": "1"}
        review = client.get(f"/api/v1/local/jobs/{job['job_id']}/review", headers=headers).json()
        decisions = [{"observation_id": observation["id"], "action": "confirm_provisional_row"} for observation in review["observations"]]
        assert len(decisions) * 5 > 50
        rejected = client.put(f"/api/v1/local/jobs/{job['job_id']}/review/decisions", headers=headers, json={"review_revision": review["review_revision"], "decisions": decisions})
        assert rejected.status_code == 422
        payload = json.loads(client.app.state.job_service.storage.review_path(UUID(job["job_id"])).read_text(encoding="utf-8"))
        assert payload["review_revision"] == 0
        assert "structured_row_decisions" not in payload


def test_retention_removes_review_snapshot(settings, synthetic_pdf):
    with _client(settings, ReviewAdapter()) as client:
        job = _create(client, synthetic_pdf)
        storage = client.app.state.job_service.storage
        assert storage.review_path(uuid4()).name == "review.json"
        assert storage.review_path(UUID(job["job_id"])).exists()
        client.app.state.retention_service.cleanup_expired_results(
            now=datetime.now(UTC).replace(year=2099)
        )
        assert not storage.review_path(UUID(job["job_id"])).exists()
