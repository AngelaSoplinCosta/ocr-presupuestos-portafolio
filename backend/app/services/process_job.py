import json
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import SQLAlchemyError

from ..adapters.motor_presupuestos import MotorPresupuestosAdapter
from ..config import Settings
from ..domain.enums import JobStatus
from ..domain.errors import StaleTransition
from ..domain.models import JobView, ReviewObservation
from ..infrastructure.repositories.jobs import SqlAlchemyJobRepository
from ..infrastructure.storage.base import JobStorage
from ..logging_config import log_job_event
from .concurrency import SingleInstanceProcessingGate
from .simple_export import standard_descriptors


class JobProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SqlAlchemyJobRepository,
        storage: JobStorage,
        adapter: MotorPresupuestosAdapter,
        logger: logging.Logger,
        gate: SingleInstanceProcessingGate,
    ):
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.adapter = adapter
        self.logger = logger
        self.gate = gate

    def process(self, job_id: UUID) -> JobView:
        started = time.monotonic()
        with self.gate.hold():
            record = self.repository.get_internal(job_id)
            if record is None:
                raise LookupError("JOB_NOT_FOUND")
            if record.status != JobStatus.RECIBIDO.value:
                return record.to_view()
            self.repository.transition(
                job_id,
                JobStatus.RECIBIDO,
                JobStatus.PROCESANDO,
                increment_attempt=True,
            )
            log_job_event(
                self.logger, job_id=job_id, status=JobStatus.PROCESANDO.value
            )
            try:
                outcome = self.adapter.process(
                    input_path=self.storage.input_path(job_id),
                    work_directory=self.storage.work_directory(job_id),
                    result_path=self.storage.result_path(job_id),
                    display_name=record.safe_original_name,
                    job_id=job_id,
                )
                status = (
                    JobStatus.REVISAR
                    if outcome.requires_review
                    else JobStatus.COMPLETADO
                )
                expires_at = datetime.now(UTC) + timedelta(
                    hours=self.settings.result_retention_hours
                )
                observations = outcome.observations
                if outcome.requires_review and not observations:
                    observations = (
                        ReviewObservation(
                            id=str(uuid5(NAMESPACE_URL, f"quipta-review:1:{job_id}:general:document:row")),
                            state="PENDING", kind="document", page=None, row_order=None,
                            row_type="document", row_label="Validaciones del documento", field="row",
                            extracted_value="", suggestion=None,
                            reason="Encontramos una diferencia en las validaciones del documento que requiere revisión.",
                            evidence=(), requires_decision=False,
                        ),
                    )
                self.storage.store_review(job_id, json.dumps({
                    "schema_version": "2", "job_id": str(job_id), "status": status.value,
                    "review_revision": 0, "decisions": {}, "result_expires_at": expires_at.isoformat(),
                    "observations": [{
                        "id": item.id, "state": item.state, "kind": item.kind, "page": item.page,
                        "row": {"order": item.row_order, "type": item.row_type, "label": item.row_label},
                        "field": item.field, "extracted_value": item.extracted_value,
                        "suggestion": None if item.suggestion is None else {"value": item.suggestion.value, "confidence": item.suggestion.confidence},
                        "reason": item.reason, "evidence": list(item.evidence),
                        "allowed_actions": list(item.allowed_actions), "requires_decision": item.requires_decision,
                    } for item in observations],
                }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                self.storage.store_export(job_id, json.dumps({
                    "export_revision": 0, "source_review_revision": 0,
                    "snapshot": outcome.export_snapshot or {"rows": []},
                    "columns": standard_descriptors(),
                }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                self.storage.cleanup_transient(job_id)
                view = self.repository.transition(
                    job_id,
                    JobStatus.PROCESANDO,
                    status,
                    result_storage_key=self.storage.result_storage_key(job_id),
                    result_expires_at=expires_at,
                )
                log_job_event(
                    self.logger,
                    job_id=job_id,
                    status=status.value,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                return view
            except (SQLAlchemyError, StaleTransition):
                raise
            except Exception as exc:
                error_code = (
                    "STORAGE_PROCESSING_FAILED"
                    if isinstance(exc, OSError)
                    else "ENGINE_PROCESSING_FAILED"
                )
                view = self.repository.transition(
                    job_id,
                    JobStatus.PROCESANDO,
                    JobStatus.ERROR,
                    error_code,
                )
                try:
                    self.storage.remove_job(job_id)
                except Exception:
                    pass
                log_job_event(
                    self.logger,
                    job_id=job_id,
                    status=JobStatus.ERROR.value,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_code=error_code,
                )
                return view
