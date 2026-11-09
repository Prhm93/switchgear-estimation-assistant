"""OCR of drawing PDFs and images with Tesseract (Stage 4).

What it does
------------
- A drawing PDF page is rendered with pypdfium2 at ``dpi`` (150 or 300). An
  image is taken as a 150 dpi scan (as the generated scans and photos are):
  at 300 it is enlarged twice (Lanczos) before reading, at 150 read as it is.
- Tesseract reads the page twice: upright, and turned a quarter turn clockwise
  so that the vertical way texts (rating and description, written bottom to
  top) read as normal lines. Boxes from the turned pass are mapped back.
- Every box is returned in the answer key's coordinates: pixels of the page at
  150 dpi for a PDF (the clean drawing's coordinates), pixels of the image for
  a PNG or JPG. A 300 dpi box is halved, so the same scorer works for both.

Tesseract is a separate program (Apache-2.0), called through pytesseract
(Apache-2.0). Its path comes from ``TESSERACT_CMD`` when it is not on PATH.
Nothing here decides what a text means: that is :mod:`backend.app.drawing.link`.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import shutil
import time
from collections import OrderedDict
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.storage import FileType
from data_generator.schemas import DrawingVersionKind

ANSWER_DPI = 150  # the clean drawing's answer-key coordinates are pixels of the page at this resolution
DPI_CHOICES = (150, 300)
PSM = 11  # Tesseract page mode "sparse text": labels scattered over a drawing, no paragraphs
DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # the Windows installer's folder


class TesseractMissing(RuntimeError):
    """OCR is switched on but the Tesseract program cannot be found."""


class OcrWord(BaseModel):
    text: str = Field(min_length=1)
    bbox: list[float] = Field(min_length=4, max_length=4)  # answer-key coordinates
    conf: float  # Tesseract's word confidence, 0 to 100


class OcrLine(BaseModel):
    """One line of words as Tesseract grouped them, upright or from the turned pass."""

    words: list[OcrWord] = Field(min_length=1)
    rotated: bool = False  # True: vertical text, read in the quarter-turned pass

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> list[float]:
        return union([w.bbox for w in self.words])

    @property
    def conf(self) -> float:
        return sum(w.conf for w in self.words) / len(self.words)


class SheetOcr(BaseModel):
    """The OCR of one drawing sheet (one PDF page or one image)."""

    sheet: int
    version: DrawingVersionKind
    width_px: int  # answer-key coordinates
    height_px: int
    lines: list[OcrLine]
    seconds: float


def union(boxes: list[list[float]]) -> list[float]:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def tesseract_command(explicit: str | None = None) -> str | None:
    """The Tesseract program to call: ``explicit``, else TESSERACT_CMD, else PATH, else the Windows default."""
    for candidate in (explicit, os.environ.get("TESSERACT_CMD")):
        if candidate:
            return candidate if Path(candidate).exists() or shutil.which(candidate) else None
    found = shutil.which("tesseract")
    if found:
        return found
    return DEFAULT_TESSERACT if Path(DEFAULT_TESSERACT).exists() else None


def tesseract_version(cmd: str | None = None) -> str | None:
    """Tesseract's version, or None when it cannot be found."""
    import pytesseract

    path = tesseract_command(cmd)
    if path is None:
        return None
    pytesseract.pytesseract.tesseract_cmd = path
    try:
        return str(pytesseract.get_tesseract_version())
    except (pytesseract.TesseractNotFoundError, OSError):
        return None


def drawing_identity(name: str, file_type: FileType) -> tuple[DrawingVersionKind, int | None]:
    """Version and sheet of an uploaded drawing, from its name.

    A PDF is the clean drawing; its sheets are its pages (``None`` here). An
    image is a photo when its name says so, otherwise a scan; its sheet is the
    number after "sheet" in the name, else 1. The version only labels the
    boxes; the reading is the same for both.
    """
    if file_type == FileType.PDF:
        return DrawingVersionKind.CLEAN, None
    stem = Path(name).stem.lower()
    m = re.search(r"sheet[ _-]?(\d+)", stem)
    version = DrawingVersionKind.PHOTO if "photo" in stem else DrawingVersionKind.SCANNED
    return version, int(m.group(1)) if m else 1


