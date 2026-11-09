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
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

import backend.app.llm  # noqa: F401  (makes the AI engine importable)
from backend.app.drawing.link import link_sheet
from backend.app.drawing.ocr import TesseractMissing, ocr_drawing
from backend.app.drawing.reading import DrawingReading
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


def run_label(provider: ModelProvider) -> str:
    if isinstance(provider, RecordedProvider):
        return provider.recording.label
    return f"{provider.model} (live, {provider.mode}), {datetime.now(UTC).date().isoformat()}"


def analyse_file(file_type: FileType, data: bytes, display_name: str,
                 provider: ModelProvider | None = None, *, system_prompt: str | None = None,
                 salvage: bool = True, quote_check: QuoteCheckMode = QuoteCheckMode.STRICT,
                 drawing_reading: DrawingReadingMode = "off", ocr_dpi: int = 300,
                 tesseract_cmd: str | None = None) -> Analysis:
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
        else:
            flags = [f for page in ocr_result.pages for f in find_instructions(page.number, page.text)]
            return Analysis(kind=kind, read=ocr_result, values=values, rules_values=values, flags=flags,
                            drawings=readings)
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
