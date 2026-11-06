"""LLM extraction: one model call per page, every value checked against its quote.

For each page with text, the model gets the system prompt (documents are data,
never instructions) and the page, and answers in the :class:`PageReading`
schema. A reply that is not valid JSON is usually one the model was cut off in
(the way-table pages are the longest replies): every complete item up to the
last closed one is kept for the checks below, and one rejection records "reply
cut off, N items kept". An empty reply is recorded as such. Then, per value:

1. schema check (known field name, a quote present), else rejected;
2. the value is brought to the answer key's form (``"250"`` -> 250,
   ``"Moulded case circuit breaker"`` -> ``mccb``, ``"ip 54"`` -> ``IP54``);
3. quote check (:mod:`backend.app.llm.quote`), else rejected;
4. a quote inside a flagged instruction-like sentence is rejected (this reason wins over the others).

Kept values have method ``llm`` and confidence ``medium`` (Stage 6 sets
confidence from method agreement). Rejected values are logged and returned
with their reason, so the caller can audit them; they never become
extracted values.
"""

from __future__ import annotations

import json
import logging
import re
from enum import StrEnum

from estimation_assistant.providers import ModelProvider, RecordingProvider
from pydantic import BaseModel, ValidationError

from backend.app import normalise as norm
from backend.app.injection import find_instructions, inside_flag
from backend.app.llm.prompt import SYSTEM_PROMPT, page_material, page_prompt
from backend.app.llm.quote import NUMBER_WORDS, check_quote
from backend.app.llm.schema import LlmValue, output_schema
from backend.app.reading import PageText
from backend.app.schemas import Confidence, DocumentKind, ExtractedValue, Method, SourceRef

log = logging.getLogger(__name__)

NUMERIC = re.compile(r"^(system\.(voltage|frequency|fault_level)|incomer\.(rating|poles)|busbar\.rating|"
                     r"enclosure\.(width|sections)|ways\.count|way\.Q\d+\.(rating|poles|breaking_capacity|"
                     r"cable_length))$")
UNIT_OF = {"system.voltage": "V", "system.frequency": "Hz", "system.fault_level": "kA", "incomer.rating": "A",
           "busbar.rating": "A", "metering.ct_ratio": "A", "enclosure.width": "mm"}
WAY_UNIT = {"rating": "A", "breaking_capacity": "kA", "cable_length": "m"}
DEVICE_WORDS = {"isolator": "switch_disconnector", "load-break switch-disconnector": "switch_disconnector",
                "moulded-case cb": "mccb", "miniature cb": "mcb", "air cb": "acb", "air circuit-breaker": "acb"}


class Rejection(BaseModel):
    """A model value that was not kept, and why."""

    page: int
    field: str | None
    value: object = None
    quote: str | None = None
    reason: str


class ReplyStatus(StrEnum):
    OK = "ok"  # valid JSON
    CUT_OFF = "cut_off"  # not valid JSON, and the text ends before the JSON does: the model stopped mid-reply
    EMPTY = "empty"  # no text at all
    INVALID = "invalid"  # not valid JSON for another reason (an error before the end of the text)


class ReplyInfo(BaseModel):
    """How one page's reply ended, for the cut-off counts in the evaluation."""

    page: int
    status: ReplyStatus
    items_kept: int = 0  # complete items passed on to the checks
    done_reason: str | None = None  # from the recording (schema 1.1) or the live reply; None in 1.0 recordings
    eval_count: int | None = None


class LlmResult(BaseModel):
    values: list[ExtractedValue]
    rejected: list[Rejection]
    model: str
    calls: int
    replies: list[ReplyInfo] = []


def salvage_items(text: str) -> list[object]:
    """Every complete item of the ``values`` list of a reply that stops part-way.

    Reads the items one by one with the standard JSON decoder and stops at the
    first one that is incomplete, so nothing is guessed or repaired: an item is
    either wholly in the reply or dropped.
    """
    m = re.search(r'"values"\s*:\s*\[', text)
    if not m:
        return []
    decoder = json.JSONDecoder()
    items: list[object] = []
    i = m.end()
    while True:
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text) or text[i] == "]":
            break
        try:
            item, i = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        items.append(item)
    return items


def parse_reply(text: str, salvage: bool = True) -> tuple[list[object], ReplyStatus, str | None]:
    """The items of one reply, how the reply ended, and the page-level rejection reason (None if none).

    ``salvage=False`` is the Stage 3 Part A parser (a reply that is not valid
    JSON loses the whole page); the evaluation keeps it to report old and new
    numbers side by side.
    """
    if not text.strip():
        return [], ReplyStatus.EMPTY, "reply is empty"
    try:
        items = json.loads(text).get("values", [])
        if not isinstance(items, list):
            raise TypeError("values is not a list")
        return items, ReplyStatus.OK, None
    except (json.JSONDecodeError, AttributeError, TypeError) as error:
        # Cut off: the decoder ran out of text (the error is at the very end, or a string never closes).
        # Anything else is malformed.
        at_end = isinstance(error, json.JSONDecodeError) and (error.pos >= len(text.rstrip())
                                                               or error.msg.startswith("Unterminated string"))
        status = ReplyStatus.CUT_OFF if at_end else ReplyStatus.INVALID
        if not salvage:
            return [], status, f"reply is not valid JSON ({error})"
        items = salvage_items(text)
        what = "reply cut off" if status == ReplyStatus.CUT_OFF else f"reply is not valid JSON ({error})"
        return items, status, f"{what}, {len(items)} items kept"


