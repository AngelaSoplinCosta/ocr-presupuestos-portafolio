import logging
import re
from uuid import UUID


class SafeFieldsFilter(logging.Filter):
    MAX_STDERR_LENGTH = 512
    ALLOWED = {
        "job_id",
        "request_id",
        "status",
        "duration_ms",
        "error_code",
        "metric",
        "count",
        "stage",
        "exception_type",
        "return_code",
        "stderr",
    }
    SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    SAFE_METRIC = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
    SAFE_STAGE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
    SAFE_EXCEPTION_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    SAFE_STDERR = re.compile(r"^[A-Za-z0-9 _.,:;=\-\[\]()]{1,512}$")
    ALLOWED_STATUSES = {
        "RECIBIDO",
        "PROCESANDO",
        "COMPLETADO",
        "REVISAR",
        "ERROR",
        "PROCESS_INTERRUPTED",
        "REQUEST_FAILED",
        "STARTUP_FAILED",
        "RESULT_REMOVED",
        "RESULT_CLEANUP_ERROR",
    }

    @classmethod
    def valid_fields(cls, fields: object) -> bool:
        if (
            not isinstance(fields, dict)
            or not fields
            or not set(fields).issubset(cls.ALLOWED)
        ):
            return False
        for key, value in fields.items():
            if key in {"job_id", "request_id"}:
                try:
                    UUID(str(value))
                except (ValueError, TypeError, AttributeError):
                    return False
            elif key == "status":
                if value not in cls.ALLOWED_STATUSES:
                    return False
            elif key == "error_code":
                if not isinstance(value, str) or cls.SAFE_CODE.fullmatch(value) is None:
                    return False
            elif key == "metric":
                if not isinstance(value, str) or cls.SAFE_METRIC.fullmatch(value) is None:
                    return False
            elif key == "stage":
                if not isinstance(value, str) or cls.SAFE_STAGE.fullmatch(value) is None:
                    return False
            elif key == "exception_type":
                if (
                    not isinstance(value, str)
                    or cls.SAFE_EXCEPTION_TYPE.fullmatch(value) is None
                ):
                    return False
            elif key == "return_code":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < -1_000_000_000
                    or value > 1_000_000_000
                ):
                    return False
            elif key == "stderr":
                if (
                    not isinstance(value, str)
                    or cls.SAFE_STDERR.fullmatch(value) is None
                    or len(value) > cls.MAX_STDERR_LENGTH
                ):
                    return False
            elif key in {"duration_ms", "count"}:
                if isinstance(value, bool) or not isinstance(value, int):
                    return False
                if value < 0 or value > 1_000_000_000:
                    return False
        return True

    def filter(self, record: logging.LogRecord) -> bool:
        fields = getattr(record, "safe_fields", None)
        if not self.valid_fields(fields):
            return False
        expected = " ".join(f"{key}={fields[key]}" for key in sorted(fields))
        return record.getMessage() == expected


def configure_safe_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.addFilter(SafeFieldsFilter())
    for name in (
        "ocr_orchestration",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "starlette",
        "fastapi",
        "sqlalchemy",
        "sqlalchemy.engine",
    ):
        configured = logging.getLogger(name)
        configured.handlers = [handler]
        configured.setLevel(logging.INFO)
        configured.propagate = False
    return logging.getLogger("ocr_orchestration")


def log_job_event(logger: logging.Logger, **safe_fields: object) -> None:
    if not SafeFieldsFilter.valid_fields(safe_fields):
        raise ValueError("UNSAFE_LOG_FIELDS")
    ordered = " ".join(f"{key}={safe_fields[key]}" for key in sorted(safe_fields))
    logger.info(ordered, extra={"safe_fields": safe_fields})