def unturn(box: list[float], turned_width: float) -> list[float]:
    """Map a box from the image turned a quarter turn clockwise back to the upright image.

    Turning clockwise sends upright ``(x, y)`` to ``(H - y, x)``, where ``H`` is the
    upright height (the turned image's width). So upright ``x = y'`` and ``y = H - x'``.
    """
    x0, y0, x1, y1 = box
    return [y0, turned_width - x1, y1, turned_width - x0]


def _lines(image, scale: float, rotated: bool) -> list[OcrLine]:
    """Tesseract words grouped into its lines; boxes scaled by ``scale`` (and unturned when ``rotated``)."""
    import pytesseract

    data = pytesseract.image_to_data(image, config=f"--psm {PSM}", output_type=pytesseract.Output.DICT)
    groups: dict[tuple[int, int, int], list[OcrWord]] = {}
    for i, raw in enumerate(data["text"]):
        text, conf = raw.strip(), float(data["conf"][i])
        if not text or conf < 0:
            continue
        box = [float(data["left"][i]), float(data["top"][i]),
               float(data["left"][i] + data["width"][i]), float(data["top"][i] + data["height"][i])]
        if rotated:
            box = unturn(box, image.width)
        box = [round(v * scale, 2) for v in box]
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(OcrWord(text=text, bbox=box, conf=conf))
    out = []
    for words in groups.values():
        if rotated:  # in the turned pass a line's words run from the bottom of the page upwards
            words.sort(key=lambda w: -w.bbox[3])
        out.append(OcrLine(words=words, rotated=rotated))
    return out


def ocr_image(image, scale: float = 1.0) -> list[OcrLine]:
    """Both passes over one greyscale image."""
    from PIL import Image

    upright = _lines(image, scale, rotated=False)
    turned = _lines(image.transpose(Image.Transpose.ROTATE_270), scale, rotated=True)
    return upright + turned


_CACHE: OrderedDict[tuple[str, int], list[SheetOcr]] = OrderedDict()
_CACHE_SIZE = 64  # small readings only (text and boxes), never the images


def ocr_drawing(file_type: FileType, data: bytes, name: str, *, dpi: int = 300,
                tesseract_cmd: str | None = None) -> list[SheetOcr]:
    """OCR every sheet of a drawing PDF, or the one sheet of an image. Raises :class:`TesseractMissing`."""
    import pytesseract
    from PIL import Image

    if dpi not in DPI_CHOICES:
        raise ValueError(f"dpi must be one of {DPI_CHOICES}, got {dpi}")
    path = tesseract_command(tesseract_cmd)
    if path is None:
        raise TesseractMissing("Tesseract was not found: install it or set TESSERACT_CMD")
    pytesseract.pytesseract.tesseract_cmd = path
    key = (hashlib.sha256(data).hexdigest() + name, dpi)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    version, sheet = drawing_identity(name, file_type)
    sheets: list[SheetOcr] = []
    if file_type == FileType.PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            for index in range(len(pdf)):
                start = time.perf_counter()
                page = pdf[index]
                width, height = page.get_size()  # points
                image = page.render(scale=dpi / 72).to_pil().convert("L")
                page.close()
                lines = ocr_image(image, scale=ANSWER_DPI / dpi)
                del image
                # the renderer rounds the page size up, so the 150 dpi answer-key page does too
                sheets.append(SheetOcr(sheet=index + 1, version=version, width_px=math.ceil(width / 72 * ANSWER_DPI),
                                       height_px=math.ceil(height / 72 * ANSWER_DPI), lines=lines,
                                       seconds=time.perf_counter() - start))
        finally:
            pdf.close()
    else:
        start = time.perf_counter()
        with Image.open(io.BytesIO(data)) as raw:
            image = raw.convert("L")
        width, height = image.width, image.height
        factor = dpi / ANSWER_DPI  # an image is taken as a 150 dpi scan: at 300 it is enlarged twice
        if factor != 1:
            image = image.resize((round(width * factor), round(height * factor)), Image.Resampling.LANCZOS)
        lines = ocr_image(image, scale=1 / factor)
        del image
        sheets.append(SheetOcr(sheet=sheet or 1, version=version, width_px=width, height_px=height,
                               lines=lines, seconds=time.perf_counter() - start))
    _CACHE[key] = sheets
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return sheets
