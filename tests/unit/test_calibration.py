"""Stage 6 calibration: each value marked right or wrong by the scorer's own rule, then accuracy per level."""

from __future__ import annotations

from backend.app.evaluation import correct_flags, score, total
from backend.calibration import calibration_table, tally
from backend.app.schemas import Confidence, ExtractedValue, Method
from data_generator.schemas import DocumentKind, SourceRef, TruthValue


def src(page=1, doc=DocumentKind.SPECIFICATION):
    return SourceRef(document=doc, file="specification.pdf", page=page, source_text="x")


def ev(field, value, unit="A", page=1, method=Method.RULES, conf=Confidence.HIGH):
    return ExtractedValue(field=field, value=value, unit=unit, source=src(page), method=method, confidence=conf)


def tv(field, value, unit="A", page=1):
    return TruthValue(field=field, value=value, unit=unit, source=src(page))


def test_correct_flags_follow_the_scorers_one_to_one_rule() -> None:
    truth = [tv("busbar.rating", 630), tv("way.Q1.rating", 250)]
    values = [ev("busbar.rating", 630), ev("busbar.rating", 630), ev("way.Q1.rating", 400), ev("way.Q1.rating", 250, page=2)]
    flags = correct_flags(values, truth)
    assert flags == [True, False, False, False]  # a duplicate, a wrong value and a wrong page are all wrong
    assert sum(flags) == total(score(values, truth)).tp


def test_tally_and_table_give_accuracy_per_level() -> None:
    counts = tally([("high", True), ("high", True), ("high", False), ("low", False)])
    assert counts["high"] == [2, 3] and counts["low"] == [0, 1]
    table = calibration_table(counts)
    assert "| high | 3 | 2 | 0.667 |" in table and "| low | 1 | 0 | 0.000 |" in table
