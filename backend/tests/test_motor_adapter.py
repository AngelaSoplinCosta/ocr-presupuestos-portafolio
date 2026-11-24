import importlib
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.adapters.motor_presupuestos import MotorPresupuestosAdapter


def test_importing_motor_does_not_run_subprocess_or_create_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("no ejecutar")))
    sys.modules.pop("procesar_presupuestos", None)
    before = set(tmp_path.iterdir())
    imported = importlib.import_module("procesar_presupuestos")
    assert imported.__name__ == "procesar_presupuestos"
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    ("reviews", "control_status", "expected"),
    [([], "OK", False), ([object()], "OK", True), ([], "REVISAR", True)],
)
def test_adapter_calls_published_contract(reviews, control_status, expected, tmp_path):
    result = SimpleNamespace(
        controls=[SimpleNamespace(estado_control=control_status)],
        validations=["Conciliación: OK"],
    )
    module = SimpleNamespace(
        process_source_pdf=Mock(return_value=result),
        write_workbook_v6=Mock(),
        build_client_review_records=Mock(return_value=reviews),
    )
    adapter = MotorPresupuestosAdapter(module=module)
    input_path = tmp_path / "input" / "source.pdf"
    work_dir = tmp_path / "work" / "ocr"
    result_path = tmp_path / "output" / "result.xlsx"

    outcome = adapter.process(
        input_path=input_path,
        work_directory=work_dir,
        result_path=result_path,
        display_name="metadato.pdf",
    )

    args = module.process_source_pdf.call_args.args
    assert args[0] == input_path
    assert args[2:] == (work_dir, None, None)
    module.write_workbook_v6.assert_called_once_with(
        result_path, "metadato.pdf", result, False
    )
    assert outcome.requires_review is expected


@pytest.mark.parametrize(
    ("validations", "reviews", "control_status", "expected"),
    [
        (["Suma de parciales: REVISAR (diferencia S/ 1.00)"], [], "OK", True),
        (["Suma de parciales: OK"], [], "OK", False),
        (
            ["Suma de parciales: REVISAR (diferencia S/ 1.00)"],
            [object()],
            "REVISAR",
            True,
        ),
    ],
)
def test_adapter_combines_all_explicit_review_sources(
    validations, reviews, control_status, expected, tmp_path
):
    result = SimpleNamespace(
        controls=[SimpleNamespace(estado_control=control_status)],
        validations=validations,
    )
    module = SimpleNamespace(
        process_source_pdf=Mock(return_value=result),
        write_workbook_v6=Mock(),
        build_client_review_records=Mock(return_value=reviews),
    )
    outcome = MotorPresupuestosAdapter(module=module).process(
        input_path=tmp_path / "source.pdf",
        work_directory=tmp_path / "work",
        result_path=tmp_path / "result.xlsx",
        display_name="metadato.pdf",
    )
    assert outcome.requires_review is expected


def test_adapter_rejects_unknown_economic_validation_state(tmp_path):
    result = SimpleNamespace(
        controls=[SimpleNamespace(estado_control="OK")],
        validations=["Suma de parciales: AMBIGUO"],
    )
    module = SimpleNamespace(
        process_source_pdf=Mock(return_value=result),
        write_workbook_v6=Mock(),
        build_client_review_records=Mock(return_value=[]),
    )
    with pytest.raises(ValueError, match="UNKNOWN_ECONOMIC_VALIDATION_STATE"):
        MotorPresupuestosAdapter(module=module).process(
            input_path=tmp_path / "source.pdf",
            work_directory=tmp_path / "work",
            result_path=tmp_path / "result.xlsx",
            display_name="metadato.pdf",
        )


def test_engine_error_propagates_and_logger_state_is_restored(tmp_path):
    logger = logging.getLogger("presupuestos")
    initial_state = (
        list(logger.handlers),
        list(logger.filters),
        logger.level,
        logger.disabled,
        logger.propagate,
    )
    original_handler = logging.NullHandler()
    original_filter = logging.Filter("original")
    logger.handlers = [original_handler]
    logger.filters = [original_filter]
    logger.setLevel(logging.WARNING)
    logger.disabled = True
    logger.propagate = True
    module = SimpleNamespace(process_source_pdf=Mock(side_effect=RuntimeError("sensitive")))

    try:
        with pytest.raises(RuntimeError):
            MotorPresupuestosAdapter(module=module).process(
                input_path=tmp_path / "source.pdf",
                work_directory=tmp_path / "work",
                result_path=tmp_path / "result.xlsx",
                display_name="privado.pdf",
            )

        assert logger.handlers == [original_handler]
        assert logger.filters == [original_filter]
        assert logger.level == logging.WARNING
        assert logger.disabled is True
        assert logger.propagate is True
    finally:
        logger.handlers = initial_state[0]
        logger.filters = initial_state[1]
        logger.setLevel(initial_state[2])
        logger.disabled = initial_state[3]
        logger.propagate = initial_state[4]
