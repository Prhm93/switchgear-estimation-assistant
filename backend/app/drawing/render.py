"""A drawing sheet as a PNG with boxes drawn on it, for the proof panel and the report.

Boxes are in the answer key's coordinates (see :mod:`backend.app.drawing.ocr`):
pixels of the page at 150 dpi for a PDF, pixels of the image for a PNG or JPG.
A PDF page is therefore rendered at 150 dpi, so a box lands where it was read.
Only one sheet is held in memory at a time.
"""

from __future__ import annotations

import io

from backend.app.drawing.ocr import ANSWER_DPI
from backend.app.storage import FileType

BOX_COLOUR = (227, 30, 36)  # the palette red
MARGIN = 220  # pixels kept around the boxes when cropping
MAX_WIDTH = 1600  # a full sheet is scaled down to this width


def can_render(file_type: FileType) -> bool:
    return file_type in (FileType.PDF, FileType.PNG, FileType.JPG)


def sheet_image(file_type: FileType, data: bytes, sheet: int = 1):
    """One sheet as an RGB Pillow image in answer-key coordinates. Raises ValueError for a missing sheet."""
    from PIL import Image

    if file_type == FileType.PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            if not 1 <= sheet <= len(pdf):
                raise ValueError(f"the drawing has no sheet {sheet}")
            page = pdf[sheet - 1]
            image = page.render(scale=ANSWER_DPI / 72).to_pil().convert("RGB")
            page.close()
            return image
        finally:
            pdf.close()
    if file_type in (FileType.PNG, FileType.JPG):
        with Image.open(io.BytesIO(data)) as raw:
            return raw.convert("RGB")
    raise ValueError(f"a {file_type.value} file has no picture to show")


def drawing_png(file_type: FileType, data: bytes, sheet: int, boxes: list[list[float]], crop: bool = False) -> bytes:
    """The sheet with every box outlined in red. ``crop`` keeps only the area around the boxes."""
    from PIL import ImageDraw

    image = sheet_image(file_type, data, sheet)
    draw = ImageDraw.Draw(image)
    width = max(3, image.width // 600)
    for x0, y0, x1, y1 in boxes:
        draw.rectangle([x0 - width, y0 - width, x1 + width, y1 + width], outline=BOX_COLOUR, width=width)
    if crop and boxes:
        left = max(0, int(min(b[0] for b in boxes)) - MARGIN)
        top = max(0, int(min(b[1] for b in boxes)) - MARGIN)
        right = min(image.width, int(max(b[2] for b in boxes)) + MARGIN)
        bottom = min(image.height, int(max(b[3] for b in boxes)) + MARGIN)
        image = image.crop((left, top, right, bottom))
    elif image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
