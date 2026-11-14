"""The six tiles on an enquiry's Summary page (Stage UX visual pass, V4), worked out from the enquiry.

Design decisions of 12 Nov 2026: the cost tile says "Waiting for approvals" until something is approved,
then shows the total built from approved values only, marked "Draft, from N of M lines". The missing
tile counts required fields that no file gives ("Required, not found", from the app's own list of
required fields, not from the specification) and shows TBC values apart, as "Marked TBC".
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace as NS

from backend.app.enquiry import summary_tiles


def doc(kind: str, file_type: str) -> NS:
    return NS(kind=kind, file_type=file_type)


def found(conflicts=0, needs=0, approved=0, missing=(), ways=("Q1", "Q2")) -> NS:
    groups = {f"way.{w}.rating": {} for w in ways}
    groups["system.voltage"] = {}
    return NS(conflicts=[{}] * conflicts, disagree=conflicts, needs=needs, approved=approved, missing=list(missing),
              groups=groups)


def tiles(**kw) -> dict:
    project = kw.pop("project", NS(name="MSB-2 main switchboard",
                                   documents=[doc("specification", "pdf"), doc("schematic", "dxf"),
                                              doc("schematic", "pdf")]))
    out = summary_tiles(project, kw.pop("found", found()), kw.pop("items", [1, 2, 3]),
                        kw.pop("estimate", None), kw.pop("blockers", []))
    return {t.key: t for t in out}


def test_six_tiles_in_order_with_plain_labels() -> None:
    project = NS(name="MSB-2", documents=[])
    out = summary_tiles(project, found(), [], None, [])
    assert [t.label for t in out] == ["What is quoted", "Parts found", "Drawing attached", "Do they agree?",
                                      "Estimated cost", "Required, not found"]
    assert all(t.href for t in out)  # every tile opens the step that shows its detail


def value(v, unit=None) -> dict:
    return {"sides": [[NS(review_status="extracted", value=v, unit=unit)]], "conflict": False}


def test_what_is_quoted_parts_and_drawing() -> None:
    # Changed on purpose (brief, steps 6 and 7): the tile is a line from the values, not the enquiry's name.
    t = tiles()
    assert t["quoted"].value == "No main ratings found yet" and t["quoted"].note == "2 outgoing ways found"
    assert t["parts"].value == "3"
    assert t["drawing"].value == "Yes: DXF, PDF"
    assert tiles(project=NS(name="X", documents=[doc("specification", "pdf")]))["drawing"].value == "No"


def test_agreement_tile_names_conflicts_and_waiting_decisions() -> None:
    assert tiles(found=found(conflicts=3, needs=46))["agree"].value == "Not yet: 3 disagree"
    assert tiles(found=found(conflicts=3, needs=46))["agree"].tone == "conflict"
    agree = tiles(found=found(conflicts=0, needs=46))["agree"]
    assert agree.value == "Yes" and agree.note == "46 decisions wait for you"
    assert tiles(found=found(conflicts=0, needs=0))["agree"].note is None


def test_cost_waits_for_approvals_and_then_says_draft_from_n_of_m_lines() -> None:
    estimate = NS(lines=[1, 2, 3, 4], currency="GBP", total=Decimal("19924.74"))
    waiting = tiles(found=found(approved=0), estimate=estimate)["cost"]
    assert waiting.value == "Waiting for approvals" and waiting.note is None  # nothing approved: no total
    assert tiles(found=found(approved=5), estimate=None)["cost"].value == "Waiting for approvals"
    cost = tiles(found=found(approved=5), estimate=estimate, blockers=[1, 2])["cost"]
    assert cost.value == "GBP 19,924.74" and cost.note == "Draft, from 4 of 6 lines"


def test_missing_counts_required_fields_and_keeps_tbc_apart() -> None:
    missing = [{"label": "Fault level", "why": "Not found in any file read"},
               {"label": "Way Q3 rating", "why": "Stated as TBC; no value given"},
               {"label": "IP rating", "why": "Not found in any file read"}]
    m = tiles(found=found(missing=missing))["missing"]
    assert m.value == "2" and m.extra == "Marked TBC: 1"
    assert m.note == "From the app's list of required fields, not from the specification."
    none = tiles(found=found(missing=[]))["missing"]
    assert none.value == "None" and none.extra is None


def test_the_decision_count_leaves_out_the_accept_all_line() -> None:
    """Design decision, 12 Nov 2026: "Accept all agreeing values" is not a decision. The count is conflicts plus
    values to review, and the agreeing values are shown apart."""
    from collections import OrderedDict

    from backend.app.enquiry import Decisions
    d = Decisions(groups=OrderedDict(), conflicts=[{}, {}], reasons=OrderedDict(medium=[1, 2, 3], ocr=[4]),
                  acceptable=[5] * 118, missing=[], not_read=[], busy=False, total=0, approved=0)
    assert d.needs == 2 + 4 and d.disagree == 2
    assert not hasattr(d, "cards")  # the old count that added one for the Accept all line is gone


def test_what_is_quoted_is_one_line_from_the_values() -> None:
    f = found()
    f.groups.update({"incomer.device": value("acb"), "incomer.rating": value(1250.0, "A"),
                     "system.voltage": value(400, "V"), "enclosure.form": value("4a"),
                     "enclosure.ip_rating": value("IP54")})
    assert tiles(found=f)["quoted"].value == "ACB incomer 1250 A, 400 V, form 4a, IP54"
    # A field the documents disagree on is left out: the agreement tile names it instead.
    f.groups["system.voltage"] = {"sides": [[NS(review_status="extracted", value=400, unit="V")],
                                            [NS(review_status="extracted", value=415, unit="V")]], "conflict": True}
    assert tiles(found=f)["quoted"].value == "ACB incomer 1250 A, form 4a, IP54"
    empty = NS(conflicts=[], disagree=0, needs=0, approved=0, missing=[], groups={})
    assert tiles(found=empty)["quoted"].value == "Nothing read from the files yet"
