from openpyxl import load_workbook

from backend.app.services.simple_export import write_simple_export


def test_simple_export_uses_serializable_selected_descriptors(tmp_path):
    output = tmp_path / "simple.xlsx"
    write_simple_export(
        output,
        filename="presupuesto.pdf",
        snapshot={"rows": [{"row_key": "1:1", "values": {"description": "Excavación", "supplier": "Obras SAC"}}]},
        decisions={},
        columns=[
            {"key": "supplier", "label": "Proveedor", "data_type": "text", "included": True, "position": 0, "origin": "candidate"},
            {"key": "description", "label": "Descripción", "data_type": "text", "included": True, "position": 1, "origin": "standard"},
        ],
    )
    workbook = load_workbook(output)
    assert workbook.sheetnames == ["Resumen", "Partidas"]
    assert [cell.value for cell in workbook["Partidas"][1]] == ["Proveedor", "Descripción"]
    assert [cell.value for cell in workbook["Partidas"][2]] == ["Obras SAC", "Excavación"]
