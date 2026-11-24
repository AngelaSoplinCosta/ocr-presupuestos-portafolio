from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

STANDARD_DESCRIPTORS = (
    ("item", "Ítem", "text"),
    ("description", "Descripción", "text"),
    ("unit", "Unidad", "text"),
    ("quantity", "Metrado", "decimal"),
    ("unit_price", "Precio unitario", "currency"),
    ("amount", "Parcial", "currency"),
)


def standard_descriptors() -> list[dict[str, Any]]:
    return [
        {"key": key, "label": label, "data_type": data_type, "source_header": None,
         "included": True, "position": position, "origin": "standard"}
        for position, (key, label, data_type) in enumerate(STANDARD_DESCRIPTORS)
    ]


def write_simple_export(path: Path, *, filename: str, snapshot: dict[str, Any], decisions: dict[str, Any], columns: list[dict[str, Any]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumen"
    summary.append(["Documento", filename])
    summary.append(["Partidas", len(snapshot.get("rows", []))])
    summary.append(["Observaciones resueltas", len(decisions)])
    parts = workbook.create_sheet("Partidas")
    selected = sorted((item for item in columns if item["included"]), key=lambda item: item["position"])
    parts.append([item["label"] for item in selected])
    for row in snapshot.get("rows", []):
        values = dict(row["values"])
        for decision in decisions.values():
            if decision.get("target_scope") != "cell" or decision.get("row_key") != row["row_key"]:
                continue
            field = decision.get("field")
            value = decision.get("value")
            if isinstance(field, str) and isinstance(value, str):
                values[field] = value
        parts.append([values.get(item["key"], "") for item in selected])
    fill = PatternFill("solid", fgColor="174B9E")
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2" if sheet.title == "Partidas" else None
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = fill
        sheet.auto_filter.ref = sheet.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".xlsx", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        workbook.save(temporary)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
