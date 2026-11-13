"""Stage 6: confidence from how a value was read, whether files agree, and whether there is a conflict.

The rules under test (backend/app/confidence.py):

- Base level from how it was read: the rules reading a file's text are high; a model with an exact quote is
  medium; a model with a pieced quote is low; OCR and the vision model keep their own level, never above
  medium; the symbol detector is low; a value the engineer approved or typed is high.
- Another file giving the same value raises the level one step (a model value up to high; a picture or
  pieced value up to medium).
- A conflict needs at least one high value: two values that differ where one is high are a conflict.
  Two lower values that differ (model against model, picture against model) are a "weak difference":
  each is low and checked on its own, never a conflict card and never accepted in bulk.
- Only high values read by the rules (no model, no picture) may be accepted in bulk.
- Risk orders the review queue: conflict, then low, medium, high; within a level the less reliable method first.
"""

from __future__ import annotations

from backend.app.confidence import assess, base_level
from backend.app.crosscheck import Seen, differences


def s(ref, field="way.Q2.rating", value=630, document="specification", method="rules", conf="high",
      quote=None, flags=(), status="extracted", unit="A", page=1):
    return Seen(field, value, unit, document, f"{document}.pdf", page, ref, method=method, quote_match=quote,
                confidence=conf, flags=tuple(flags), status=status)


def test_base_level_follows_how_the_value_was_read() -> None:
    assert base_level(s(1)) == "high"
    assert base_level(s(1, method="llm", conf="medium", quote="exact")) == "medium"
    assert base_level(s(1, method="llm", conf="medium", quote="words_on_page")) == "low"
    assert base_level(s(1, method="ocr", conf="medium")) == "medium"
    assert base_level(s(1, method="ocr", conf="high")) == "medium"  # a picture is never high on its own
    assert base_level(s(1, method="vision", conf="low")) == "low"
    assert base_level(s(1, method="detector", conf="low")) == "low"
    assert base_level(s(1, method="llm", conf="low", quote="exact", flags=["poles_from_cable_cores"])) == "low"
    assert base_level(s(1, method="llm", conf="medium", quote="exact", status="approved")) == "high"


def test_another_file_with_the_same_value_raises_the_level_one_step() -> None:
    out = assess([s(1, method="llm", conf="medium", quote="exact"), s(2, document="schematic")])
    assert out[1].level == "high" and out[2].level == "high"
    assert any("agree" in r for r in out[1].reasons)
    pic = assess([s(1, method="ocr", conf="medium", document="schematic"), s(2)])
    assert pic[1].level == "medium"  # a picture value stays at most medium
    low_pic = assess([s(1, method="ocr", conf="low", document="schematic"), s(2)])
    assert low_pic[1].level == "medium"


def test_a_difference_with_a_high_value_is_a_conflict() -> None:
    out = assess([s(1), s(2, value=400, document="schematic", method="llm", conf="medium", quote="exact")])
    assert out[1].level == "conflict" and out[2].level == "conflict"


def test_two_lower_values_that_differ_are_a_weak_difference_not_a_conflict() -> None:
    out = assess([s(1, method="llm", conf="medium", quote="exact"),
                  s(2, value=400, document="schematic", method="llm", conf="medium", quote="exact")])
    assert out[1].level == "low" and out[2].level == "low"
    assert out[1].weak_difference and not out[1].bulk_ok
    assert any("another reading" in r.lower() for r in out[1].reasons)


def test_only_high_values_read_by_the_rules_may_be_accepted_in_bulk() -> None:
    out = assess([s(1), s(2, field="busbar.rating", method="llm", conf="medium", quote="exact"),
                  s(3, field="busbar.rating", document="schematic"),
                  s(4, field="enclosure.form", value="4b", unit=None, method="ocr", conf="medium", document="schematic"),
                  s(5, field="enclosure.form", value="4b", unit=None)])
    assert out[1].bulk_ok
    assert out[2].level == "high" and not out[2].bulk_ok  # a model value is ticked by a person
    assert out[3].bulk_ok
    assert not out[4].bulk_ok  # a picture value is ticked by a person
    assert out[5].bulk_ok


def test_tbc_and_placeholders_are_left_as_read_and_never_bulk() -> None:
    out = assess([s(1, value=None, unit=None), s(2, value=630, document="schematic")])
    assert not out[1].bulk_ok and out[2].level == "high"


def test_risk_puts_conflicts_first_then_low_then_less_reliable_methods() -> None:
    out = assess([s(1, field="busbar.rating"),
                  s(2, field="incomer.rating", value=800, document="schematic", method="llm", conf="medium",
                    quote="exact"),
                  s(3, field="incomer.rating", value=1000),
                  s(4, field="way.Q3.device", value="mccb", unit=None, method="detector", conf="low",
                    document="schematic"),
                  s(5, field="way.Q4.device", value="mccb", unit=None, method="llm", conf="low", quote="exact",
                    flags=["poles_from_cable_cores"])])
    order = sorted(out, key=lambda k: out[k].risk, reverse=True)
    assert order[:2] == [2, 3] or order[:2] == [3, 2]
    assert order[2:4] == [4, 5]  # both low; the detector is less reliable than the model
    assert order[-1] == 1


def test_rejected_values_are_left_out() -> None:
    out = assess([s(1), s(2, value=400, document="schematic", status="rejected")])
    assert 2 not in out and out[1].level == "high"


# --- the cross-check gate -------------------------------------------------------------------------------

def test_the_gated_cross_check_flags_only_differences_with_a_high_side() -> None:
    model_vs_model = [s(1, method="llm", conf="medium", quote="exact"),
                      s(2, value=400, document="schematic", method="llm", conf="medium", quote="exact")]
    assert len(differences(model_vs_model)) == 1  # Stage 5 behaviour is unchanged by default
    assert differences(model_vs_model, gate=True) == []
    rules_vs_model = [s(1), s(2, value=400, document="schematic", method="llm", conf="medium", quote="exact")]
    assert len(differences(rules_vs_model, gate=True)) == 1


def test_the_gated_cross_check_flags_a_missing_way_only_when_one_listing_is_reliable() -> None:
    model_only = [s(1, field="way.Q1.rating", method="llm", conf="medium", quote="exact"),
                  s(2, field="way.Q1.rating", document="schematic", method="llm", conf="medium", quote="exact"),
                  s(3, field="way.Q9.rating", document="schematic", method="llm", conf="medium", quote="exact")]
    assert [d.field for d in differences(model_only)] == ["way.Q9"]
    assert differences(model_only, gate=True) == []
    reliable_spec = [s(1, field="way.Q1.rating"), s(2, field="way.Q1.rating", document="schematic"),
                     s(3, field="way.Q9.rating", document="schematic", method="llm", conf="medium", quote="exact")]
    assert [d.field for d in differences(reliable_spec, gate=True)] == ["way.Q9"]
