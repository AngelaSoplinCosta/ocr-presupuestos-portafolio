import io
import logging
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.adapters.motor_presupuestos import MotorPresupuestosAdapter
from backend.app.logging_config import SafeFieldsFilter


@contextmanager
def capture_adapter_log():
    logger = logging.getLogger("ocr_orchestration")
    snapshot = (list(logger.handlers), logger.level, logger.propagate)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SafeFieldsFilter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield stream
    finally:
        logger.handlers = snapshot[0]
        logger.setLevel(snapshot[1])
        logger.propagate = snapshot[2]


def failing_adapter(failure: Exception) -> MotorPresupuestosAdapter:
    return MotorPresupuestosAdapter(
        module=SimpleNamespace(
            process_source_pdf=Mock(side_effect=failure),
            write_workbook_v6=Mock(),
            build_client_review_records=Mock(),
        )
    )


def chained_process_failure(*, stderr: object = None, stdout: object = None) -> RuntimeError:
    cause = subprocess.CalledProcessError(
        17,
        ["ocrmypdf", "/tmp/synthetic-private/input.pdf"],
        stderr=stderr,
        output=stdout,
    )
    failure = RuntimeError("ENGINE_PROCESSING_FAILED")
    failure.__cause__ = cause
    return failure


def test_adapter_logs_sanitized_details_from_chained_process_failure(tmp_path):
    secret = "token=super-secret-value"
    source_path = "/tmp/synthetic-private/input.pdf"
    ocr_text = "OCR texto: Persona Privada Empresa Reservada"
    identifier = "123e4567-e89b-12d3-a456-426614174000"
    digest = "a" * 64
    adapter = failing_adapter(chained_process_failure(
        stderr=f"{secret} {source_path} {ocr_text} uuid={identifier} hash={digest}"
    ))

    with capture_adapter_log() as stream, pytest.raises(RuntimeError, match="ENGINE_PROCESSING_FAILED"):
        adapter.process(
            input_path=tmp_path / "input.pdf",
            work_directory=tmp_path / "work",
            result_path=tmp_path / "result.xlsx",
            display_name="private.pdf",
        )

    output = stream.getvalue()
    assert "stage=adapter_process" in output
    assert "stage=source_processing" in output
    assert "exception_type=RuntimeError" in output
    assert "return_code=17" in output
    for sensitive in (secret, source_path, "Persona", "Privada", identifier, digest):
        assert sensitive not in output
    assert "stderr=" in output


def test_adapter_failure_keeps_public_error_and_truncates_stderr(
    client, app, auth_headers, synthetic_pdf
):
    adapter = failing_adapter(chained_process_failure(stdout="ocrmypdf error " * 300))
    app.state.job_service.processor.adapter = adapter

    with capture_adapter_log() as stream:
        response = client.post(
            "/v1/jobs",
            headers=auth_headers,
            files={"file": ("documento.pdf", synthetic_pdf, "application/pdf")},
        )

    output = stream.getvalue()
    assert response.json()["error_code"] == "INTERNAL_ERROR"
    assert response.json()["status"] == "ERROR"
    assert "[TRUNCATED]" in output
    stderr_line = next(line for line in output.splitlines() if "stderr=" in line)
    stderr = stderr_line.split("stderr=", 1)[1]
    assert len(stderr) <= SafeFieldsFilter.MAX_STDERR_LENGTH


def test_adapter_stops_on_cyclic_exception_chain(tmp_path):
    first = RuntimeError("ENGINE_PROCESSING_FAILED")
    second = RuntimeError("nested")
    first.__cause__ = second
    second.__context__ = first
    adapter = failing_adapter(first)

    with capture_adapter_log() as stream, pytest.raises(RuntimeError, match="ENGINE_PROCESSING_FAILED"):
        adapter.process(
            input_path=tmp_path / "input.pdf",
            work_directory=tmp_path / "work",
            result_path=tmp_path / "result.xlsx",
            display_name="private.pdf",
        )

    output = stream.getvalue()
    assert "stage=source_processing" in output
    assert "exception_type=RuntimeError" in output
