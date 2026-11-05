"""The answer-key schema: ground truth only, strict, boxes checked."""

import pytest
from pydantic import ValidationError

from data_generator.schemas import AnswerKey, DrawingVersion, Region, SourceRef, SourcedValue, TruthValue


def _src(**kw):
    base = {"document": "specification", "file": "specification.pdf", "page": 3, "source_text": "400 V"}
    base.update(kw)
    return SourceRef(**base)


def test_truth_value_has_exactly_the_ground_truth_fields():
    v = TruthValue(field="system.voltage", value=400, unit="V", source=_src())
    assert set(v.model_dump()) == {"field", "value", "unit", "source"}
    assert set(v.source.model_dump()) == {"document", "file", "page", "source_text", "regions"}


@pytest.mark.parametrize("extra", ["method", "confidence", "review_status"])
def test_extraction_fields_are_rejected(extra):
    # Method, confidence and review status belong to extracted values (Stage 2), not to the answer key.
    with pytest.raises(ValidationError):
        TruthValue(field="system.voltage", value=400, unit="V", source=_src(), **{extra: "x"})


def test_truth_value_is_a_sourced_value():
    assert issubclass(TruthValue, SourcedValue)


def test_source_needs_text_or_region():
    with pytest.raises(ValidationError):
        SourceRef(document="schematic", file="drawing/schematic.pdf", page=1)
    ok = SourceRef(document="schematic", file="drawing/schematic.pdf", page=1,
                   regions=[Region(version="clean", sheet=1, bbox=[1, 2, 3, 4])])
    assert ok.source_text is None


def test_box_must_have_size():
    with pytest.raises(ValidationError):
        Region(version="clean", sheet=1, bbox=[5, 5, 5, 9])


def test_symbol_box_must_lie_inside_the_image():
    with pytest.raises(ValidationError, match="outside"):
        DrawingVersion(sheet=1, version="scanned", file="a.png", width_px=100, height_px=100,
                       symbols=[{"id": "S01", "cls": "mccb", "bbox": [90, 10, 101, 20]}])


def test_unknown_symbol_class_is_rejected():
    with pytest.raises(ValidationError):
        DrawingVersion(sheet=1, version="clean", file="a.pdf", page=1, dpi=150, width_px=100, height_px=100,
                       symbols=[{"id": "S01", "cls": "fuse", "bbox": [1, 1, 5, 5]}])


def test_minimal_answer_key_round_trips():
    key = AnswerKey(project_id="R01", origin="real", purpose="real",
                    values=[TruthValue(field="system.voltage", value=400, unit="V", source=_src())])
    assert AnswerKey.model_validate_json(key.model_dump_json()) == key
