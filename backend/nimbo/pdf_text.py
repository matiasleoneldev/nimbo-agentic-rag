"""PDF to plain text, keeping each table row on one line."""

from pathlib import Path

import pdfplumber
from pdfplumber.page import Page

# pdfminer emits the bullet glyph of the help-center PDFs as an unmapped cid.
_BULLET_CID = "(cid:127)"


def extract_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(_page_text(page) for page in pdf.pages).strip()


def _page_text(page: Page) -> str:
    # (top coordinate, text) blocks, sorted afterwards into reading order.
    blocks: list[tuple[float, str]] = []
    outside_tables = page
    # ponytail: default (ruling-lines) strategy; the help-center tables are all drawn with lines.
    for table in page.find_tables():
        outside_tables = outside_tables.outside_bbox(table.bbox)
        rows = [
            " | ".join(" ".join((cell or "").split()) for cell in row) for row in table.extract()
        ]
        blocks.append((table.bbox[1], "\n".join(rows)))
    for line in outside_tables.extract_text_lines():
        blocks.append((line["top"], line["text"]))
    blocks.sort(key=lambda block: block[0])
    return "\n".join(text for _, text in blocks).replace(_BULLET_CID, "•")
