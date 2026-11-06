"""Reworded phrasing for the held-out reworded test set (Stage 3).

The rule extractor was written after reading the generator's sentence
templates, so its score on the original test set says little about new
documents. The reworded set states the same kinds of facts with different
wording: synonyms ("moulded case circuit breaker", "isolator"), number words
("eight outgoing ways"), unit styles ("4P", "4 pole", "four-pole", "400V",
"400 volts"), other clause and section order, and other table headings.

A :class:`Wording` is created from a seed and only used when a document view
has ``reword`` set, so the original set keeps its exact bytes. Every phrase is
chosen with its own random stream; each method returns the exact printed text,
which becomes the answer key's ``source_text``.
"""

from __future__ import annotations

import random

from data_generator.design import Device

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}


class Wording:
    """Phrase choices for one document, from one seed."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def pick(self, options: list[str]) -> str:
        return self.rng.choice(options)

    # --- units and numbers ---------------------------------------------------------------------

    def amps(self, a: int) -> str:
        return self.pick([f"{a}A", f"{a} A", f"{a} amps", f"{a} amperes"])

    def amps_short(self, a: int) -> str:
        """For table cells and drawing labels: no spelt-out unit."""
        return self.pick([f"{a}A", f"{a} A", f"In={a}A", f"{a}"])

    def kiloamps(self, ka: int) -> str:
        return self.pick([f"{ka}kA", f"{ka} kA", f"{ka} kiloamps"])

    def volts(self, v: int) -> str:
        return self.pick([f"{v}V", f"{v} V", f"{v} volts", f"{v}/{round(v / 3 ** 0.5)} V"])

    def hertz(self, hz: int) -> str:
        return self.pick([f"{hz}Hz", f"{hz} Hz", f"{hz} hertz"])

    def poles(self, p: int) -> str:
        word = NUMBER_WORDS.get(p, str(p))
        return self.pick([f"{p}P", f"{p} pole", f"{p}-pole", f"{word}-pole", f"{word} pole"])

    def poles_short(self, p: int) -> str:
        return self.pick([f"{p}P", f"{p} pole", f"{p}-pole", str(p)])

    def count(self, n: int) -> str:
        return self.pick([str(n), NUMBER_WORDS.get(n, str(n)), f"{NUMBER_WORDS.get(n, str(n))} ({n})"])

    # --- devices ------------------------------------------------------------------------------

    def device(self, d: Device) -> str:
        return self.pick({
            Device.MCCB: ["MCCB", "Moulded case circuit breaker", "Moulded-case CB", "MCCB (moulded case)"],
            Device.MCB: ["MCB", "Miniature circuit breaker", "Miniature CB"],
            Device.SWITCH_DISCONNECTOR: ["Switch-disconnector", "Switch disconnector", "Isolator",
                                         "Load-break switch-disconnector"],
        }[d])

    def device_label(self, d: Device) -> str:
        """Upper-case drawing label."""
        return self.pick({
            Device.MCCB: ["MCCB", "M.C.C.B."],
            Device.MCB: ["MCB", "M.C.B."],
            Device.SWITCH_DISCONNECTOR: ["SWITCH DISC.", "ISOLATOR", "SW DISCONNECTOR"],
        }[d])

    def entry(self, where: str) -> str:
        other = {"bottom": "below", "top": "above"}[where]
        return self.pick([f"{where} entry", f"entry from {other}", f"{where}-entry", f"from {other}"])

    def meter(self, meter: str) -> str:
        if meter == "MFM":
            return self.pick(["multi-function meter", "MFM power meter", "multifunction instrument (MFM)"])
        return self.pick(["kWh meter", "energy meter (kWh)", "kilowatt-hour meter"])

    def ct_ratio(self, ratio: str) -> str:
        primary, secondary = ratio.split("/")
        return self.pick([f"{ratio}A", f"{ratio} A", f"{primary}:{secondary}", f"{primary}/{secondary}"])

    def form(self, form: str) -> str:
        return self.pick([f"Form {form}", f"form {form}", f"Form {form.upper()}", f"type {form}"])

    def ip(self, ip: str) -> str:
        digits = ip[2:]
        return self.pick([ip, f"IP {digits}", f"IP-{digits}"])