def expected_unit(field: str) -> str | None:
    if field in UNIT_OF:
        return UNIT_OF[field]
    m = re.match(r"^way\.Q\d+\.(\w+)$", field)
    return WAY_UNIT.get(m.group(1)) if m else None


def canonical(field: str, value: object, unit: str | None) -> tuple[object, str | None]:
    """The answer-key form of a model value. Only spelling changes; the value itself never does."""
    unit = expected_unit(field) if field == "metering.ct_ratio" else norm.unit(unit)
    if isinstance(value, str):
        text = " ".join(value.split())
        if NUMERIC.match(field):
            # "250", "250 A", "4P", "4-pole" -> the number; "four" -> 4. Anything else stays text (and will not score).
            m = re.match(r"(\d+(?:\.\d+)?)\s*-?\s*([A-Za-z]+)?", text)
            if m:
                value = norm.number(m.group(1))
                unit = unit or norm.unit(m.group(2))
            elif text.casefold() in NUMBER_WORDS:
                value = NUMBER_WORDS[text.casefold()]
        elif field.endswith("device"):
            value = norm.device(text) or DEVICE_WORDS.get(text.casefold()) or text.casefold()
        elif field == "metering.meter":
            value = norm.meter(text) or ("MFM" if "mfm" in text.casefold() or "multi" in text.casefold()
                                         else "kWh" if "kwh" in text.casefold() else text)
        elif field == "enclosure.form":
            value = re.sub(r"^(form|type)\s+", "", text, flags=re.IGNORECASE).lower()
        elif field == "enclosure.ip_rating":
            value = "IP" + re.sub(r"[^0-9X]", "", text.upper().removeprefix("IP"))
        elif field == "enclosure.cable_entry":
            low = text.casefold()
            value = "bottom" if ("bottom" in low or "below" in low) else "top" if ("top" in low or "above" in low) \
                else text
        elif field == "metering.ct_ratio":
            value = re.sub(r"\s*[:/]\s*", "/", text.upper().removesuffix("A").strip())
        elif field == "system.earthing":
            value = text.upper()
        else:
            value = text
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if NUMERIC.match(field):
        # Counts and poles have no unit ("4P" is not a unit); a missing unit of a rating is the field's own.
        unit = None if expected_unit(field) is None else (unit or expected_unit(field))
    return value, unit


def llm_extract(kind: DocumentKind, pages: list[PageText], file: str, provider: ModelProvider, *,
                system_prompt: str = SYSTEM_PROMPT, salvage: bool = True) -> LlmResult:
    """Ask the model about every page and keep only the values whose quotes check out.

    ``system_prompt`` is the current prompt; only the evaluation passes another
    one (an older recording's own prompt, to score it with the new parser).
    """
    values: list[ExtractedValue] = []
    rejected: list[Rejection] = []
    replies: list[ReplyInfo] = []
    calls = 0
    schema = output_schema()
    for page in pages:
        material = page_material(page)
        if not material.strip():
            continue
        prompt = page_prompt(kind.value, page)
        if isinstance(provider, RecordingProvider):
            reply = provider.generate(system_prompt, prompt, schema, key=f"{file} page {page.number}")
        else:
            reply = provider.generate(system_prompt, prompt, schema)
        calls += 1
        flags = find_instructions(page.number, material)
        items, status, page_reason = parse_reply(reply.content, salvage)
        replies.append(ReplyInfo(page=page.number, status=status, items_kept=len(items),
                                 done_reason=reply.done_reason, eval_count=reply.eval_count))
        if page_reason:
            rejected.append(Rejection(page=page.number, field=None, reason=page_reason))
        for item in items:
            try:
                v = LlmValue.model_validate(item)
            except ValidationError as error:
                field = item.get("field") if isinstance(item, dict) else None
                rejected.append(Rejection(page=page.number, field=field if isinstance(field, str) else None,
                                          value=item.get("value") if isinstance(item, dict) else None,
                                          quote=item.get("quote") if isinstance(item, dict) else None,
                                          reason="schema: " + "; ".join(e["msg"] for e in error.errors())))
                continue
            value, unit = canonical(v.field, v.value, v.unit)
            check = check_quote(v.value, v.quote, material)
            reason = check.reason if not check.ok else None
            if inside_flag(v.quote, flags):
                reason = "quote is inside instruction-like text"
            if reason is None and value is None:
                reason = "no value"
            if reason:
                rejected.append(Rejection(page=page.number, field=v.field, value=v.value, quote=v.quote,
                                          reason=reason))
                continue
            values.append(ExtractedValue(
                field=v.field, value=value, unit=unit, method=Method.LLM, confidence=Confidence.MEDIUM,
                rule=f"llm:{provider.model}",
                source=SourceRef(document=kind, file=file, page=page.number, source_text=check.source_text)))
    for r in rejected:
        log.info("LLM value rejected: page %s field %s value %r quote %r: %s", r.page, r.field, r.value, r.quote,
                 r.reason)
    return LlmResult(values=dedupe(values), rejected=rejected, model=provider.model, calls=calls, replies=replies)


def dedupe(values: list[ExtractedValue]) -> list[ExtractedValue]:
    """One value per field, page and normal form (a model may list the same fact twice)."""
    seen: set[tuple] = set()
    out = []
    for v in values:
        key = (v.field, v.source.page, norm.value_key(v.value), v.unit)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
