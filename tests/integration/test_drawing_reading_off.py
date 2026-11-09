"""With drawing reading off, the evaluation is exactly the Stage 3 / 3c evaluation.

The pipeline and the accuracy command default to off; only the app turns OCR
on (DRAWING_READING=ocr). The showcase has the same file layout as a test
project, so the accuracy command's upload sets can be checked on it without
the git-ignored test sets.
"""

from __future__ import annotations

import inspect

from backend import evaluate
from backend.app.config import Settings
from backend.app.pipeline import analyse_file
from backend.app.schemas import DocumentKind, Method
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"


def test_defaults_are_off_for_scoring_and_ocr_for_the_app() -> None:
    assert inspect.signature(analyse_file).parameters["drawing_reading"].default == "off"
    assert inspect.signature(evaluate.project_values).parameters["drawing_reading"].default == "off"
    assert Settings().drawing_reading == "ocr"


def test_without_dxf_reads_no_drawing_values_by_default() -> None:
    values = evaluate.project_values(SHOWCASE, with_dxf=False)
    assert values and not [v for v in values if v.method == Method.OCR]
    assert not [v for v in values if v.source.document == DocumentKind.SCHEMATIC]


def test_off_gives_the_same_values_as_before_with_and_without_dxf() -> None:
    for with_dxf in (True, False):
        default = evaluate.project_values(SHOWCASE, with_dxf=with_dxf)
        off = evaluate.project_values(SHOWCASE, with_dxf=with_dxf, drawing_reading="off")
        assert [v.model_dump() for v in default] == [v.model_dump() for v in off]
        assert all(v.method == Method.RULES for v in default)
