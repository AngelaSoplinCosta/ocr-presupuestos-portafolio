import importlib
import logging
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from uuid import NAMESPACE_URL, UUID, uuid5

from ..domain.models import EngineOutcome, ReviewObservation, ReviewSuggestion
from ..logging_config import SafeFieldsFilter, log_job_event

_LOGGER_LOCK = threading.RLock()
REVIEW_SCHEMA_VERSION = "1"
MAX_TEXT_LENGTH = 500
_ADAPTER_LOGGER = logging.getLogger("ocr_orchestration")
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(?:api[_-]?key|hash|hmac|password|secret|token)\b\s*(?:=|:)\s*\S+"
)
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:)?/(?:[^\s'\"<>]|\\ )+")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
_HASH = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_OCR_TEXT = re.compile(r"(?i)\b(?:ocr\s*(?:text|texto)|texto\s+ocr)\s*[:=].*")
_STDERR_WORD = re.compile(r"[A-Za-zÀ-ÿ_]+|\d+")
_SAFE_STDERR_WORDS = frozenset(
    {
        "cannot",
        "code",
        "command",
        "corrupt",
        "cross",
        "damaged",
        "denied",
        "error",
        "exit",
        "failed",
        "failure",
        "file",
        "found",
        "ghostscript",
        "input",
        "invalid",
        "linearized",
        "missing",
        "not",
        "ocrmypdf",
        "output",
        "pdf",
        "permission",
        "qpdf",
        "redacted",
        "return",
        "status",
        "stderr",
        "stream",
        "subprocess",
        "tesseract",
        "timeout",
        "unavailable",
        "unsupported",
        "warning",
    }
)


def _safe_text(value: object, *, limit: int = MAX_TEXT_LENGTH) -> str:
    return " ".join(str(value or "").split())[:limit]


def _sanitize_stderr(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    text = " ".join(text.split())
    if not text:
        return None
    text = _OCR_TEXT.sub("ocr_text=[REDACTED]", text)
    text = _SENSITIVE_VALUE.sub("[REDACTED]", text)
    text = _ABSOLUTE_PATH.sub("[REDACTED_PATH]", text)
    text = _UUID.sub("[REDACTED_UUID]", text)
    text = _HASH.sub("[REDACTED_HASH]", text)

    def redact_unapproved(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.casefold() in _SAFE_STDERR_WORDS:
            return value
        return "REDACTED"

    text = _STDERR_WORD.sub(redact_unapproved, text)
    text = re.sub(r"[^A-Za-z0-9 _.,:;=\-\[\]()]", " ", text)
    text = " ".join(text.split())
    if len(text) > SafeFieldsFilter.MAX_STDERR_LENGTH:
        marker = " [TRUNCATED]"
        text = text[: SafeFieldsFilter.MAX_STDERR_LENGTH - len(marker)].rstrip() + marker
    return text or "[REDACTED]"


def _return_code(exc: Exception) -> int | None:
    value = getattr(exc, "returncode", None)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _process_failure_details(exc: Exception) -> tuple[int | None, object | None]:
    pending = [exc]
    seen: set[int] = set()
    while pending:
        candidate = pending.pop(0)
        candidate_id = id(candidate)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)

        stderr = getattr(candidate, "stderr", None)
        stdout = getattr(candidate, "stdout", None)
        return_code = _return_code(candidate)
        if return_code is not None or stderr is not None or stdout is not None:
            return return_code, stderr if stderr is not None else stdout

        for related in (candidate.__cause__, candidate.__context__):
            if isinstance(related, Exception):
                pending.append(related)
    return None, None


def _exception_type(exc: Exception) -> str:
    candidate = type(exc).__name__
    if SafeFieldsFilter.SAFE_EXCEPTION_TYPE.fullmatch(candidate) is None:
        return "UnknownError"
    return candidate


def _field_kind(field: str) -> tuple[str, str]:
    return {
        "item": ("code", "code"), "codigo": ("code", "code"), "código": ("code", "code"),
        "und": ("unit", "unit"), "unidad": ("unit", "unit"),
        "metrado": ("quantity", "quantity"), "precio": ("price", "unit_price"),
        "precio_soles": ("price", "unit_price"), "parcial": ("amount", "amount"),
        "parcial_soles": ("amount", "amount"),
    }.get(field.casefold(), ("document", "row"))


@contextmanager
def suppressed_engine_logger():
    """Silencia el logger global del motor y restaura exactamente su estado."""
    with _LOGGER_LOCK:
        logger = logging.getLogger("presupuestos")
        snapshot = {
            "handlers": list(logger.handlers),
            "filters": list(logger.filters),
            "level": logger.level,
            "disabled": logger.disabled,
            "propagate": logger.propagate,
        }
        logger.handlers = [logging.NullHandler()]
        logger.filters = []
        logger.setLevel(logging.CRITICAL + 1)
        logger.disabled = False
        logger.propagate = False
        try:
            yield logger
        finally:
            logger.handlers = snapshot["handlers"]
            logger.filters = snapshot["filters"]
            logger.setLevel(snapshot["level"])
            logger.disabled = snapshot["disabled"]
            logger.propagate = snapshot["propagate"]


class MotorPresupuestosAdapter:
    def __init__(self, module: ModuleType | None = None):
        self._module = module

    def _load_module(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module("procesar_presupuestos")
        return self._module

    def validate_available(self) -> None:
        module = self._load_module()
        required = (
            "process_source_pdf",
            "write_workbook_v6",
            "build_client_review_records",
        )
        if not all(callable(getattr(module, name, None)) for name in required):
            raise RuntimeError("MOTOR_CONTRACT_UNAVAILABLE")

    @staticmethod
    def _economic_validation_requires_review(message: object) -> bool:
        if not isinstance(message, str):
            raise ValueError("INVALID_ECONOMIC_VALIDATION")
        _label, separator, outcome = message.partition(":")
        if not separator:
            raise ValueError("INVALID_ECONOMIC_VALIDATION")
        normalized = outcome.strip()
        if normalized == "OK":
            return False
        if normalized.startswith("REVISAR (") or normalized == "REVISAR":
            return True
        if normalized.startswith("NO VALIDADA"):
            return True
        raise ValueError("UNKNOWN_ECONOMIC_VALIDATION_STATE")

    def process(
        self,
        *,
        input_path: Path,
        work_directory: Path,
        result_path: Path,
        display_name: str,
        job_id: UUID | None = None,
    ) -> EngineOutcome:
        started = time.monotonic()
        stage = "module_loading"
        log_job_event(_ADAPTER_LOGGER, stage="adapter_process", duration_ms=0)
        try:
            module = self._load_module()
            with suppressed_engine_logger() as engine_logger:
                stage = "source_processing"
                result = module.process_source_pdf(
                    input_path,
                    engine_logger,
                    work_directory,
                    None,
                    None,
                )
                stage = "workbook_writing"
                module.write_workbook_v6(
                    result_path,
                    display_name,
                    result,
                    False,
                )
                stage = "review_building"
                reviews = module.build_client_review_records(display_name, result)
                stage = "review_validation"
                control_requires_review = any(
                    control.estado_control == "REVISAR" for control in result.controls
                )
                validation_requires_review = any(
                    self._economic_validation_requires_review(validation)
                    for validation in result.validations
                )
        except Exception as exc:
            fields: dict[str, object] = {
                "stage": stage,
                "exception_type": _exception_type(exc),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            return_code, process_output = _process_failure_details(exc)
            if return_code is not None:
                fields["return_code"] = return_code
            stderr = _sanitize_stderr(process_output)
            if stderr is not None:
                fields["stderr"] = stderr
            log_job_event(_ADAPTER_LOGGER, **fields)
            raise
        return EngineOutcome(
            requires_review=(
                bool(reviews)
                or control_requires_review
                or validation_requires_review
            ),
            observations=tuple(self._public_observations(job_id or UUID(int=0), reviews, result)),
            export_snapshot=self._export_snapshot(result),
        )

    @staticmethod
    def _export_snapshot(result: object) -> dict[str, object]:
        rows = []
        for row in getattr(result, "rows", []):
            if getattr(row, "tipo_fila", "") != "partida":
                continue
            page, order = getattr(row, "pagina", 0), getattr(row, "orden_documento", 0)
            rows.append({
                "row_key": f"{page}:{order}",
                "values": {
                    "item": _safe_text(getattr(row, "item", "") or getattr(row, "codigo_normalizado", "")),
                    "description": _safe_text(getattr(row, "descripcion", "")),
                    "unit": _safe_text(getattr(row, "und", "")),
                    "quantity": _safe_text(getattr(row, "metrado", "")),
                    "unit_price": _safe_text(getattr(row, "precio_soles", "")),
                    "amount": _safe_text(getattr(row, "parcial_soles", "")),
                },
            })
        return {"rows": rows}

    @staticmethod
    def _public_observations(
        job_id: UUID, reviews: list[object], result: object
    ) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        for review in reviews:
            field = _safe_text(getattr(review, "observed_field", "row"), limit=64)
            kind, public_field = _field_kind(field)
            page, order = getattr(review, "page", None), getattr(review, "order", None)
            row_type = _safe_text(getattr(review, "row_type", "document"), limit=64) or "document"
            identifier = str(uuid5(NAMESPACE_URL, f"quipta-review:{REVIEW_SCHEMA_VERSION}:{job_id}:{page}:{order}:{row_type}:{public_field}"))
            original = _safe_text(getattr(review, "original_value", ""))
            suggested = _safe_text(getattr(review, "suggested_value", ""))
            confidence = _safe_text(getattr(review, "confidence", ""), limit=32)
            action = _safe_text(getattr(review, "required_action", ""))
            allowed_actions = tuple(
                action_name
                for action_name, available in (
                    ("accept_suggestion", bool(suggested)),
                    ("keep_original", bool(original)),
                    ("set_value", True),
                )
                if available
            )
            observations.append(ReviewObservation(
                id=identifier, state="PENDING", kind=kind,
                page=page if isinstance(page, int) and page > 0 else None,
                row_order=order if isinstance(order, int) and order >= 0 else None,
                row_type=row_type, row_label=_safe_text(getattr(review, "description", ""), limit=180),
                field=public_field, extracted_value=original,
                suggestion=ReviewSuggestion(suggested, confidence or "UNKNOWN") if suggested else None,
                reason=_safe_text(getattr(review, "reason", "")) or "Este dato requiere revisión.",
                evidence=(action,) if action else (),
                allowed_actions=allowed_actions,
                requires_decision=True,
            ))
        if observations:
            return observations
        controls = getattr(result, "controls", [])
        page = next((getattr(control, "pagina", None) for control in controls if getattr(control, "estado_control", "") == "REVISAR"), None)
        identifier = str(uuid5(NAMESPACE_URL, f"quipta-review:{REVIEW_SCHEMA_VERSION}:{job_id}:{page}:general:document:row"))
        return [ReviewObservation(
            id=identifier, state="PENDING", kind="document", page=page if isinstance(page, int) and page > 0 else None,
            row_order=None, row_type="document", row_label="Validaciones del documento", field="row", extracted_value="",
            suggestion=None, reason="Encontramos una diferencia en las validaciones del documento que requiere revisión.", evidence=(),
            requires_decision=False,
        )]
