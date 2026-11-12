"""The analysis of one uploaded file, free of any database or web code.

The background task (``backend/app/services.py``), the accuracy command
(``backend/evaluate.py``) and the recording command (``backend/record.py``)
all call :func:`analyse_file`, so the scores are for exactly the code the app
runs.

Without a model provider this is rules mode. With one (recorded or live), the
LLM reads every page too and the result is the combined list
(:mod:`backend.app.llm.combine`); the rules values and the LLM result are
also kept apart so each method can be scored on its own. If the model fails
(server down, recording refused) the rules values are used and the reason is
kept in ``llm_error``.

Drawing reading (Stage 4): with ``drawing_reading="ocr"`` a drawing PDF without
a text layer, or a drawing image, is read by Tesseract OCR
(:mod:`backend.app.drawing`) instead of being marked "not read yet". Its values
have method ``ocr``, at most medium confidence and a box on the drawing. The
default here is ``"off"``, so every Stage 2 and Stage 3 score is unchanged;
the app passes its DRAWING_READING setting (``ocr`` by default).

Vision (Stage 4 Part B): with a vision client (VISION_MODE, off by default) each
drawing sheet that OCR read, or every sheet when Tesseract is missing, also goes
to a vision model. Its values (method ``vision``) only fill fields OCR left
empty on that sheet (:mod:`backend.app.drawing.vision`). A failure keeps the OCR
values and says why in the note.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

import backend.app.llm  # noqa: F401  (makes the AI engine importable)
from backend.app.drawing.link import link_sheet
from backend.app.drawing.ocr import TesseractMissing, drawing_identity, ocr_drawing
from backend.app.drawing.reading import DrawingReading
from backend.app.drawing.vision import VisionClient, VisionUnavailable, vision_values
from backend.app.extraction import extract
from backend.app.injection import InstructionFlag, find_instructions
from backend.app.llm.combine import combine
from backend.app.llm.extract import LlmResult, llm_extract
from backend.app.llm.quote import QuoteCheckMode
from backend.app.reading import PageText, ReadResult, classify, read_document
from backend.app.schemas import DocumentKind, DocumentStatus, ExtractedValue
from backend.app.storage import FileType
from estimation_assistant.providers import ModelProvider, ModelUnavailable, RecordedProvider, RecordingMismatch


class Analysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: DocumentKind
    read: ReadResult
    values: list[ExtractedValue]  # what the app stores: rules values, or the combined list
    rules_values: list[ExtractedValue] = []
    llm: LlmResult | None = None
    llm_error: str | None = None
    model_run: str | None = None  # label for the UI, e.g. "gemma4:e2b, 2026-11-07"
    flags: list[InstructionFlag] = []
    drawings: list[DrawingReading] = []  # one per sheet read by OCR (Stage 4)
    vision_run: str | None = None  # label of the vision model run whose values were added (Part B)


DrawingReadingMode = Literal["off", "ocr"]
OCR_READABLE = (FileType.PDF, FileType.PNG, FileType.JPG)


def read_drawing_ocr(file_type: FileType, data: bytes, display_name: str, dpi: int,
                     tesseract_cmd: str | None) -> tuple[ReadResult, list[ExtractedValue], list[DrawingReading]]:
    """OCR every sheet: page text (upright lines, then vertical lines, top to bottom), values and readings."""
    sheets = ocr_drawing(file_type, data, display_name, dpi=dpi, tesseract_cmd=tesseract_cmd)
    pages, values, readings = [], [], []
    for sheet in sheets:
        ordered = sorted(sheet.lines, key=lambda ln: (ln.rotated, round(ln.bbox[1] / 10), ln.bbox[0]))
        pages.append(PageText(number=sheet.sheet, lines=[ln.text for ln in ordered]))
        sheet_values, reading = link_sheet(sheet, display_name)
        values += sheet_values
        readings.append(reading)
    note = f"Read by OCR (Tesseract, {dpi} dpi): every value needs the engineer's review."
    return ReadResult(status=DocumentStatus.DONE, pages=pages, note=note), values, readings


def sheet_count(file_type: FileType, data: bytes) -> int:
    """Sheets in a drawing file: pages of a PDF, one for an image."""
    if file_type != FileType.PDF:
        return 1
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


def _sheet_png(file_type: FileType, data: bytes, sheet: int) -> Callable[[], bytes]:
    def render() -> bytes:
        from backend.app.drawing.render import sheet_image

        out = io.BytesIO()
        sheet_image(file_type, data, sheet).save(out, format="PNG")
        return out.getvalue()
    return render


def add_vision(vision: VisionClient, file_type: FileType, data: bytes, display_name: str, read: ReadResult,
               values: list[ExtractedValue]) -> tuple[list[ExtractedValue], str | None, str]:
    """Vision values for every sheet, for fields OCR left empty; the run label and a note for the file."""
    version, image_sheet = drawing_identity(display_name, file_type)
    sha = hashlib.sha256(data).hexdigest()
    sheets = [image_sheet or 1] if file_type != FileType.PDF else list(range(1, sheet_count(file_type, data) + 1))
    text = {p.number: " ".join(p.lines) for p in read.pages}
    added: list[ExtractedValue] = []
    try:
        for sheet in sheets:
            output = vision.read(file_sha256=sha, sheet=sheet, image=_sheet_png(file_type, data, sheet))
            filled = {v.field for v in values if v.source.page == sheet}
            added += vision_values(output, file=display_name, version=version, sheet=sheet,
                                   ocr_text=text.get(sheet, ""), filled=filled)
    except VisionUnavailable as error:
        return [], None, f"The vision model did not read it: {error}."
    note = (f"A vision model ({vision.label}) also read the picture: {len(added)} value(s) for fields OCR left "
            "empty, each to be checked.")
    return added, vision.label, note


def run_label(provider: ModelProvider) -> str:
    if isinstance(provider, RecordedProvider):
        return provider.recording.label
    return f"{provider.model} (live, {provider.mode}), {datetime.now(UTC).date().isoformat()}"


def analyse_file(file_type: FileType, data: bytes, display_name: str,
                 provider: ModelProvider | None = None, *, system_prompt: str | None = None,
                 salvage: bool = True, quote_check: QuoteCheckMode = QuoteCheckMode.STRICT,
                 drawing_reading: DrawingReadingMode = "off", ocr_dpi: int = 300,
                 tesseract_cmd: str | None = None, vision: VisionClient | None = None) -> Analysis:
    """Read, classify and extract. Files that cannot be read yet give no values.

    ``system_prompt`` and ``salvage`` are for the evaluation only (scoring an
    older recording with its own prompt, and with the Part A parser); the app
    always uses the defaults. ``quote_check`` is strict here (the v2 baseline); the app passes its
    QUOTE_CHECK setting (relaxed by default). ``drawing_reading`` is off here (the Stage 3 baseline);
    the app passes its DRAWING_READING setting. OCR'd drawings are not sent to the model.
    """
    result = read_document(file_type, data)
    kind = classify(file_type, result)
    if (drawing_reading == "ocr" and kind == DocumentKind.SCHEMATIC and result.status == DocumentStatus.NOT_READ
            and file_type in OCR_READABLE):
        try:
            ocr_result, values, readings = read_drawing_ocr(file_type, data, display_name, ocr_dpi, tesseract_cmd)
        except TesseractMissing as error:
            result.note = f"{result.note} OCR is switched on, but {error}."
            if vision is not None:
                added, run, note = add_vision(vision, file_type, data, display_name, result, [])
                if added:
                    read = ReadResult(status=DocumentStatus.DONE, pages=result.pages,
                                      note=f"{result.note} {note}")
                    return Analysis(kind=kind, read=read, values=added, rules_values=added, vision_run=run)
                result.note = f"{result.note} {note}"
        else:
            run = None
            if vision is not None:
                added, run, note = add_vision(vision, file_type, data, display_name, ocr_result, values)
                values = values + added
                ocr_result.note = f"{ocr_result.note} {note}"
            flags = [f for page in ocr_result.pages for f in find_instructions(page.number, page.text)]
            return Analysis(kind=kind, read=ocr_result, values=values, rules_values=values, flags=flags,
                            drawings=readings, vision_run=run)
    done = result.status == DocumentStatus.DONE
    rules = extract(kind, result.pages, display_name) if done else []
    flags = [f for page in result.pages for f in find_instructions(page.number, page.text)]
    analysis = Analysis(kind=kind, read=result, values=rules, rules_values=rules, flags=flags)
    if provider is None or not done:
        return analysis
    try:
        options = {"system_prompt": system_prompt} if system_prompt is not None else {}
        llm = llm_extract(kind, result.pages, display_name, provider, salvage=salvage, quote_check=quote_check,
                          **options)
    except (ModelUnavailable, RecordingMismatch) as error:
        analysis.llm_error = str(error)
        return analysis
    analysis.llm = llm
    analysis.model_run = run_label(provider)
    analysis.values = combine(rules, llm.values)
    return analysis
