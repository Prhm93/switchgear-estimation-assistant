"""Load real drawings and their hand-written answer keys.

Real drawings live in ``data/external/`` (git-ignored, never committed), one
folder per drawing or enquiry, each with an ``answers.json`` in exactly the
synthetic format (:class:`~data_generator.schemas.AnswerKey`) and
``origin: "real"``. See ``docs/real-drawings.md``.

The loader checks more than the schema: every file named in the key must
exist, every hash must match, and every image size must match the key, so a
key never silently describes a different file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from data_generator.project import sha256_file
from data_generator.schemas import AnswerKey

EXTERNAL = Path(__file__).resolve().parents[1] / "data" / "external"


class AnswerKeyError(ValueError):
    """An answer key that does not match its files."""


@dataclass
class RealProject:
    folder: Path
    key: AnswerKey


def _pdf_page_size_px(path: Path, page: int, dpi: float) -> tuple[int, int]:
    pdf = pdfium.PdfDocument(str(path))
    try:
        w_pt, h_pt = pdf[page - 1].get_size()
    finally:
        pdf.close()
    return round(w_pt * dpi / 72.0), round(h_pt * dpi / 72.0)


def load_project(folder: Path, require_real: bool = True) -> RealProject:
    """Read and check ``folder/answers.json`` against the files beside it."""
    key = AnswerKey.model_validate_json((folder / "answers.json").read_bytes())
    if require_real and key.origin != "real":
        raise AnswerKeyError(f"{folder}: origin must be 'real', got {key.origin!r}")
    for doc in key.documents:
        path = folder / doc.file
        if not path.is_file():
            raise AnswerKeyError(f"{folder}: missing file {doc.file}")
        if sha256_file(path) != doc.sha256:
            raise AnswerKeyError(f"{folder}: SHA-256 of {doc.file} does not match the answer key")
    for d in key.drawings:
        path = folder / d.file
        if not path.is_file():
            raise AnswerKeyError(f"{folder}: missing drawing file {d.file}")
        if path.suffix.lower() == ".pdf":
            if d.page is None or d.dpi is None:
                raise AnswerKeyError(f"{folder}: a PDF drawing needs page and dpi ({d.file})")
            size = _pdf_page_size_px(path, d.page, d.dpi)
            tol = 1
        else:
            with Image.open(path) as im:
                size = im.size
            tol = 0
        if abs(size[0] - d.width_px) > tol or abs(size[1] - d.height_px) > tol:
            raise AnswerKeyError(f"{folder}: {d.file} is {size[0]}x{size[1]} px, key says "
                                 f"{d.width_px}x{d.height_px}")
    return RealProject(folder, key)


def discover(root: Path = EXTERNAL) -> list[RealProject]:
    """Every folder under ``root`` that has an ``answers.json``, loaded and checked."""
    if not root.is_dir():
        return []
    return [load_project(p.parent) for p in sorted(root.rglob("answers.json"))]
