"""Rules of the Check page that decide what "Accept all" may approve."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.enquiry import open_in_a_document, partial_ways
from backend.app.labels import activity_text, field_label


def row(field: str, document: str, status: str = "extracted", value=1) -> SimpleNamespace:
    return SimpleNamespace(field=field, source_document=document, review_status=status, value=value)


def test_a_way_in_every_document_that_lists_ways_is_not_partial() -> None:
    rows = [row("way.Q1.rating", "specification"), row("way.Q1.rating", "schematic"),
            row("ways.count", "requirements")]
    assert partial_ways(rows) == {}


def test_a_way_only_on_the_drawing_is_partial() -> None:
    rows = [row("way.Q1.rating", "specification"), row("way.Q1.rating", "schematic"),
            row("way.Q9.rating", "schematic"), row("way.Q9.device", "schematic")]
    assert partial_ways(rows) == {"Q9": ["specification"]}


def test_the_letter_does_not_list_ways_and_rejected_values_do_not_count() -> None:
    rows = [row("way.Q1.rating", "specification"), row("way.Q1.rating", "schematic"),
            row("way.Q2.rating", "specification"), row("way.Q2.rating", "schematic", "rejected"),
            row("ways.count", "requirements")]
    assert partial_ways(rows) == {"Q2": ["schematic"]}


def test_only_one_document_with_ways_means_nothing_to_compare() -> None:
    assert partial_ways([row("way.Q1.rating", "specification"), row("way.Q2.rating", "specification")]) == {}


def test_field_labels() -> None:
    assert field_label("way.Q12.breaking_capacity") == "Way Q12 breaking capacity"
    assert field_label("system.fault_level") == "Fault level"


def test_a_field_one_document_leaves_open_is_not_approved_in_bulk() -> None:
    """The specification says TBC and only the drawing gives the rating: the engineer decides."""
    assert open_in_a_document([row("way.Q3.rating", "specification", value=None), row("way.Q3.rating", "schematic")])
    assert not open_in_a_document([row("way.Q3.rating", "specification"), row("way.Q3.rating", "schematic")])
    assert not open_in_a_document([row("way.Q3.rating", "specification", "rejected", None),
                                   row("way.Q3.rating", "schematic")])


def test_activity_reads_as_plain_words() -> None:
    detail = {"field": "way.Q2.rating", "old": {"value": 200, "unit": "A", "status": "extracted"},
              "new": {"value": None, "unit": None, "status": "rejected"}, "reason": "superseded", "actor": None}
    assert activity_text("reject", detail) == "Rejected Way Q2 rating 200 A: superseded"
