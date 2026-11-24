from datetime import UTC, datetime
from dataclasses import replace
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

from fastapi import UploadFile

from ..config import Settings
from ..domain.enums import JobStatus
from ..domain.errors import (
    InvalidUpload,
    JobNotFound,
    ReadinessFailed,
    ResultNotReady,
    StaleTransition,
    StorageCleanupFailed,
)
from .simple_export import write_simple_export
from ..domain.models import JobView, TenantPrincipal
from ..infrastructure.repositories.jobs import SqlAlchemyJobRepository
from ..infrastructure.storage.base import JobStorage
from ..security import protect_drive_file_id
from .process_job import JobProcessor
from .simple_export import standard_descriptors


class JobService:
    RECOVERABLE_ERRORS = {"PROCESS_INTERRUPTED", "RESULT_EXPIRED"}
    STRUCTURED_FIELDS = ("item", "description", "unit", "quantity", "unit_price", "amount")
    STRUCTURED_LABELS = {
        "item": "Ítem", "description": "Descripción", "unit": "Unidad",
        "quantity": "Metrado", "unit_price": "Precio unitario", "amount": "Parcial",
    }
    STRUCTURED_NUMERIC_FIELDS = {"quantity", "unit_price", "amount"}
    _RAW_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)$")
    _LEGACY_ITEM_CANDIDATE = re.compile(r"(?:^|[;|\n])\s*candidato\s*:\s*([^;|\n]+?)\s*$", re.IGNORECASE)
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SqlAlchemyJobRepository,
        storage: JobStorage,
        processor: JobProcessor,
    ):
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.processor = processor

    def create_job(
        self,
        *,
        principal: TenantPrincipal,
        drive_file_id: str,
        drive_revision: str | None,
        upload: UploadFile,
        local_identity: bool = False,
    ) -> JobView:
        self.preflight()
        provisional_id = uuid4()
        try:
            stored = self.storage.store_upload(provisional_id, upload)
            identity = stored.content_sha256 if local_identity else drive_file_id
            drive_hmac = protect_drive_file_id(
                principal.tenant_id,
                identity,
                self.settings.require_hmac_secret(),
            )
            job, created = self.repository.create_or_get(
                job_id=provisional_id,
                tenant_id=principal.tenant_id,
                drive_file_hmac=drive_hmac,
                content_sha256=stored.content_sha256,
                drive_revision=drive_revision,
                safe_original_name=stored.safe_original_name,
            )
        except Exception:
            self._remove_or_raise(provisional_id)
            raise
        if not created:
            if job.status == JobStatus.RECIBIDO:
                try:
                    self.storage.replace_job_upload(provisional_id, job.id)
                except Exception:
                    self._remove_or_raise(provisional_id)
                    raise
                return self.processor.process(job.id)
            if self._can_retry(job):
                try:
                    self.storage.replace_job_upload(provisional_id, job.id)
                    self.repository.prepare_retry(job.id, job.status)
                except Exception:
                    self._remove_or_raise(job.id)
                    raise
                return self.processor.process(job.id)
            self._remove_or_raise(provisional_id)
            return self._with_result_state(job)
        return self.processor.process(job.id)

    def preflight(self) -> None:
        self.settings.validate_runtime()
        self.storage.validate_configuration()
        try:
            schema_ready = self.repository.schema_is_current()
        except Exception as exc:
            raise ReadinessFailed("DATABASE_NOT_READY") from exc
        if not schema_ready:
            raise ReadinessFailed("DATABASE_SCHEMA_NOT_READY")
        try:
            storage_ready = self.storage.check_writable()
        except Exception as exc:
            raise ReadinessFailed("JOB_STORAGE_NOT_READY") from exc
        if not storage_ready:
            raise ReadinessFailed("JOB_STORAGE_NOT_READY")
        validate_adapter = getattr(self.processor.adapter, "validate_available", None)
        if validate_adapter is not None:
            try:
                validate_adapter()
            except Exception as exc:
                raise ReadinessFailed("MOTOR_ADAPTER_NOT_READY") from exc

    def recover_interrupted_jobs(self) -> int:
        interrupted = self.repository.recover_interrupted_processing()
        cleanup_failed = False
        for job_id in interrupted:
            try:
                self.storage.remove_job(job_id)
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            raise StorageCleanupFailed("INTERRUPTED_JOB_CLEANUP_FAILED")
        return len(interrupted)

    def _remove_or_raise(self, job_id: UUID) -> None:
        try:
            self.storage.remove_job(job_id)
        except Exception as exc:
            raise StorageCleanupFailed("UPLOAD_CLEANUP_FAILED") from exc

    def _can_retry(self, job: JobView) -> bool:
        if job.status == JobStatus.ERROR:
            return job.error_code in self.RECOVERABLE_ERRORS
        if job.status in {JobStatus.COMPLETADO, JobStatus.REVISAR}:
            return not self.result_available(job)
        return False

    def _with_result_state(self, job: JobView) -> JobView:
        if (
            job.status in {JobStatus.COMPLETADO, JobStatus.REVISAR}
            and not self.result_available(job)
        ):
            return replace(job, error_code="RESULT_EXPIRED")
        return job

    def get_job(self, principal: TenantPrincipal, job_id: UUID) -> JobView:
        job = self.repository.get_for_tenant(job_id, principal.tenant_id)
        if job is None:
            raise JobNotFound("JOB_NOT_FOUND")
        return self._with_result_state(job)

    def result_available(self, job: JobView) -> bool:
        return (
            job.status in {JobStatus.COMPLETADO, JobStatus.REVISAR}
            and job.result_expires_at is not None
            and job.result_expires_at > datetime.now(UTC)
            and self.storage.result_path(job.id).is_file()
        )

    def result_path(self, principal: TenantPrincipal, job_id: UUID) -> Path:
        job = self.get_job(principal, job_id)
        if job.status not in {JobStatus.COMPLETADO, JobStatus.REVISAR}:
            raise ResultNotReady("RESULT_NOT_READY")
        if not self.result_available(job):
            raise JobNotFound("RESULT_NOT_FOUND")
        result = self.storage.result_path(job_id)
        return result

    def source_path(self, principal: TenantPrincipal, job_id: UUID) -> Path:
        job = self.get_job(principal, job_id)
        if job.status not in {JobStatus.COMPLETADO, JobStatus.REVISAR}:
            raise ResultNotReady("RESULT_NOT_READY")
        if not self.result_available(job):
            raise JobNotFound("RESULT_NOT_FOUND")
        source = self.storage.input_path(job_id)
        if not source.is_file():
            raise JobNotFound("RESULT_NOT_FOUND")
        return source

    def _load_json(self, path: Path, code: str) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise JobNotFound(code) from exc
        if not isinstance(payload, dict):
            raise JobNotFound(code)
        return payload

    def _review(self, principal: TenantPrincipal, job_id: UUID) -> tuple[JobView, dict[str, object]]:
        job = self.get_job(principal, job_id)
        if job.status not in {JobStatus.REVISAR, JobStatus.COMPLETADO}:
            raise ResultNotReady("RESULT_NOT_READY")
        if not self.result_available(job):
            raise JobNotFound(
                "RESULT_EXPIRED" if job.error_code == "RESULT_EXPIRED" else "RESULT_NOT_FOUND"
            )
        payload = self._load_json(self.storage.review_path(job_id), "REVIEW_NOT_FOUND")
        if not isinstance(payload, dict) or payload.get("job_id") != str(job_id):
            raise JobNotFound("REVIEW_NOT_FOUND")
        return job, payload

    @staticmethod
    def _row_key(observation: dict[str, object]) -> str:
        row = observation.get("row") if isinstance(observation.get("row"), dict) else {}
        return f"{observation.get('page') or 0}:{row.get('order') or 0}"

    @staticmethod
    def _snapshot_rows(export: dict[str, object]) -> dict[str, dict[str, str]]:
        snapshot = export.get("snapshot", {}) if isinstance(export, dict) else {}
        source_rows = snapshot.get("rows", []) if isinstance(snapshot, dict) else []
        rows: dict[str, dict[str, str]] = {}
        for source in source_rows:
            if not isinstance(source, dict) or not isinstance(source.get("row_key"), str):
                continue
            values = source.get("values") if isinstance(source.get("values"), dict) else {}
            rows[source["row_key"]] = {key: value for key, value in values.items() if isinstance(key, str) and isinstance(value, str)}
        return rows

    @classmethod
    def _canonical_structured_value(cls, field: str, value: str) -> str | Decimal | None:
        compact = " ".join(value.split())
        if not compact:
            return None
        if field not in cls.STRUCTURED_NUMERIC_FIELDS:
            return compact.casefold()
        if not cls._RAW_NUMBER.fullmatch(compact):
            return None
        if "," in compact and "." in compact:
            compact = compact.replace(",", "")
        elif "," in compact:
            compact = compact.replace(",", ".")
        try:
            return Decimal(compact)
        except InvalidOperation:
            return None

    @classmethod
    def _raw_structured_values(cls, raw_line: str, provisional: dict[str, str]) -> dict[str, str]:
        tokens = raw_line.split()
        if len(tokens) < 6 or not all(cls._RAW_NUMBER.fullmatch(token) for token in tokens[-3:]):
            return {}
        unit = provisional.get("unit", "").strip()
        if not unit:
            return {}
        unit_positions = [index for index, token in enumerate(tokens[:-3]) if token.casefold() == unit.casefold()]
        if len(unit_positions) != 1 or unit_positions[0] < 2:
            return {}
        unit_index = unit_positions[0]
        return {
            "item": tokens[0], "description": " ".join(tokens[1:unit_index]), "unit": tokens[unit_index],
            "quantity": tokens[-3], "unit_price": tokens[-2], "amount": tokens[-1],
        }

    @classmethod
    def _structured_review(cls, observation: dict[str, object], values: dict[str, str], decisions: object, legacy_decision: object) -> dict[str, object] | None:
        if observation.get("field") != "row" or not observation.get("requires_decision"):
            return None
        if not all(field in values for field in cls.STRUCTURED_FIELDS):
            return None
        raw_line = observation.get("extracted_value")
        if not isinstance(raw_line, str) or not raw_line.strip():
            return None
        raw_values = cls._raw_structured_values(raw_line, values)
        reason = observation.get("reason") if isinstance(observation.get("reason"), str) else ""
        legacy_candidate = cls._LEGACY_ITEM_CANDIDATE.search(reason)
        candidate = legacy_candidate.group(1).strip() if legacy_candidate else ""
        stored_fields = decisions if isinstance(decisions, dict) else {}
        fields: list[dict[str, object]] = []
        for field in cls.STRUCTURED_FIELDS:
            raw_value = raw_values.get(field)
            provisional_value = values[field]
            suggestion = {"value": candidate, "confidence": "LEGACY"} if field == "item" and candidate else None
            saved = stored_fields.get(field)
            decision = {"action": saved.get("action"), "value": saved.get("value")} if isinstance(saved, dict) and isinstance(saved.get("action"), str) and isinstance(saved.get("value"), str) else None
            comparable = raw_value is not None and cls._canonical_structured_value(field, raw_value) is not None and cls._canonical_structured_value(field, provisional_value) is not None
            differs = cls._canonical_structured_value(field, raw_value) != cls._canonical_structured_value(field, provisional_value) if comparable and raw_value is not None else None
            fields.append({
                "key": field, "label": cls.STRUCTURED_LABELS[field], "ocr_value": raw_value,
                "provisional_value": provisional_value, "suggestion": suggestion,
                "differs_from_ocr": differs, "state": "RESOLVED" if decision else "PENDING",
                "decision": decision, "can_confirm_provisional": not decision and comparable and differs is False and suggestion is None,
                "manual_only": raw_value is None,
            })
        confirmed = sum(1 for field in fields if field["state"] == "RESOLVED")
        legacy = {"action": legacy_decision.get("action"), "value": legacy_decision.get("value")} if isinstance(legacy_decision, dict) and isinstance(legacy_decision.get("action"), str) and isinstance(legacy_decision.get("value"), str) else None
        return {
            "observation_id": observation["id"], "raw_ocr_line": raw_line, "fields": fields,
            "confirmed_field_count": confirmed, "pending_field_count": len(fields) - confirmed,
            "legacy_row_decision": legacy,
        }

    @classmethod
    def _structured_reviews(cls, review: dict[str, object], export: dict[str, object]) -> dict[str, dict[str, object]]:
        stored = review.get("structured_row_decisions", {})
        legacy = review.get("decisions", {})
        observations = review.get("observations", [])
        rows = cls._snapshot_rows(export)
        if not isinstance(observations, list):
            return {}
        result: dict[str, dict[str, object]] = {}
        for observation in observations:
            if not isinstance(observation, dict) or not isinstance(observation.get("id"), str):
                continue
            projection = cls._structured_review(
                observation, rows.get(cls._row_key(observation), {}),
                stored.get(observation["id"]) if isinstance(stored, dict) else None,
                legacy.get(observation["id"]) if isinstance(legacy, dict) else None,
            )
            if projection is not None:
                result[observation["id"]] = projection
        return result

    @classmethod
    def _decision_counts(cls, review: dict[str, object], export: dict[str, object]) -> tuple[int, int]:
        observations = review.get("observations", [])
        decisions = review.get("decisions", {})
        if not isinstance(observations, list) or not isinstance(decisions, dict):
            raise JobNotFound("REVIEW_NOT_FOUND")
        structured = cls._structured_reviews(review, export)
        required = pending = 0
        for observation in observations:
            if not isinstance(observation, dict) or not observation.get("requires_decision"):
                continue
            projection = structured.get(observation.get("id")) if isinstance(observation.get("id"), str) else None
            if projection is not None:
                field_count = len(projection["fields"])
                required += field_count
                pending += int(projection["pending_field_count"])
            else:
                required += 1
                pending += int(observation.get("id") not in decisions)
        return required, pending

    def review_payload(self, principal: TenantPrincipal, job_id: UUID, *, offset: int = 0, limit: int = 25) -> dict[str, object]:
        _job, payload = self._review(principal, job_id)
        observations = payload.get("observations", [])
        if not isinstance(observations, list):
            raise JobNotFound("REVIEW_NOT_FOUND")
        export = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        required, pending = self._decision_counts(payload, export)
        return {
            "schema_version": "2", "job_id": str(job_id), "status": payload.get("status"),
            "review_revision": payload.get("review_revision", 0), "total_count": len(observations),
            "requires_decision_count": required, "pending_decision_count": pending,
            "offset": offset, "limit": limit, "result_expires_at": payload.get("result_expires_at"),
            "observations": observations[offset:offset + limit],
        }

    @staticmethod
    def _columns(payload: dict[str, object]) -> list[dict[str, object]]:
        columns = payload.get("columns")
        if not isinstance(columns, list):
            return standard_descriptors()
        normalized: list[dict[str, object]] = []
        for index, item in enumerate(columns):
            if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                return standard_descriptors()
            normalized.append({
                "key": item["key"], "label": item.get("label") or item["key"],
                "data_type": item.get("data_type") if item.get("data_type") in {"text", "decimal", "currency"} else "text",
                "source_header": item.get("source_header") if isinstance(item.get("source_header"), str) else None,
                "included": bool(item.get("included", True)), "position": item.get("position", index),
                "origin": item.get("origin") if item.get("origin") in {"standard", "candidate"} else "standard",
            })
        return normalized

    def review_table_payload(self, principal: TenantPrincipal, job_id: UUID, *, offset: int, limit: int, filter_name: str) -> dict[str, object]:
        _job, review = self._review(principal, job_id)
        export = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        snapshot = export.get("snapshot", {}) if isinstance(export, dict) else {}
        rows = snapshot.get("rows", []) if isinstance(snapshot, dict) else []
        decisions = review.get("decisions", {}) if isinstance(review.get("decisions"), dict) else {}
        observations = review.get("observations", []) if isinstance(review.get("observations"), list) else []
        structured = self._structured_reviews(review, export)
        by_row: dict[str, list[dict[str, object]]] = {}
        field_map = {"code": "item", "unit": "unit", "quantity": "quantity", "unit_price": "unit_price", "amount": "amount"}
        for item in observations:
            if not isinstance(item, dict):
                continue
            row_key = self._row_key(item)
            saved = decisions.get(item.get("id")) if isinstance(item.get("id"), str) else None
            row_review = structured.get(item.get("id")) if isinstance(item.get("id"), str) else None
            resolved = int(row_review["pending_field_count"]) == 0 if row_review is not None else isinstance(saved, dict)
            target = {"scope": "row"} if item.get("field") == "row" else {"scope": "cell", "column_key": field_map.get(str(item.get("field")), "description")}
            projected = dict(item)
            projected.update({
                "state": "RESOLVED" if resolved else "PENDING",
                "target": target, "decision": {"action": saved.get("action"), "value": saved.get("value")} if isinstance(saved, dict) else None,
                "resolved_value": saved.get("value") if isinstance(saved, dict) else None,
            })
            if item.get("requires_decision"):
                by_row.setdefault(row_key, []).append(projected)
        rendered: list[dict[str, object]] = []
        for source in rows:
            if not isinstance(source, dict) or not isinstance(source.get("row_key"), str):
                continue
            row_observations = by_row.get(source["row_key"], [])
            row_structured = next((structured[item["id"]] for item in row_observations if isinstance(item.get("id"), str) and item.get("id") in structured), None)
            has_pending = any(item["state"] == "PENDING" for item in row_observations)
            has_resolved = any(item["state"] == "RESOLVED" for item in row_observations)
            if filter_name == "pending" and not has_pending:
                continue
            if filter_name == "resolved" and not (has_resolved and not has_pending):
                continue
            values = source.get("values") if isinstance(source.get("values"), dict) else {}
            page, order = source["row_key"].split(":", 1)
            rendered.append({"row_key": source["row_key"], "page": int(page) or None, "order": int(order), "cells": values, "observations": row_observations, "structured_review": row_structured})
        _required, pending = self._decision_counts(review, export)
        return {"schema_version": "4", "job_id": str(job_id), "review_revision": review.get("review_revision", 0), "pending_decision_count": pending, "filter": filter_name, "offset": offset, "limit": limit, "total_count": len(rendered), "columns": self._columns(export), "rows": rendered[offset:offset + limit]}

    def save_decisions(self, principal: TenantPrincipal, job_id: UUID, *, revision: int, decisions: list[dict[str, object]]) -> dict[str, int]:
        _job, payload = self._review(principal, job_id)
        if payload.get("review_revision") != revision:
            raise StaleTransition("STALE_REVIEW_REVISION")
        export = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        observations = {item["id"]: item for item in payload.get("observations", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
        stored = payload.setdefault("decisions", {})
        if not isinstance(stored, dict):
            raise JobNotFound("REVIEW_NOT_FOUND")
        structured = self._structured_reviews(payload, export)
        structured_stored = payload.get("structured_row_decisions", {})
        if not isinstance(structured_stored, dict):
            raise JobNotFound("REVIEW_NOT_FOUND")
        staged_standard: dict[str, dict[str, str | None]] = {}
        staged_structured: dict[tuple[str, str], dict[str, str]] = {}
        seen: set[str] = set()
        field_map = {"code": "item", "unit": "unit", "quantity": "quantity", "unit_price": "unit_price", "amount": "amount"}
        for decision in decisions:
            identifier = decision.get("observation_id")
            action = decision.get("action")
            field = decision.get("field")
            if not isinstance(identifier, str) or identifier not in observations:
                raise InvalidUpload("INVALID_REVIEW_DECISION")
            observation = observations[identifier]
            if not observation.get("requires_decision"):
                raise InvalidUpload("INVALID_REVIEW_DECISION")
            projection = structured.get(identifier)
            if action == "confirm_provisional_row":
                marker = f"row:{identifier}"
                if field is not None or marker in seen or projection is None:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                seen.add(marker)
                confirmed = 0
                for structured_field in projection["fields"]:
                    key = structured_field["key"]
                    if structured_field["can_confirm_provisional"]:
                        if (identifier, key) in staged_structured:
                            raise InvalidUpload("INVALID_REVIEW_DECISION")
                        staged_structured[(identifier, key)] = {
                            "action": "confirm_provisional", "value": structured_field["provisional_value"],
                            "field": key, "row_key": self._row_key(observation), "target_scope": "cell",
                        }
                        confirmed += 1
                if not confirmed:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                continue
            if field is not None:
                marker = f"field:{identifier}:{field}"
                if marker in seen or projection is None or field not in self.STRUCTURED_FIELDS or (identifier, field) in staged_structured:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                seen.add(marker)
                structured_field = next((item for item in projection["fields"] if item["key"] == field), None)
                if structured_field is None:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                if structured_field["manual_only"]:
                    if action != "set_value":
                        raise InvalidUpload("INVALID_REVIEW_DECISION")
                    value = decision.get("value")
                elif action == "keep_provisional":
                    value = structured_field["provisional_value"]
                elif action == "accept_suggestion":
                    suggestion = structured_field["suggestion"]
                    value = suggestion.get("value") if isinstance(suggestion, dict) else None
                elif action == "set_value":
                    value = decision.get("value")
                else:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                normalized = self._validated_structured_value(field, value)
                if normalized is None:
                    raise InvalidUpload("INVALID_REVIEW_DECISION")
                staged_structured[(identifier, field)] = {
                    "action": str(action), "value": normalized, "field": field,
                    "row_key": self._row_key(observation), "target_scope": "cell",
                }
                continue
            if identifier in seen or action == "keep_provisional":
                raise InvalidUpload("INVALID_REVIEW_DECISION")
            seen.add(identifier)
            if action not in observation.get("allowed_actions", []):
                raise InvalidUpload("INVALID_REVIEW_DECISION")
            if action == "accept_suggestion":
                suggestion = observation.get("suggestion")
                value = suggestion.get("value") if isinstance(suggestion, dict) else None
            elif action == "keep_original":
                value = observation.get("extracted_value")
            else:
                value = decision.get("value")
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 500:
                raise InvalidUpload("INVALID_REVIEW_DECISION")
            target_scope = "row" if observation.get("field") == "row" else "cell"
            staged_standard[identifier] = {
                "action": action,
                "value": " ".join(value.split()),
                "field": field_map.get(str(observation.get("field"))) if target_scope == "cell" else None,
                "row_key": self._row_key(observation),
                "target_scope": target_scope,
            }
        if not staged_standard and not staged_structured or len(staged_standard) + len(staged_structured) > 50:
            raise InvalidUpload("INVALID_REVIEW_DECISION")
        stored.update(staged_standard)
        structured_target = {identifier: dict(values) for identifier, values in structured_stored.items() if isinstance(identifier, str) and isinstance(values, dict)}
        for (identifier, field), value in staged_structured.items():
            structured_target.setdefault(identifier, {})[field] = value
        if structured_target:
            payload["structured_row_decisions"] = structured_target
        payload["review_revision"] = revision + 1
        self.storage.store_review(job_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self.storage.remove_export_result(job_id)
        pending = self._pending_decision_count(payload, export)
        return {"review_revision": revision + 1, "pending_decision_count": pending}

    @classmethod
    def _validated_structured_value(cls, field: str, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > (500 if field == "description" else 120) or any(ord(char) < 32 for char in normalized):
            return None
        if field in cls.STRUCTURED_NUMERIC_FIELDS and cls._canonical_structured_value(field, normalized) is None:
            return None
        return normalized

    @staticmethod
    def _pending_decision_count(review: dict[str, object], export: dict[str, object]) -> int:
        return JobService._decision_counts(review, export)[1]

    @staticmethod
    def _normalized_export_decisions(review: dict[str, object]) -> dict[str, dict[str, object]]:
        observations = {
            item["id"]: item
            for item in review.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        decisions = review.get("decisions", {})
        if not isinstance(decisions, dict):
            return {}
        field_map = {"code": "item", "unit": "unit", "quantity": "quantity", "unit_price": "unit_price", "amount": "amount"}
        normalized: dict[str, dict[str, object]] = {}
        for observation_id, decision in decisions.items():
            observation = observations.get(observation_id)
            if not isinstance(observation_id, str) or not isinstance(observation, dict) or not isinstance(decision, dict):
                continue
            item = dict(decision)
            if observation.get("field") == "row":
                item["target_scope"] = "row"
                item["field"] = None
            else:
                item["target_scope"] = "cell"
                field = field_map.get(str(observation.get("field")))
                if field is None and isinstance(item.get("field"), str):
                    field = item["field"]
                item["field"] = field
            normalized[observation_id] = item
        structured = review.get("structured_row_decisions", {})
        if isinstance(structured, dict):
            for observation_id, fields in structured.items():
                observation = observations.get(observation_id)
                if not isinstance(observation_id, str) or not isinstance(observation, dict) or observation.get("field") != "row" or not isinstance(fields, dict):
                    continue
                for field, decision in fields.items():
                    if field not in JobService.STRUCTURED_FIELDS or not isinstance(decision, dict) or not isinstance(decision.get("value"), str):
                        continue
                    item = dict(decision)
                    item.update({"field": field, "target_scope": "cell", "row_key": JobService._row_key(observation)})
                    normalized[f"{observation_id}:{field}"] = item
        return normalized

    @classmethod
    def _snapshot_with_structured_numeric_decisions(
        cls, snapshot: object, review: dict[str, object], decisions: dict[str, dict[str, object]]
    ) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            return {}
        projected = dict(snapshot)
        source_rows = snapshot.get("rows", [])
        if not isinstance(source_rows, list):
            return projected
        rows: list[dict[str, object]] = []
        values_by_row: dict[str, dict[str, object]] = {}
        for source in source_rows:
            if not isinstance(source, dict):
                continue
            row = dict(source)
            values = source.get("values") if isinstance(source.get("values"), dict) else {}
            copied_values = dict(values)
            row["values"] = copied_values
            rows.append(row)
            if isinstance(source.get("row_key"), str):
                values_by_row[source["row_key"]] = copied_values
        projected["rows"] = rows
        structured = review.get("structured_row_decisions", {})
        if not isinstance(structured, dict):
            return projected
        for observation_id, fields in structured.items():
            if not isinstance(observation_id, str) or not isinstance(fields, dict):
                continue
            for field in fields:
                if field not in cls.STRUCTURED_NUMERIC_FIELDS:
                    continue
                decision = decisions.get(f"{observation_id}:{field}")
                if not isinstance(decision, dict) or not isinstance(decision.get("value"), str) or not isinstance(decision.get("row_key"), str):
                    continue
                canonical = cls._canonical_structured_value(field, decision["value"])
                values = values_by_row.get(decision["row_key"])
                if canonical is None or values is None:
                    continue
                if not isinstance(canonical, Decimal):
                    continue
                values[field] = canonical
                decision["value"] = canonical
        return projected

    def _simple_export_available(
        self, job_id: UUID, review: dict[str, object], export: dict[str, object]
    ) -> bool:
        return (
            export.get("source_review_revision") == review.get("review_revision")
            and self._pending_decision_count(review, export) == 0
            and self.storage.export_result_path(job_id).is_file()
        )

    def export_payload(self, principal: TenantPrincipal, job_id: UUID) -> dict[str, object]:
        _job, review = self._review(principal, job_id)
        payload = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        pending = self._pending_decision_count(review, payload)
        return {"export_revision": payload.get("export_revision", 0), "source_review_revision": payload.get("source_review_revision", 0), "columns": payload.get("columns", []), "pending_decision_count": pending, "simple_result_available": self._simple_export_available(job_id, review, payload)}

    def save_export_config(self, principal: TenantPrincipal, job_id: UUID, *, revision: int, columns: list[dict[str, object]]) -> dict[str, object]:
        _job, review = self._review(principal, job_id)
        payload = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        if payload.get("export_revision") != revision:
            raise StaleTransition("STALE_EXPORT_REVISION")
        snapshot = payload.get("snapshot", {}) if isinstance(payload.get("snapshot"), dict) else {}
        rows = snapshot.get("rows", []) if isinstance(snapshot.get("rows"), list) else []
        allowed = {item.get("key") for item in self._columns(payload)}
        available = {key for row in rows if isinstance(row, dict) for key in (row.get("values", {}) if isinstance(row.get("values"), dict) else {})}
        if not columns or {item.get("key") for item in columns} - allowed or {item.get("key") for item in columns if item.get("origin") == "candidate"} - available or not any(item.get("included") for item in columns):
            raise InvalidUpload("INVALID_EXPORT_CONFIG")
        if len({item.get("key") for item in columns}) != len(columns) or len({item.get("position") for item in columns}) != len(columns):
            raise InvalidUpload("INVALID_EXPORT_CONFIG")
        if any(not isinstance(item.get("label"), str) or not item["label"].strip() or len(item["label"].strip()) > 60 or item.get("data_type") not in {"text", "decimal", "currency"} or item.get("origin") not in {"standard", "candidate"} for item in columns):
            raise InvalidUpload("INVALID_EXPORT_CONFIG")
        payload["columns"] = sorted(columns, key=lambda item: int(item["position"]))
        payload["export_revision"] = revision + 1
        payload["source_review_revision"] = review.get("review_revision", 0)
        self.storage.store_export(job_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        return self.export_payload(principal, job_id)

    def generate_export(self, principal: TenantPrincipal, job_id: UUID) -> Path:
        job, review = self._review(principal, job_id)
        payload = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        if payload.get("source_review_revision") != review.get("review_revision"):
            raise StaleTransition("STALE_EXPORT_CONFIG")
        if self._pending_decision_count(review, payload) > 0:
            raise ResultNotReady("RESULT_NOT_READY")
        decisions = self._normalized_export_decisions(review)
        snapshot = self._snapshot_with_structured_numeric_decisions(payload.get("snapshot", {}), review, decisions)
        write_simple_export(self.storage.export_result_path(job_id), filename=job.original_filename, snapshot=snapshot, decisions=decisions, columns=payload.get("columns", []))
        return self.storage.export_result_path(job_id)

    def export_result_path(self, principal: TenantPrincipal, job_id: UUID) -> Path:
        _job, review = self._review(principal, job_id)
        export = self._load_json(self.storage.export_path(job_id), "EXPORT_NOT_FOUND")
        if not self._simple_export_available(job_id, review, export):
            raise ResultNotReady("RESULT_NOT_READY")
        path = self.storage.export_result_path(job_id)
        return path
