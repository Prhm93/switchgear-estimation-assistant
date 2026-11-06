"""Normal forms for units and values, shared by the extractor, the scorer and the estimate.

Two values are "the same" when their normal forms are equal: numbers compare
as numbers (``"250"`` equals ``250.0``), text compares case-insensitively with
runs of spaces collapsed, and device words map onto the answer-key codes
(``"Switch-disconnector"`` and ``"SW-DISC"`` are both ``switch_disconnector``).
"""

from __future__ import annotations

import re

Scalar = str | int | float | None

UNITS = {"a": "A", "amp": "A", "amps": "A", "ka": "kA", "v": "V", "volt": "V", "volts": "V", "hz": "Hz",
         "mm": "mm", "m": "m", "mva": "MVA", "kw": "kW"}

DEVICES = {
    "acb": "acb", "air circuit breaker": "acb",
    "mccb": "mccb", "moulded-case circuit breaker": "mccb", "moulded case circuit breaker": "mccb",
    "mcb": "mcb", "miniature circuit breaker": "mcb",
    "switch-disconnector": "switch_disconnector", "switch disconnector": "switch_disconnector",
    "sw-disc": "switch_disconnector", "switch_disconnector": "switch_disconnector",
}

METERS = {"kwh": "kWh", "kwh energy meter": "kWh", "kwh meter": "kWh", "mfm": "MFM",
          "multifunction power meter (mfm)": "MFM", "multifunction power meter": "MFM",
          "multifunction meter": "MFM"}


def unit(u: str | None) -> str | None:
    if u is None:
        return None
    u = u.strip()
    return UNITS.get(u.lower(), u) if u else None


def device(text: str) -> str | None:
    return DEVICES.get(" ".join(text.lower().split()))


def meter(text: str) -> str | None:
    return METERS.get(" ".join(text.lower().split()))


def number(text: str) -> int | float | None:
    """``"250"`` -> 250, ``"2.5"`` -> 2.5; None when the text is not a plain number."""
    t = text.strip()
    if re.fullmatch(r"\d+", t):
        return int(t)
    if re.fullmatch(r"\d+\.\d+", t):
        return float(t)
    return None


def value_key(v: Scalar) -> Scalar:
    """The comparable form of a value."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    n = number(v)
    if n is not None:
        return float(n)
    return " ".join(str(v).split()).casefold()


def same(a: Scalar, unit_a: str | None, b: Scalar, unit_b: str | None) -> bool:
    return value_key(a) == value_key(b) and unit(unit_a) == unit(unit_b)
