"""The structured answer the model must give for one page, as Pydantic models.

The JSON schema of :class:`PageReading` is sent to the model as its output
format, so the reply is a JSON object with a list of values. Each value names
an answer-key field, gives the value and unit, and carries ``quote``: the
exact words of the page it was read from. Items are validated one by one, so
one bad item is rejected (and logged) without losing the rest of the page.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Field names the model may use: the answer-key fields (data_generator/schemas.py) and nothing else.
PROJECT_FIELDS = (
    "system.voltage", "system.frequency", "system.fault_level", "system.earthing",
    "incomer.device", "incomer.rating", "incomer.poles",
    "busbar.rating", "metering.ct_ratio", "metering.meter",
    "enclosure.form", "enclosure.ip_rating", "enclosure.cable_entry", "enclosure.width", "enclosure.sections",
    "ways.count",
)
WAY_PROPERTIES = ("rating", "poles", "device", "breaking_capacity", "cable", "cable_length", "description")
FIELD_RE = re.compile(r"^(?:" + "|".join(re.escape(f) for f in PROJECT_FIELDS)
                      + r"|way\.Q[1-9]\d?\.(?:" + "|".join(WAY_PROPERTIES) + r"))$")

Scalar = str | int | float | None


class LlmValue(BaseModel):
    """One value the model read, with the exact quote it used."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="Answer-key field name, e.g. system.voltage or way.Q3.rating")
    value: Scalar = Field(description="The value: a number for ratings and counts, a short code otherwise")
    unit: str | None = Field(default=None, description="A, kA, V, Hz, mm or m; null when the field has none")
    quote: str = Field(min_length=1, max_length=300,
                       description="The exact words of this page the value was read from, copied character "
                                   "for character")

    @field_validator("field")
    @classmethod
    def _known_field(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_RE.match(value):
            raise ValueError(f"unknown field {value!r}")
        return value

    @field_validator("quote")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty quote")
        return value


class PageReading(BaseModel):
    """The model's whole answer for one page."""

    model_config = ConfigDict(extra="forbid")

    values: list[LlmValue] = Field(default_factory=list)


def output_schema() -> dict:
    """The JSON schema sent as the model's output format, with ``$defs`` inlined (no ``$ref``)."""
    schema = PageReading.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].split("/")[-1]])
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(schema)  # type: ignore[return-value]
