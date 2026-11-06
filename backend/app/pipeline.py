"""The rules-mode analysis of one uploaded file, free of any database or web code.

The background task (``backend/app/services.py``) and the accuracy command
(``backend/evaluate.py``) both call :func:`analyse_file`, so the scores are
for exactly the code the app runs.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.extraction import extract
from backend.app.reading import ReadResult, classify, read_document
from backend.app.schemas import DocumentKind, DocumentStatus, ExtractedValue
from backend.app.storage import FileType


class Analysis(BaseModel):
    kind: DocumentKind
    read: ReadResult
    values: list[ExtractedValue]


def analyse_file(file_type: FileType, data: bytes, display_name: str) -> Analysis:
    """Read, classify and extract. Files that cannot be read yet give no values."""
    result = read_document(file_type, data)
    kind = classify(file_type, result)
    values = extract(kind, result.pages, display_name) if result.status == DocumentStatus.DONE else []
    return Analysis(kind=kind, read=result, values=values)
