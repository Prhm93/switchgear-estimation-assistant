"""Score extracted values against an answer key: precision, recall and F1 per field.

When a value counts as correct
------------------------------
An extracted value is a **true positive** when an answer-key entry has

- the same field (``way.Q3.rating``),
- the same source document (specification, schematic or requirements),
- the same page (for a drawing: the sheet), and
- the same value and unit after normalising (:mod:`backend.app.normalise`:
  numbers as numbers, text case-insensitive with spaces collapsed, device and
  meter words mapped to codes, unit spellings unified). A "TBC" in the
  document is an answer-key value of ``None``; extracting ``None`` there is
  correct, any number there is wrong.

Duplicates and pages
--------------------
Matching is one to one: an extracted value matches at most one answer-key
entry and an answer-key entry is matched by at most one extracted value. A
second extraction of the same statement is a false positive. The answer key
records each statement on its page, so a value that appears on several pages
counts once per page where the key lists it; finding it on a page where the
key does not list it is a false positive, and missing it on a listed page is a
false negative. Unmatched extracted values are false positives, unmatched
answer-key entries are false negatives.

Fields are reported grouped, with the way number replaced by ``*``
(``way.*.rating``), and over all fields (micro-averaged).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from backend.app import normalise as norm
from backend.app.schemas import ExtractedValue
from data_generator.schemas import TruthValue


class Score(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if p + r else 0.0

    def add(self, other: Score) -> None:
        self.tp, self.fp, self.fn = self.tp + other.tp, self.fp + other.fp, self.fn + other.fn


def field_group(field: str) -> str:
    return re.sub(r"^way\.[^.]+\.", "way.*.", field)


def _key(field: str, document: str, page: int | None) -> tuple[str, str, int | None]:
    return field, document, page


def score(extracted: Iterable[ExtractedValue], truth: Iterable[TruthValue]) -> dict[str, Score]:
    """Scores per field group, one-to-one matching as described in the module docstring."""
    pending: dict[tuple, list[TruthValue]] = defaultdict(list)
    for t in truth:
        pending[_key(t.field, t.source.document.value, t.source.page)].append(t)
    out: dict[str, Score] = defaultdict(Score)
    for e in extracted:
        group = field_group(e.field)
        candidates = pending.get(_key(e.field, e.source.document.value, e.source.page), [])
        hit = next((t for t in candidates if norm.same(t.value, t.unit, e.value, e.unit)), None)
        if hit is not None:
            candidates.remove(hit)
            out[group].tp += 1
        else:
            out[group].fp += 1
    for left in pending.values():
        for t in left:
            out[field_group(t.field)].fn += 1
    return dict(out)


def total(scores: dict[str, Score]) -> Score:
    all_ = Score()
    for s in scores.values():
        all_.add(s)
    return all_
