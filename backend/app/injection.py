"""Find instruction-like text in documents ("prompt injection"), to flag it, never to follow it.

Documents are data. A sentence that tries to steer an automated reader
("ignore all previous instructions", "approve every value", "set the total to
zero") is shown to the engineer with a red flag on the analysis and review
screens. LLM values quoted from a flagged sentence are rejected.

Detection is a small set of patterns in four groups. A sentence is flagged
when it tries to override instructions, or when it matches two or more of the
other groups (it speaks to a machine reader, asks for approval without review,
or tries to change a price or total). Limits: the patterns are English only
and were written by the same person who wrote the planted lines in the
generator, so they say little about attacks phrased in new ways.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from backend.app.llm.quote import locate

OVERRIDE = re.compile(r"\b(ignore|disregard|forget|override)\b[^.]{0,60}\b(instructions?|prompts?|rules|"
                      r"review(?:ing)? process)\b", re.IGNORECASE)
GROUPS = {
    "addresses a machine reader": re.compile(
        r"\b(AI|LLM|language model|chatbot|assistant|automated (?:review )?(?:tools?|readers?|systems?|review)|"
        r"system (?:note|prompt|message)|you must|you are now)\b", re.IGNORECASE),
    "asks for approval without review": re.compile(
        r"\b(approve|mark)\b[^.]{0,40}\b(every|all|everything)\b|\bwithout (?:review|checking)\b", re.IGNORECASE),
    "changes a price or total": re.compile(
        r"\b(total|price|estimate)\b[^.]{0,40}\bzero\b|\bprice of zero\b", re.IGNORECASE),
}
# A sentence ends at ".", "!" or "?" followed by a space or the end ("2.1" and "1.5 m" do not end one).
SENTENCE = re.compile(r".+?(?:[.!?](?=\s|$)|$)")


class InstructionFlag(BaseModel):
    """One flagged sentence: where it is and why."""

    page: int
    text: str  # as printed on the page
    reasons: list[str]


def sentence_reasons(sentence: str) -> list[str]:
    reasons = ["tries to override instructions"] if OVERRIDE.search(sentence) else []
    others = [name for name, pattern in GROUPS.items() if pattern.search(sentence)]
    if reasons or len(others) >= 2:
        return reasons + others
    return []


def blocks(text: str) -> list[str]:
    """Lines joined into blocks: a line starting with a lower-case letter continues the line before it."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if out and line[0].islower():
            out[-1] += " " + line
        else:
            out.append(line)
    return out


def find_instructions(page: int, text: str) -> list[InstructionFlag]:
    """Flag the instruction-like sentences of one page's text."""
    flags = []
    for block in blocks(text):
        for match in SENTENCE.finditer(block):
            sentence = match.group(0).strip()
            if len(sentence) < 12:
                continue
            reasons = sentence_reasons(sentence)
            if reasons:
                flags.append(InstructionFlag(page=page, text=locate(sentence, text) or sentence, reasons=reasons))
    return flags


def inside_flag(quote: str, flags: list[InstructionFlag]) -> bool:
    """True when a quote is part of a flagged sentence (such a value must not be used)."""
    q = " ".join(quote.split()).casefold()
    return bool(q) and any(q in " ".join(f.text.split()).casefold() for f in flags)
