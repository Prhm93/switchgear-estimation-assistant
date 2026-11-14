"""Stage 7 report: wrong and missed values by the scorer's rule, the error table, and honest cells."""

from __future__ import annotations

import json

from backend.app.evaluation import Score
from backend.evaluation_report import WAITING, Partial, cell, error_analysis, mismatches, plain, section, wait_for_memory
from tests.unit.test_calibration import ev, tv


def test_mismatches_list_wrong_values_with_what_the_key_says_and_missed_values() -> None:
    truth = [tv("busbar.rating", 630), tv("way.Q1.rating", 250)]
    wrong, missed = mismatches([ev("busbar.rating", 630), ev("way.Q1.rating", 400)], truth)
    assert [(e.value, t.value) for e, t in wrong] == [(400, 250)]
    assert [t.field for t in missed] == ["way.Q1.rating"]


def test_error_table_counts_per_field_group_with_examples() -> None:
    truth = [tv("way.Q1.rating", 250), tv("way.Q2.rating", 160)]
    wrong, missed = mismatches([ev("way.Q1.rating", 400)], truth)
    text = error_analysis([("Rules", *plain(wrong, missed))])  # changed on purpose: rows are saved as dicts
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


def test_the_partial_file_is_saved_after_every_project_and_read_back_by_a_new_run(tmp_path) -> None:
    path = tmp_path / "eval-fresh-partial.json"
    first = Partial(path, "fresh")
    first.put("rules_dxf", "F01", {"scores": {}})
    assert not path.with_suffix(".tmp").exists()
    again = Partial(path, "fresh")  # a new run after a stop
    assert again.get("rules_dxf", "F01") == {"scores": {}} and again.get("rules_dxf", "F02") is None
    assert again.rows("rules_dxf", ["F01", "F02"]) is None and again.rows("rules_dxf", ["F01"]) == [{"scores": {}}]
    assert Partial(path, "test").get("rules_dxf", "F01") is None  # another set never reads these rows


def test_under_the_memory_floor_the_run_waits_and_never_stops() -> None:
    readings = iter([500.0, 700.0, 1200.0])
    slept: list[float] = []
    assert wait_for_memory(lambda: next(readings), slept.append, floor=800, pause=300) == 2
    assert slept == [300, 300]
    assert wait_for_memory(lambda: None, slept.append) == 0  # unreadable memory: carry on


def _saved(tp: int, fp: int, fn: int) -> dict:
    return {"scores": {"busbar.rating": [tp, fp, fn]}, "wrong": [], "missed": [], "seconds": 1.0,
            "calibration": [["high", True]], "cross": {"planted": 1, "found": 1, "false": 0, "missing_planted": 0,
                                                       "missing_found": 0}}


def test_a_section_is_written_only_when_every_row_is_saved(tmp_path) -> None:
    partial = Partial(tmp_path / "p.json", "fresh")
    for row in ("rules_dxf", "rules_nodxf", "ocr_clean"):
        for name in ("F01", "F02"):
            partial.put(row, name, _saved(1, 0, 0))
    assert section("fresh", "Fresh", ["F01", "F02"], ("clean",), partial) is None  # detector row missing
    for name in ("F01", "F02"):
        partial.put("detector_clean", name, {"classes": {"acb": [1, 0, 1]}, "seconds": [2.0]})
    text = section("fresh", "Fresh", ["F01", "F02"], ("clean",), partial)
    assert "| Rules | DXF | 1.000, 1.000, **1.000** (2/0/0) |" in text
    assert "| clean | 2 | 0 | 2 | 1.000 | 0.500 | 0.667 | 2 of 4 | 2.00 |" in text
    assert f"| Rules + model | DXF | {WAITING} |" in text
    assert "Planted conflicts found: 2 of 2; false flags: 0." in text


def _full(partial: Partial, names: list[str]) -> None:
    for row in ("rules_dxf", "rules_nodxf", "ocr_clean"):
        for name in names:
            partial.put(row, name, _saved(1, 0, 0))
    for name in names:
        partial.put("detector_clean", name, {"classes": {"acb": [1, 0, 1]}, "seconds": [2.0]})


def test_model_alone_and_vision_rows_are_shown_when_saved_and_unread_sheets_say_not_read(tmp_path) -> None:
    partial = Partial(tmp_path / "p.json", "fresh")
    _full(partial, ["F01", "F02"])
    text = section("fresh", "Fresh", ["F01", "F02"], ("clean",), partial)
    assert f"| Model alone (v2, strict) | DXF | {WAITING} |" in text
    assert f"| Rules + OCR + vision | clean, no DXF | {WAITING} |" in text
    for name in ("F01", "F02"):
        partial.put("llm_dxf", name, _saved(1, 1, 0))
        partial.put("vision_clean", name, _saved(1, 0, 0) | {"sheets": [1, 2, ["schematic.pdf sheet 1"]]})
        partial.put("visiononly_clean", name, {"scores": {"way.*.rating": [2, 1, 1]}, "sheets": [1, 2,
                    [f"{name} schematic.pdf sheet 1"]], "padded": 1, "seconds": 0.1})
    text = section("fresh", "Fresh", ["F01", "F02"], ("clean",), partial)
    assert "| Model alone (v2, strict) | DXF | 0.500, 1.000, **0.667** (2/2/0) |" in text
    assert "| Rules + OCR + vision | clean, no DXF | 1.000, 1.000, **1.000** (2/0/0) |" in text
    assert "| clean | 2 of 4 | F01 schematic.pdf sheet 1, F02 schematic.pdf sheet 1 |" in text
    table = [ln for ln in text.split("### Vision model alone")[1].split("###")[0].splitlines() if ln.startswith("| clean")]
    assert table and "error" not in table[0].lower()


def test_question_box_table_puts_both_embedders_side_by_side_and_counts_right_refusals(tmp_path) -> None:
    from backend.evaluation_report import ask_section

    def saved(name: str, at1: int, in3: int, refused: list[bool], right: list[bool]) -> None:
        rows = [{"project": "F01", "field": "system.voltage", "refused": r, "right_refusal": ok}
                for r, ok in zip(refused, right, strict=True)]
        (tmp_path / f"fresh-{name}.json").write_text(json.dumps({
            "totals": {"questions": 4, "found_at_1": at1, "found_in_3": in3, "refused": sum(refused)},
            "rows": rows, "embedder": {"words": "words", "mxbai": "mxbai-embed-large"}[name],
            "min_score": 0.2 if name == "words" else 0.5}), encoding="utf-8")

    assert ask_section("fresh", tmp_path) is None
    saved("words", 2, 3, [True, False, False, False], [True, False, False, False])
    saved("mxbai", 3, 3, [True, True, False, False], [True, False, False, False])
    text = ask_section("fresh", tmp_path)
    assert "| words (threshold 0.2) | 4 | 0.500 | 0.750 | 1 | 1 |" in text
    assert "| mxbai-embed-large (threshold 0.5) | 4 | 0.750 | 0.750 | 2 | 1 |" in text


def test_redo_drops_only_the_named_rows(tmp_path) -> None:
    partial = Partial(tmp_path / "p.json", "fresh")
    for row in ("rules_dxf", "vision_clean", "visiononly_clean"):
        partial.put(row, "F01", {"scores": {}})
    assert partial.drop(["vision_", "visiononly_"]) == 2
    again = Partial(tmp_path / "p.json", "fresh")
    assert again.get("rules_dxf", "F01") is not None and again.get("vision_clean", "F01") is None
