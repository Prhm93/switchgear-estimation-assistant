"""Cross-checks between files (Stage 5): where the specification, the drawing and the letter differ.

A **difference** is a field for which two files give values that do not overlap at all, after
normalising (``250`` equals ``250 A``, ``ACB`` equals ``air circuit breaker``): for example the
specification says 630 A and the drawing 400 A. A way listed in one file but not in another is a
difference too (a quantity question).

Differences are flagged for the engineer and never resolved here: nothing is picked, approved or
rejected, and both sides keep their sources (file, page, value ids). Two readings of the **same** file
that disagree (the rules and the model, say) are not a difference between files; they stay a conflict
on Check, as before.

The same code runs on extracted values (the scorer, ``python -m backend.crosschecks``) and on stored
rows (the app), through :class:`Seen`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from backend.app import labels
from backend.app import normalise as norm

DOCUMENT_WORDS = {"specification": "the specification", "schematic": "the drawing", "requirements": "the letter"}
DOCUMENT_ORDER = {"specification": 0, "schematic": 1, "requirements": 2}  # the order sides and messages name files
DONE = ("approved", "edited")
WAY_FIELD = re.compile(r"^way\.([^.]+)\.")
# Text that states an item but no value: "TBC" and the placeholders a model may copy for it. Like a missing
# value (None), it is never a difference; the missing-information list names it instead.
PLACEHOLDERS = {"", "tbc", "tba", "-", "n/a", "na"}
Kind = Literal["rating", "poles", "device", "quantity", "other"]


@dataclass(frozen=True)
class Seen:
    """One value as a cross-check sees it."""

    field: str
    value: Any
    unit: str | None
    document: str  # document kind: specification, schematic, requirements
    file: str
    page: int | None
    ref: int | None = None  # the stored value's id, when there is one
    # How it was read (Stage 6, for confidence): method, quote match, the reading's own level, flags, review status.
    method: str = "rules"
    quote_match: str | None = None
    confidence: str | None = None
    flags: tuple[str, ...] = ()
    status: str = "extracted"


def seen_from_values(values: Iterable[Any]) -> list[Seen]:
    """From extracted values (pipeline output)."""
    return [Seen(v.field, v.value, v.unit, v.source.document.value, v.source.file, v.source.page, ref,
                 method=v.method.value, quote_match=v.quote_match.value if v.quote_match else None,
                 confidence=v.confidence.value, flags=tuple(f.value for f in v.flags),
                 status=v.review_status.value)
            for ref, v in enumerate(values) if v.review_status.value != "rejected"]


def seen_from_rows(rows: Iterable[Any], *, as_read: bool = False) -> list[Seen]:
    """From stored rows: the engineer's value once approved or edited, rejected rows left out.

    ``as_read``: every row with the value as read, whatever the engineer decided since (the Review cards
    keep a settled conflict as one group).
    """
    out = []
    for r in rows:
        if r.review_status == "rejected" and not as_read:
            continue
        done = r.review_status in DONE and not as_read
        value, unit = (r.approved_value, r.approved_unit) if done else (r.value, r.unit)
        out.append(Seen(r.field, value, unit, r.source_document, getattr(r, "source_file", ""), r.page, r.id,
                        method=getattr(r, "method", "rules"), quote_match=getattr(r, "quote_match", None),
                        confidence=getattr(r, "confidence", None), flags=tuple(getattr(r, "flags", None) or ()),
                        status="extracted" if as_read else r.review_status))
    return out


def value_key(value: Any, unit: str | None) -> tuple[Any, str | None]:
    """The comparable form: device words by their plain name, then numbers and text as the scorer compares them."""
    if isinstance(value, str) and (device := norm.device(value)):
        return device, None
    return norm.value_key(value), norm.unit(unit)


class Side(BaseModel):
    document: str
    value: Any
    unit: str | None
    sources: list[dict[str, Any]]  # file, page, ref


class Difference(BaseModel):
    """Two or more files disagree on one field. Flagged for the engineer; never resolved in code."""

    field: str
    label: str
    kind: Kind
    sides: list[Side]
    message: str


def kind_of(field: str) -> Kind:
    if field == "ways.count":
        return "quantity"
    if field.endswith(".rating") or field.endswith(".breaking_capacity"):
        return "rating"
    if field.endswith(".poles"):
        return "poles"
    if field.endswith(".device"):
        return "device"
    return "other"


def is_placeholder(value: Any) -> bool:
    """No value stated: None, or placeholder text such as "TBC", "-" or "N/A"."""
    return value is None or (isinstance(value, str) and value.strip().lower() in PLACEHOLDERS)


def _ordered(documents: Iterable[str]) -> list[str]:
    return sorted(documents, key=lambda d: (DOCUMENT_ORDER.get(d, len(DOCUMENT_ORDER)), d))


def _words(document: str) -> str:
    return DOCUMENT_WORDS.get(document, document)


def _reliable(items: Iterable[Seen]) -> bool:
    """At least one value read reliably (high before any agreement): the Stage 6 gate."""
    from backend.app.confidence import base_level

    return any(base_level(x) == "high" for x in items)


def differences(seen: list[Seen], *, gate: bool = False) -> list[Difference]:
    """Every field on which two files give values that do not overlap, then every way missing from a file.

    ``gate`` (Stage 6): two files are apart only when at least one of them gives a value read reliably
    (high confidence before agreement: the rules on the file's text, or the engineer). A difference between
    two lower readings (model against model, picture against model) is left to each value's own check.
    """
    by_field: dict[str, dict[str, dict[tuple, list[Seen]]]] = {}
    for s in seen:
        if is_placeholder(s.value):  # "TBC" states the item but no value: a missing value, not a difference
            continue
        by_field.setdefault(s.field, {}).setdefault(s.document, {}).setdefault(value_key(s.value, s.unit), []).append(s)
    out: list[Difference] = []
    for field, docs in by_field.items():
        names = _ordered(docs)
        def counts(a: str, b: str) -> bool:
            if set(docs[a]) & set(docs[b]):
                return False
            return not gate or _reliable(x for d in (a, b) for items in docs[d].values() for x in items)
        apart = any(counts(a, b) for i, a in enumerate(names) for b in names[i + 1:])
        if not apart:
            continue
        sides = []
        for doc in names:
            for items in docs[doc].values():
                first = items[0]
                sources = sorted({(x.file, x.page, x.ref) for x in items}, key=lambda t: (t[0], t[1] or 0, t[2] or 0))
                sides.append(Side(document=doc, value=first.value, unit=first.unit,
                                  sources=[{"file": f, "page": p, "ref": r} for f, p, r in sources]))
        said = "; ".join(f"{_words(s.document)} says {labels.display(s.value, s.unit)}" for s in sides)
        out.append(Difference(field=field, label=labels.field_label(field), kind=kind_of(field), sides=sides,
                              message=said[0].upper() + said[1:]))
    out += missing_ways(seen, gate=gate)
    return out


def missing_ways(seen: list[Seen], *, gate: bool = False) -> list[Difference]:
    """A way listed in one file but not in another file that lists ways (a quantity question).

    ``gate`` (Stage 6): flagged only when the way's own values or the listing of a file it is missing from
    include a value read reliably; two lower listings that differ are left to each value's own check.
    """
    listed: dict[str, dict[str, list[Seen]]] = {}
    for s in seen:
        if m := WAY_FIELD.match(s.field):
            listed.setdefault(m.group(1), {}).setdefault(s.document, []).append(s)
    listing = {d for docs in listed.values() for d in docs}
    if len(listing) < 2:
        return []
    # files whose list of ways includes a value read reliably: their silence about a way means something
    reliable_listing = {d for d in listing if _reliable(x for docs in listed.values() for x in docs.get(d, []))}
    out = []
    for way, docs in sorted(listed.items(), key=lambda kv: (len(kv[0]), kv[0])):
        absent = _ordered(listing - set(docs))
        if not absent:
            continue
        if gate and not (_reliable(x for d in docs for x in docs[d]) or set(absent) & reliable_listing):
            continue
        present = _ordered(docs)
        sides = [Side(document=d, value=way, unit=None,
                      sources=[{"file": x.file, "page": x.page, "ref": x.ref} for x in docs[d][:1]]) for d in present]
        message = (f"Way {way} is in {' and '.join(_words(d) for d in present)} but not in "
                   f"{' or '.join(_words(d) for d in absent)}")
        out.append(Difference(field=f"way.{way}", label=f"Way {way}", kind="quantity", sides=sides, message=message))
    return out
