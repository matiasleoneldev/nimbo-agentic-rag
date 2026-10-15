"""Writes a small fake help center (manifest + generated PDFs) into a directory.

The real corpus is git-ignored and no PDF may be committed, so tests build their own.
The NIM-020 PDF reproduces the real fee tables: bordered cells, one row per fee.
"""

import json
from pathlib import Path
from typing import Any

from fpdf import FPDF

FEE_TABLE = [
    ("Operación", "Comisión"),
    ("Cargar saldo por transferencia bancaria", "Gratis"),
    ("Retiro estándar a cuenta bancaria", "Gratis"),
    ("Retiro inmediato a cuenta bancaria", "1,5% del monto, con el mínimo de la tabla siguiente"),
]
MINIMUM_TABLE = [
    ("País", "Mínimo por retiro inmediato"),
    ("Argentina", "150 ARS"),
    ("Chile", "500 CLP"),
]


def _entry(file_path: str, doc_id: str, version: int, title: str, category: str) -> dict[str, Any]:
    return {
        "file_path": file_path,
        "id": doc_id,
        "version": version,
        "title": title,
        "category": category,
        "products": ["personal"],
        "countries": ["AR", "CL"],
        "language": "es",
        "updated_at": "2026-03-01",
        "tags": [],
    }


MANIFEST = [
    _entry(
        "documents/NIM-004-verificacion-en-dos-pasos.pdf",
        "NIM-004",
        1,
        "Activar la verificación en dos pasos",
        "account_security",
    ),
    _entry(
        "documents/NIM-020-comisiones-cuenta-personal.pdf",
        "NIM-020",
        1,
        "Comisiones para Cuentas Personales",
        "fees_limits",
    ),
    _entry(
        "updates/NIM-020-comisiones-cuenta-personal.pdf",
        "NIM-020",
        2,
        "Comisiones para Cuentas Personales",
        "fees_limits",
    ),
]


def _write_pdf(
    path: Path, title: str, paragraphs: list[str], tables: list[list[tuple[str, str]]]
) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(text=title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for paragraph in paragraphs:
        pdf.multi_cell(w=0, text=paragraph, new_x="LMARGIN", new_y="NEXT")
    for rows in tables:
        pdf.ln(4)
        with pdf.table() as table:
            for cells in rows:
                row = table.row()
                for cell in cells:
                    row.cell(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def write_help_center(root: Path) -> Path:
    """Creates the fake help center under `root` and returns the manifest path."""
    _write_pdf(
        root / MANIFEST[0]["file_path"],
        "Activar la verificación en dos pasos",
        ["Entrá a Configuración, tocá Seguridad y activá la verificación en dos pasos."],
        [],
    )
    _write_pdf(
        root / MANIFEST[1]["file_path"],
        "Comisiones para Cuentas Personales",
        ["Vigente desde el 1 de marzo de 2026."],
        [FEE_TABLE, MINIMUM_TABLE],
    )
    _write_pdf(
        root / MANIFEST[2]["file_path"],
        "Comisiones para Cuentas Personales",
        ["Vigente desde el 1 de noviembre de 2026."],
        [[("Operación", "Comisión"), ("Retiro inmediato a cuenta bancaria", "1,2% del monto")]],
    )
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
