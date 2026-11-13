"""Confidence and review risk (Stage 6): how sure the app is of each value, and what to check first.

A value's level comes from three things, in this order:

1. **How it was read** (:func:`base_level`): the rules reading a file's text are ``high``; a model with an
   exact quote is ``medium`` and with a pieced quote ``low``; OCR and the vision model keep their own level
   but never above ``medium``; the symbol detector is ``low``; a flag (poles from a cable core count) makes it
   ``low``. A value the engineer approved or typed is ``high``.
2. **Whether there is a conflict**: two live values of one field that differ, where at least one is high,
   make every value of the field ``conflict``. Two lower values that differ (model against model, picture
   against model) are a **weak difference**: each is ``low`` with a reason, checked on its own, and never a
   conflict card. A difference between two unreliable readings is as likely a misreading as a real conflict,
   and both are checked one by one anyway.
3. **Whether files agree**: another file giving the same value raises the level one step, up to ``high``
   for the rules and a model with an exact quote, and up to ``medium`` for a picture or a pieced quote.

Only ``high`` values read by the rules (no model, no picture, no flag) may be accepted in bulk
(``bulk_ok``); everything else is ticked by a person. ``risk`` orders the review queue: conflict, then
low, medium and high, and within a level the less reliable method first.

Nothing here changes stored values or decides anything: it is worked out each time a screen is shown.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.app.crosscheck import DONE, Seen, is_placeholder, value_key

ORDER = ["low", "medium", "high"]
PICTURE = {"ocr", "vision", "detector"}
MODEL = {"llm"}
# Within one level, the less reliable method is checked first.
METHOD_RISK = {"detector": 5, "vision": 4, "ocr": 3, "llm": 2, "rules": 1}
LEVEL_RISK = {"conflict": 40, "low": 30, "medium": 20, "high": 10}
DOCUMENT_WORDS = {"specification": "the specification", "schematic": "the drawing", "requirements": "the letter"}


@dataclass
class Assessment:
    level: str  # high, medium, low or conflict
    reasons: list[str] = field(default_factory=list)  # plain words: why this level
    risk: int = 0  # higher is checked first
    bulk_ok: bool = False  # may be accepted with the agreeing values
    weak_difference: bool = False  # another lower reading gives a different value


def _step(level: str, cap: str) -> str:
    i = min(ORDER.index(level) + 1, ORDER.index(cap))
    return ORDER[max(i, ORDER.index(level))]


def _cap(level: str, cap: str) -> str:
    return ORDER[min(ORDER.index(level), ORDER.index(cap))]


def base_level(s: Seen) -> str:
    """The level from how the value was read alone (step 1 of the module docstring)."""
    if s.status in DONE:
        return "high"
    if "poles_from_cable_cores" in s.flags:
        return "low"
    own = s.confidence if s.confidence in ORDER else "medium"
    if s.method in MODEL:
        if s.quote_match == "words_on_page":
            return "low"
        return _cap(own, "medium")
    if s.method == "detector":
        return "low"
    if s.method in PICTURE:
        return _cap(own, "medium")
    return own if s.confidence else "high"


def _how(s: Seen) -> str:
    if s.status in DONE:
        return "Approved by the engineer"
    if s.method in MODEL:
        return ("Read by a model; its quote was pieced together" if s.quote_match == "words_on_page"
                else "Read by a model, with an exact quote")
    if s.method == "detector":
        return "Found by the symbol detector on a drawing picture"
    if s.method in PICTURE:
        return "Read from a drawing picture"
    return "Read by the rules from the file's text"


def _ceiling(s: Seen) -> str:
    """How high agreement may take a value."""
    if s.status in DONE or s.method == "rules" or (s.method in MODEL and s.quote_match != "words_on_page"):
        return "high"
    return "medium"


def assess(seen: Iterable[Seen]) -> dict[int | None, Assessment]:
    """One assessment per value (keyed by ``ref``); rejected values are left out."""
    live = [s for s in seen if s.status != "rejected"]
    by_field: dict[str, list[Seen]] = {}
    for s in live:
        by_field.setdefault(s.field, []).append(s)
    out: dict[int | None, Assessment] = {}
    for items in by_field.values():
        stated = [s for s in items if not is_placeholder(s.value)]
        keys = {id(s): value_key(s.value, s.unit) for s in stated}
        base = {id(s): base_level(s) for s in items}
        distinct = set(keys.values())
        differ = len(distinct) > 1
        conflict = differ and any(base[id(s)] == "high" for s in stated)
        for s in items:
            b = base[id(s)]
            reasons = [_how(s)]
            if is_placeholder(s.value):
                out[s.ref] = Assessment(level=b, reasons=reasons + ["No value given (for example TBC)"],
                                        risk=LEVEL_RISK["low"] + METHOD_RISK.get(s.method, 1))
                continue
            mine = keys[id(s)]
            if conflict:
                level, weak = "conflict", False
                reasons.append("Another value for this item differs, and one of them was read reliably")
            elif differ:
                level, weak = "low", True
                others = sorted({DOCUMENT_WORDS.get(o.document, o.document) for o in stated if keys[id(o)] != mine})
                reasons.append(f"Another reading ({', '.join(others)}) gives a different value")
            else:
                weak = False
                level = b
                agree = sorted({DOCUMENT_WORDS.get(o.document, o.document) for o in stated
                                if o.document != s.document and keys[id(o)] == mine})
                if agree:
                    level = _step(b, _ceiling(s))
                    reasons.append(f"{agree[0][0].upper()}{', '.join(agree)[1:]} agree{'s' if len(agree) == 1 else ''}")
            bulk = (level == "high" and s.method == "rules" and s.status not in DONE and not s.flags
                    and s.quote_match != "words_on_page")
            out[s.ref] = Assessment(level=level, reasons=reasons, risk=LEVEL_RISK[level] + METHOD_RISK.get(s.method, 1),
                                    bulk_ok=bulk, weak_difference=weak)
    return out
