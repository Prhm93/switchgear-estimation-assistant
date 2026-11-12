"""Sources on a conflict card: true duplicates are merged, different drawings stay apart."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.enquiry import distinct_sources, review_groups
from backend.app.labels import value_source

CAD = SimpleNamespace(id=1, file_type="dxf")
PICTURE = SimpleNamespace(id=2, file_type="pdf")
SPEC = SimpleNamespace(id=3, file_type="pdf")


def value(vid: int, doc, kind: str, page: int, number: float, method: str = "rules") -> SimpleNamespace:
    return SimpleNamespace(id=vid, field="system.fault_level", value=number, unit="kA", review_status="extracted",
                           approved_value=None, approved_unit=None, source_document=kind, page=page,
                           document=doc, document_id=doc.id, method=method)


def test_the_same_source_and_value_twice_is_shown_once() -> None:
    side = [value(1, CAD, "schematic", 1, 36), value(2, CAD, "schematic", 1, 36, "llm"),
            value(3, SPEC, "specification", 4, 36)]
    assert [value_source(v) for v in distinct_sources(side)] == ["Drawing (CAD), sheet 1", "Specification, page 4"]


def test_cad_and_picture_with_different_values_stay_apart_and_are_labelled() -> None:
    project = SimpleNamespace(values=[value(1, CAD, "schematic", 1, 36), value(2, PICTURE, "schematic", 1, 50, "ocr")])
    group = review_groups(project)["system.fault_level"]
    assert group["conflict"]
    labels = [[value_source(v) for v in distinct_sources(side)] for side in group["sides"]]
    assert labels == [["Drawing (CAD), sheet 1"], ["Drawing (picture), sheet 1"]]


def test_cad_and_picture_with_the_same_value_are_both_kept() -> None:
    side = [value(1, CAD, "schematic", 1, 36), value(2, PICTURE, "schematic", 1, 36, "ocr")]
    assert [value_source(v) for v in distinct_sources(side)] == ["Drawing (CAD), sheet 1", "Drawing (picture), sheet 1"]
