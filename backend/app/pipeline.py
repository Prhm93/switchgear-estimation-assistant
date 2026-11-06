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
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

import backend.app.llm  # noqa: F401  (makes the AI engine importable)
from backend.app.extraction import extract
from backend.app.injection import InstructionFlag, find_instructions
from backend.app.llm.combine import combine
from backend.app.llm.extract import LlmResult, llm_extract
from backend.app.reading import ReadResult, classify, read_document
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


def run_label(provider: ModelProvider) -> str:
    if isinstance(provider, RecordedProvider):
        return provider.recording.label
    return f"{provider.model} (live, {provider.mode}), {datetime.now(UTC).date().isoformat()}"


def analyse_file(file_type: FileType, data: bytes, display_name: str,
                 provider: ModelProvider | None = None, *, system_prompt: str | None = None,
                 salvage: bool = True) -> Analysis:
    """Read, classify and extract. Files that cannot be read yet give no values.

    ``system_prompt`` and ``salvage`` are for the evaluation only (scoring an
    older recording with its own prompt, and with the Part A parser); the app
    always uses the defaults.
    """
    result = read_document(file_type, data)
    kind = classify(file_type, result)
    done = result.status == DocumentStatus.DONE
    rules = extract(kind, result.pages, display_name) if done else []
    flags = [f for page in result.pages for f in find_instructions(page.number, page.text)]
    analysis = Analysis(kind=kind, read=result, values=rules, rules_values=rules, flags=flags)
    if provider is None or not done:
        return analysis
    try:
        options = {"system_prompt": system_prompt} if system_prompt is not None else {}
        llm = llm_extract(kind, result.pages, display_name, provider, salvage=salvage, **options)
    except (ModelUnavailable, RecordingMismatch) as error:
        analysis.llm_error = str(error)
        return analysis
    analysis.llm = llm
    analysis.model_run = run_label(provider)
    analysis.values = combine(rules, llm.values)
    return analysis
