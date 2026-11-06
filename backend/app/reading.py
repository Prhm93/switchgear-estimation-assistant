"""Read uploaded documents into text per page, keeping page numbers.

- PDF: pdfplumber, page by page (text lines and tables). A PDF without a text
  layer, such as a CAD export that draws its labels as outlines, is marked
  "not read yet": it needs OCR, which arrives in Stage 4.
- DOCX: python-docx paragraphs and table cells, in document order. A DOCX has
  no fixed pagination, so everything is page 1.
- DXF: ezdxf text entities (TEXT and MTEXT) with their positions. A sheet is a
  page: entities on layer ``SHEETn`` belong to page n, anything else to page 1.
- PNG and JPG (scanned or photographed drawings): stored, not read yet.

Only one page is held in memory at a time while reading a PDF.
"""

from __future__ import annotations

import io
import re

from pydantic import BaseModel, Field

from backend.app.schemas import DocumentKind, DocumentStatus
from backend.app.storage import FileType

NO_TEXT_LAYER = "No text layer: this drawing is not read yet. OCR arrives in Stage 4."
IMAGE_NOT_READ = "Scanned or photographed drawing: not read yet. OCR arrives in Stage 4."


class DxfText(BaseModel):
    """One text entity of a DXF drawing, in drawing units (mm)."""

    text: str
    x: float
    y: float
    height: float
    rotation: float = 0.0


class PageText(BaseModel):
    number: int = Field(ge=1)
    lines: list[str]  # text lines in reading order, exactly as extracted
    tables: list[list[list[str | None]]] = Field(default_factory=list)  # rows of cells
    items: list[DxfText] = Field(default_factory=list)  # DXF only

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class ReadResult(BaseModel):
    status: DocumentStatus
    pages: list[PageText] = Field(default_factory=list)
    note: str | None = None


def _read_pdf(data: bytes) -> ReadResult:
    import pdfplumber

    pages: list[PageText] = []
    chars = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            chars += len(page.chars)
            tables = page.extract_tables()
            pages.append(PageText(number=number, lines=text.splitlines(), tables=tables))
            page.close()  # frees the page's parsed objects
    if chars == 0:
        return ReadResult(status=DocumentStatus.NOT_READ, pages=pages, note=NO_TEXT_LAYER)
    return ReadResult(status=DocumentStatus.DONE, pages=pages)


def _read_docx(data: bytes) -> ReadResult:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    tables: list[list[list[str | None]]] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                lines.append(block.text)
        elif isinstance(block, Table):
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            tables.append(rows)
            lines += [" | ".join(r) for r in rows]
    return ReadResult(status=DocumentStatus.DONE, pages=[PageText(number=1, lines=lines, tables=tables)])


SHEET_LAYER = re.compile(r"^SHEET(\d+)$", re.IGNORECASE)


def _read_dxf(data: bytes) -> ReadResult:
    import ezdxf

    text = data.decode("utf-8", errors="replace")
    doc = ezdxf.read(io.StringIO(text))
    by_page: dict[int, list[DxfText]] = {}
    for e in doc.modelspace():
        kind = e.dxftype()
        if kind not in ("TEXT", "MTEXT"):
            continue
        content = e.dxf.text if kind == "TEXT" else e.plain_text()
        if not content.strip():
            continue
        m = SHEET_LAYER.match(e.dxf.layer)
        page = int(m.group(1)) if m else 1
        x, y = float(e.dxf.insert[0]), float(e.dxf.insert[1])
        height = float(e.dxf.get("height", 2.5) if kind == "TEXT" else e.dxf.get("char_height", 2.5))
        rotation = float(e.dxf.get("rotation", 0.0))
        by_page.setdefault(page, []).append(DxfText(text=content, x=x, y=y, height=height, rotation=rotation))
    pages = []
    for number in sorted(by_page):
        items = by_page[number]
        ordered = sorted(items, key=lambda t: (-round(t.y, 1), t.x))  # top to bottom, then left to right
        pages.append(PageText(number=number, lines=[t.text for t in ordered], items=items))
    if not pages:
        return ReadResult(status=DocumentStatus.NOT_READ, note="The DXF has no text entities.")
    return ReadResult(status=DocumentStatus.DONE, pages=pages)


def read_document(file_type: FileType, data: bytes) -> ReadResult:
    """Read one stored original. Never changes the bytes."""
    if file_type == FileType.PDF:
        return _read_pdf(data)
    if file_type == FileType.DOCX:
        return _read_docx(data)
    if file_type == FileType.DXF:
        return _read_dxf(data)
    return ReadResult(status=DocumentStatus.NOT_READ, note=IMAGE_NOT_READ)


def classify(file_type: FileType, result: ReadResult) -> DocumentKind:
    """Which enquiry document a file is: the letter (DOCX), the drawing, or the specification.

    Images, DXF files and PDFs without a text layer are drawings. A PDF with
    text is the specification unless its first page says it is a drawing.
    """
    if file_type == FileType.DOCX:
        return DocumentKind.REQUIREMENTS
    if file_type in (FileType.DXF, FileType.PNG, FileType.JPG) or result.note == NO_TEXT_LAYER:
        return DocumentKind.SCHEMATIC
    first = result.pages[0].text.lower() if result.pages else ""
    if "specification" not in first and ("single line diagram" in first or "drawing no" in first):
        return DocumentKind.SCHEMATIC
    return DocumentKind.SPECIFICATION
