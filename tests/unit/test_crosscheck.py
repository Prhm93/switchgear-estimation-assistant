"""Stage 5: cross-checks between files flag differences for the engineer and never resolve them."""

from __future__ import annotations

from types import SimpleNamespace as NS

from backend.app.crosscheck import Seen, differences, kind_of, seen_from_rows, value_key


def seen(field, value, unit, document, page=1, ref=None, file=None):
    return Seen(field, value, unit, document, file or f"{document}.pdf", page, ref)


def test_two_files_with_values_that_do_not_overlap_are_a_difference() -> None:
    out = differences([seen("way.Q2.rating", 630, "A", "specification", 4, 1),
                       seen("way.Q2.rating", 400, "A", "schematic", 1, 2)])
    assert len(out) == 1
    d = out[0]
    assert d.field == "way.Q2.rating" and d.kind == "rating" and d.label == "Way Q2 rating"
    assert d.message == "The specification says 630 A; the drawing says 400 A"
    assert [(s.document, s.sources[0]["ref"]) for s in d.sides] == [("specification", 1), ("schematic", 2)]


def test_same_value_written_differently_is_not_a_difference() -> None:
    assert differences([seen("way.Q2.rating", 630, "A", "specification"),
                        seen("way.Q2.rating", "630", "A", "schematic")]) == []
    assert differences([seen("incomer.device", "ACB", None, "specification"),
                        seen("incomer.device", "Air circuit breaker", None, "requirements")]) == []
    assert value_key("air circuit breaker", None) == value_key("acb", None)


def test_two_readings_of_one_file_are_not_a_difference_between_files() -> None:
    # the rules read 630 A and the model 400 A from the same specification: a conflict on Check, not here
    assert differences([seen("way.Q2.rating", 630, "A", "specification"),
                        seen("way.Q2.rating", 400, "A", "specification", 2)]) == []
    # files that share a value are not apart, even if one file also has another reading
    assert differences([seen("way.Q2.rating", 630, "A", "specification"),
                        seen("way.Q2.rating", 400, "A", "specification"),
                        seen("way.Q2.rating", 400, "A", "schematic")]) == []


def test_tbc_is_a_missing_value_not_a_difference() -> None:
    assert differences([seen("way.Q3.rating", None, None, "specification"),
                        seen("way.Q3.rating", 160, "A", "schematic")]) == []


def test_a_way_in_one_file_only_is_a_quantity_difference() -> None:
    out = differences([seen("way.Q1.rating", 250, "A", "specification"), seen("way.Q1.rating", 250, "A", "schematic"),
                       seen("way.Q11.rating", 100, "A", "schematic")])
    assert [(d.field, d.kind, d.message) for d in out] == [
        ("way.Q11", "quantity", "Way Q11 is in the drawing but not in the specification")]


def test_kinds() -> None:
    assert [kind_of(f) for f in ("ways.count", "busbar.rating", "way.Q1.breaking_capacity", "way.Q4.poles",
                                 "incomer.device", "enclosure.form")] == [
        "quantity", "rating", "rating", "poles", "device", "other"]


def test_rows_use_the_engineers_value_and_leave_rejected_ones_out() -> None:
    rows = [NS(id=1, field="busbar.rating", value=800, unit="A", approved_value=None, approved_unit=None,
               review_status="extracted", source_document="specification", source_file="s.pdf", page=2),
            NS(id=2, field="busbar.rating", value=1000, unit="A", approved_value=800, approved_unit="A",
               review_status="edited", source_document="schematic", source_file="d.dxf", page=1),
            NS(id=3, field="busbar.rating", value=1250, unit="A", approved_value=None, approved_unit=None,
               review_status="rejected", source_document="requirements", source_file="l.docx", page=None)]
    got = seen_from_rows(rows)
    assert [(s.ref, s.value) for s in got] == [(1, 800), (2, 800)]
    assert differences(got) == []  # the engineer's edit settled it; nothing is changed by the check itself


def test_the_check_never_changes_what_it_is_given() -> None:
    items = [seen("busbar.rating", 800, "A", "specification"), seen("busbar.rating", 1000, "A", "schematic")]
    before = list(items)
    differences(items)
    assert items == before


def test_files_are_named_in_one_order_specification_drawing_letter() -> None:
    out = differences([seen("busbar.rating", 1250, "A", "requirements"), seen("busbar.rating", 800, "A", "schematic"),
                       seen("busbar.rating", 1000, "A", "specification")])
    assert [s.document for s in out[0].sides] == ["specification", "schematic", "requirements"]
    assert out[0].message == "The specification says 1000 A; the drawing says 800 A; the letter says 1250 A"


def test_placeholder_text_is_a_missing_value_not_a_difference() -> None:
    # a model may copy "TBC", "-" or "N/A" as the value; like TBC, these state no value
    for text in ("TBC", "tbc", "-", "N/A", "n/a", "TBA", "", "  "):
        assert differences([seen("way.Q3.cable_length", text, "m", "specification"),
                            seen("way.Q3.cable_length", 55, "m", "schematic")]) == [], text
    assert differences([seen("way.Q1.breaking_capacity", "-", "kA", "specification"),
                        seen("way.Q1.breaking_capacity", "N/A", "kA", "schematic")]) == []
    # a real value still differs
    assert len(differences([seen("way.Q3.cable_length", 40, "m", "specification"),
                            seen("way.Q3.cable_length", 55, "m", "schematic")])) == 1
