"""Combined mode: rules and LLM values side by side, compared per field and page.

- Both methods read the same value on the same page: one value is kept (the
  rules one, with its rule name) and marked ``agree``; the LLM quote is noted
  in its derivation.
- They read different values on the same page: both are kept and marked
  ``disagree``. Nothing is decided here; Stage 6 turns agreement into
  confidence and the engineer resolves disagreements on the review screen.
- Only one method found the field on that page: kept, marked ``rules_only``
  or ``llm_only``.
"""

from __future__ import annotations

from collections import defaultdict

from backend.app import normalise as norm
from backend.app.schemas import Agreement, ExtractedValue


def _key(v: ExtractedValue) -> tuple[str, str, int | None]:
    return v.field, v.source.document.value, v.source.page


def _same(a: ExtractedValue, b: ExtractedValue) -> bool:
    return norm.same(a.value, a.unit, b.value, b.unit)


def combine(rules: list[ExtractedValue], llm: list[ExtractedValue]) -> list[ExtractedValue]:
    """Merge two methods' values; the input lists are not changed."""
    by_key: dict[tuple, list[ExtractedValue]] = defaultdict(list)
    for v in llm:
        by_key[_key(v)].append(v)
    out: list[ExtractedValue] = []
    unmatched_rules: list[ExtractedValue] = []
    for r in rules:
        candidates = by_key[_key(r)]
        twin = next((l for l in candidates if _same(r, l)), None)
        if twin is not None:
            candidates.remove(twin)
            note = f"rules and LLM read the same value; LLM quote: \"{twin.source.source_text}\""
            out.append(r.model_copy(update={"agreement": Agreement.AGREE,
                                            "derivation": f"{r.derivation}; {note}" if r.derivation else note}))
        else:
            unmatched_rules.append(r)
    rules_keys = {_key(r) for r in unmatched_rules}
    for r in unmatched_rules:
        state = Agreement.DISAGREE if by_key[_key(r)] else Agreement.RULES_ONLY
        out.append(r.model_copy(update={"agreement": state}))
    for l in (l for group in by_key.values() for l in group):
        state = Agreement.DISAGREE if _key(l) in rules_keys else Agreement.LLM_ONLY
        out.append(l.model_copy(update={"agreement": state}))
    return out
