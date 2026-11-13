"""Stage 7 report: wrong and missed values by the scorer's rule, the error table, and honest cells."""

from __future__ import annotations

from backend.app.evaluation import Score
from backend.evaluation_report import WAITING, cell, error_analysis, mismatches
from tests.unit.test_calibration import ev, tv


def test_mismatches_list_wrong_values_with_what_the_key_says_and_missed_values() -> None:
    truth = [tv("busbar.rating", 630), tv("way.Q1.rating", 250)]
    wrong, missed = mismatches([ev("busbar.rating", 630), ev("way.Q1.rating", 400)], truth)
    assert [(e.value, t.value) for e, t in wrong] == [(400, 250)]
    assert [t.field for t in missed] == ["way.Q1.rating"]


def test_error_table_counts_per_field_group_with_examples() -> None:
    truth = [tv("way.Q1.rating", 250), tv("way.Q2.rating", 160)]
    wrong, missed = mismatches([ev("way.Q1.rating", 400)], truth)
    text = error_analysis([("Rules", wrong, missed)])
    assert "| way.*.rating | 1 | 2 |" in text
    assert "read 400 A on specification p1 (rules); key: 250 A" in text and "missed 160 A" in text


def test_cells_never_invent_a_number() -> None:
    assert cell(None) == WAITING
    assert cell(Score(tp=3, fp=1, fn=0)) == "0.750, 1.000, **0.857** (3/1/0)"


def test_per_field_table_has_one_column_per_method_and_blank_cells_for_absent_groups() -> None:
    from backend.evaluation_report import per_field

    rows = per_field([("Rules", {"busbar.rating": Score(tp=2, fp=0, fn=0)}),
                      ("OCR", {"way.*.rating": Score(tp=1, fp=1, fn=0)})])
    assert rows[0] == "| Field group | Rules | OCR |"
    assert "| busbar.rating | 1.000 (2/0/0) |  |" in rows and "| way.*.rating |  | 0.667 (1/1/0) |" in rows
