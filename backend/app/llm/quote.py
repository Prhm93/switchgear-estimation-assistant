"""The quote check: a model value is kept only if its quote is really on the page.

Two tests, both must pass:

1. The quote, after collapsing runs of spaces and ignoring case, occurs in the
   page text the model was shown (:func:`backend.app.llm.prompt.page_material`).
2. The number check from the AI engine (``find_numbers``, the same check that
   guards the agent's answers): every number in the value appears among the
   numbers of the quote. Number words count too ("eleven" is 11), so a value
   read from "eleven outgoing ways" passes, and a value of 12 does not.

A value that fails is rejected with a reason and never stored as extracted.

The relaxed check (Stage 3c, :func:`check_quote_relaxed`, the app default)
runs the strict check first and keeps its result for every exact quote. Only a
quote that is not one continuous span gets a second chance, as
``words_on_page``, when all of these hold:

- it is not a placeholder: not bracketed, not "N/A", "TBC" or similar, and
  longer than 3 characters;
- every word of it is on the page (a quote with " | " may instead have every
  table cell on the page);
- the number check above passes;
- a ``*.rating`` value is a number, and not one the quote gives only as kA or
  mm2 (a breaking capacity or a cable size is never a rating).

Poles supported only by a cable core count ("4C", "4 core") are kept with the
flag ``poles_from_cable_cores``, for the engineer to check. The strict check
(:func:`check_quote`) is the fixed v2 baseline and is unchanged.
"""

from __future__ import annotations

import re
from enum import StrEnum

from estimation_assistant.checks import find_numbers
from pydantic import BaseModel, Field

from backend.app.schemas import QuoteMatch, ValueFlag


class QuoteCheckMode(StrEnum):
    """Which quote check extraction uses: ``strict`` (v2 baseline) or ``relaxed`` (app default since Stage 3c)."""

    STRICT = "strict"
    RELAXED = "relaxed"


PLACEHOLDERS = {"tbc", "tba", "n/a", "na", "none", "null", "-", "not stated", "not specified", "unknown", "varies"}
NOT_FOUND = "quote not found on the page"

NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
                "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


class QuoteCheck(BaseModel):
    ok: bool
    reason: str | None = None  # why it failed
    source_text: str | None = None  # the quote as printed on the page (original case and spacing)
    match: QuoteMatch | None = None  # how the quote was found, when ok
    flags: list[ValueFlag] = Field(default_factory=list)  # things for the engineer to check (relaxed check only)


def normalise(text: str) -> str:
    """Lower case, every run of whitespace one space, ends trimmed."""
    return " ".join(text.split()).casefold()


def locate(quote: str, page_text: str) -> str | None:
    """The text of the page that matches the quote (any spacing, any case), or None."""
    words = quote.split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(w) for w in words), re.IGNORECASE)
    match = pattern.search(page_text)
    return match.group(0) if match else None


def numbers_in(text: str) -> set[float]:
    found = {round(n, 2) for n in find_numbers(text)}
    found |= {float(NUMBER_WORDS[w.lower()]) for w in WORD_RE.findall(text)}
    return found


def check_quote(value: object, quote: str, page_text: str) -> QuoteCheck:
    """Check one value's quote against the text of its page."""
    if not quote or not quote.strip():
        return QuoteCheck(ok=False, reason="no quote")
    if normalise(quote) not in normalise(page_text):
        return QuoteCheck(ok=False, reason=NOT_FOUND)
    missing = _missing_numbers(value, quote)
    if missing:
        return QuoteCheck(ok=False, reason=missing)
    return QuoteCheck(ok=True, source_text=locate(quote, page_text) or quote.strip(), match=QuoteMatch.EXACT)


def _missing_numbers(value: object, quote: str) -> str | None:
    """The number check: the reason it fails, or None when every number of the value is in the quote."""
    if value is not None and not isinstance(value, bool):
        missing = sorted({round(n, 2) for n in find_numbers(str(value))} - numbers_in(quote))
        if missing:
            shown = ", ".join(f"{n:g}" for n in missing)
            return f"number {shown} of the value is not in the quote"
    return None


# --- the relaxed check (Stage 3c) ----------------------------------------------------------------------------

def is_placeholder(quote: str) -> bool:
    """A quote that cannot show where a value comes from: bracketed, "N/A", "TBC" and the like, or very short."""
    q = normalise(quote)
    return q.startswith("[") or q in PLACEHOLDERS or len(q) <= 3


def words_on_page(quote: str, page_text: str) -> bool:
    """Every word of the quote is on the page (or, for a quote with " | ", every table cell is)."""
    q, page = normalise(quote), normalise(page_text)
    if "|" in q and all(normalise(cell) in page for cell in q.split("|") if cell.strip()):
        return True
    return all(word in page for word in q.split())


_LEADING_NUMBER = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(a|amps?|p|-?\s*poles?)?\s*", re.IGNORECASE)


def _number(value: object) -> float | None:
    """The number of 400, "400", "800A", "250 A", "4P" or "4-pole"; None for "TBC" and other text."""
    if isinstance(value, bool) or value is None:
        return None
    match = _LEADING_NUMBER.fullmatch(str(value))
    return float(match.group(1)) if match else None


def _occurrences(n: float, quote: str, after: str) -> list[bool]:
    """For each place the number stands in the quote: True when ``after`` (a unit pattern) follows it."""
    text = str(int(n)) if n == int(n) else str(n)
    pattern = re.compile(r"(?<![\d.])" + re.escape(text) + r"(?![\d.])(" + after + r")?", re.IGNORECASE)
    return [m.group(1) is not None for m in pattern.finditer(quote)]


def rating_guard(field: str, value: object, quote: str) -> str | None:
    """Reject-only guard for a rescued rating: the reason it fails, or None.

    A rating must be a number ("TBC" is not), and a number the quote gives only
    as kA (a breaking capacity) or mm2 (a cable size) is not a rating. A bare
    "200" from a specification table row passes.
    """
    if not field.endswith(".rating"):
        return None
    n = _number(value)
    if n is None:
        return f"rating guard: {value!r} is not a number"
    places = _occurrences(n, quote, r"\s*(?:ka|mm2|mm²|sq ?mm)\b")
    if places and all(places):
        return f"rating guard: {n:g} is written as kA or mm2 in the quote"
    return None


def poles_from_cable_cores(field: str, value: object, quote: str) -> bool:
    """True when a poles value is supported only by a cable core count ("4C", "4 core")."""
    if not field.endswith(".poles"):
        return False
    n = _number(value)
    if n is None:
        return False
    places = _occurrences(n, quote, r"\s*(?:c\b|cores?\b)")
    return bool(places) and all(places)


def check_quote_relaxed(field: str, value: object, quote: str, page_text: str) -> QuoteCheck:
    """The strict check, plus a second chance for a quote whose words are all on the page (see the module doc)."""
    strict = check_quote(value, quote, page_text)
    if strict.ok or strict.reason != NOT_FOUND:
        return strict
    if is_placeholder(quote) or not words_on_page(quote, page_text):
        return strict
    missing = _missing_numbers(value, quote)
    if missing:
        return QuoteCheck(ok=False, reason=missing)
    guard = rating_guard(field, value, quote)
    if guard:
        return QuoteCheck(ok=False, reason=guard)
    flags = [ValueFlag.POLES_FROM_CABLE_CORES] if poles_from_cable_cores(field, value, quote) else []
    return QuoteCheck(ok=True, source_text=quote.strip(), match=QuoteMatch.WORDS_ON_PAGE, flags=flags)
