from pathlib import Path

from nimbo.pdf_text import extract_text
from tests.help_center_factory import MANIFEST, write_help_center


def test_pdf_text_keeps_table_rows_together(tmp_path: Path) -> None:
    write_help_center(tmp_path)

    text = extract_text(tmp_path / MANIFEST[1]["file_path"])

    lines = text.splitlines()
    assert (
        "Retiro inmediato a cuenta bancaria | 1,5% del monto, con el mínimo de la tabla siguiente"
        in lines
    )
    assert "Chile | 500 CLP" in lines
