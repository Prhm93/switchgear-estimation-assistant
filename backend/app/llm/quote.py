"""The quote check: a model value is kept only if its quote is really on the page.

Two tests, both must pass:

1. The quote, after collapsing runs of spaces and ignoring case, occurs in the
   page text the model was shown (:func:`backend.app.llm.prompt.page_material`).
2. The number check from the AI engine (``find_numbers``, the same check that
   guards the agent's answers): every number in the value appears among the
   numbers of the quote. Number words count too ("eleven" is 11), so a value
   read from "eleven outgoing ways" passes, and a value of 12 does not.

A value that fails is rejected with a reason and never stored as extracted.
"""

from __future__ import annotations

import re

from estimation_assistant.checks import find_numbers
from pydantic import BaseModel

NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
                "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


class QuoteCheck(BaseModel):
    ok: bool
    reason: str | None = None  # why it failed
    source_text: str | None = None  # the quote as printed on the page (original case and spacing)


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
        return QuoteCheck(ok=False, reason="quote not found on the page")
    if value is not None and not isinstance(value, bool):
        missing = sorted({round(n, 2) for n in find_numbers(str(value))} - numbers_in(quote))
        if missing:
            shown = ", ".join(f"{n:g}" for n in missing)
            return QuoteCheck(ok=False, reason=f"number {shown} of the value is not in the quote")
    return QuoteCheck(ok=True, source_text=locate(quote, page_text) or quote.strip())
