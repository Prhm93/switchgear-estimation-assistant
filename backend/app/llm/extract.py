"""LLM extraction: one model call per page, every value checked against its quote.

For each page with text, the model gets the system prompt (documents are data,
never instructions) and the page, and answers in the :class:`PageReading`
schema. Then, per value:

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


class LlmResult(BaseModel):
    values: list[ExtractedValue]
    rejected: list[Rejection]
    model: str
    calls: int


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


def llm_extract(kind: DocumentKind, pages: list[PageText], file: str, provider: ModelProvider) -> LlmResult:
    """Ask the model about every page and keep only the values whose quotes check out."""
    values: list[ExtractedValue] = []
    rejected: list[Rejection] = []
    calls = 0
    schema = output_schema()
    for page in pages:
        material = page_material(page)
        if not material.strip():
            continue
        prompt = page_prompt(kind.value, page)
        if isinstance(provider, RecordingProvider):
            reply = provider.generate(SYSTEM_PROMPT, prompt, schema, key=f"{file} page {page.number}")
        else:
            reply = provider.generate(SYSTEM_PROMPT, prompt, schema)
        calls += 1
        flags = find_instructions(page.number, material)
        try:
            items = json.loads(reply.content).get("values", [])
            if not isinstance(items, list):
                raise TypeError("values is not a list")
        except (json.JSONDecodeError, AttributeError, TypeError) as error:
            rejected.append(Rejection(page=page.number, field=None, reason=f"reply is not valid JSON ({error})"))
            continue
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
    return LlmResult(values=dedupe(values), rejected=rejected, model=provider.model, calls=calls)


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
