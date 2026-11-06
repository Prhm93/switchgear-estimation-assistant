"""The customer's requirements letter, as a DOCX file (python-docx, MIT licence).

A short letter in plain words. Each sentence that states a value carries a
mark. A DOCX file has no fixed pages; the letter is written to fit on one
page and every mark is recorded as page 1.

python-docx stamps the current time on the zip entries and core properties;
both are fixed afterwards so the same seed gives the same bytes.
"""

from __future__ import annotations

import datetime as dt
import io
import random
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.shared import Pt

from data_generator.names import PANEL_BUILDER
from data_generator.views import DocView
from data_generator.wording import Wording

FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
FIXED_CORE_TIME = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


@dataclass
class LetterMark:
    field: str
    value: object
    unit: str | None
    text: str
    page: int = 1


def normalise_zip(data: bytes) -> bytes:
    """Rewrite a zip (DOCX) with fixed timestamps and the original entry order.

    Deflate at a fixed level is deterministic for a given zlib build; the PDF
    writers rely on the same property.
    """
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():  # keep the original order: [Content_Types].xml must come first
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            dst.writestr(info, src.read(name))
    return out.getvalue()


def build_letter(view: DocView, seed: int, path: Path) -> list[LetterMark]:
    """Write ``requirements.docx`` and return its marks."""
    d = view.design
    rng = random.Random(seed + 2)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.size = Pt(rng.choice([10.5, 11, 12]))  # the template's default font; no font file is embedded
    marks: list[LetterMark] = []

    def para(text: str, *ms: LetterMark) -> None:
        doc.add_paragraph(text)
        marks.extend(ms)

    def mk(fld: str, value, unit, text) -> LetterMark:
        return LetterMark(fld, value, unit, text)

    para(d.customer)
    para(d.site)
    para(d.issue_date)
    para(f"To: Estimating team, {PANEL_BUILDER}")
    para(f"Our reference: {d.enquiry_ref}")
    para(f"Subject: new main switchboard {d.board_name}")
    para(rng.choice(["Dear Sir or Madam,", "Dear Estimating Team,"]))
    para(f"We are building a new {d.building_use} at the address above and would like a price for the main "
         f"low-voltage switchboard. The specification and the drawing are attached.")

    if view.reword is None:
        if view.states("system.voltage"):
            t = rng.choice([f"The supply will be {d.voltage_v} V three phase from a site transformer.",
                            f"The board will be fed at {d.voltage_v} V, three phase and neutral."])
            para(t, mk("system.voltage", d.voltage_v, "V", t))
        if view.states("incomer.rating"):
            t = rng.choice([f"Please allow for an incoming air circuit breaker rated {d.incomer_rating_a} A.",
                            f"The incomer should be a {d.incomer_rating_a} A air circuit breaker."])
            para(t, mk("incomer.rating", d.incomer_rating_a, "A", t))
        t = rng.choice([f"We need {len(d.ways)} outgoing ways, as listed in the specification.",
                        f"There are {len(d.ways)} outgoing circuits in total."])
        para(t, mk("ways.count", len(d.ways), None, t))
        if view.states("enclosure.ip_rating"):
            t = rng.choice([f"The board will stand in a plant room, so it must be at least {d.ip_rating}.",
                            f"Please provide {d.ip_rating} protection, as the room can be dusty."])
            para(t, mk("enclosure.ip_rating", d.ip_rating, None, t))
        if view.states("enclosure.form"):
            t = f"Our consultant has asked for Form {d.form} separation."
            para(t, mk("enclosure.form", d.form, None, t))
        if view.states("enclosure.cable_entry"):
            t = rng.choice([f"All cables will come in from the {d.cable_entry}.",
                            f"Cable entry will be from the {d.cable_entry}."])
            para(t, mk("enclosure.cable_entry", d.cable_entry, None, t))
        if view.states("metering.meter"):
            words = "a multifunction meter" if d.meter == "MFM" else "a kWh meter"
            t = f"We would like {words} on the incomer so we can track energy use."
            para(t, mk("metering.meter", d.meter, None, t))

    else:
        _reworded_values(view, para, mk)
    para("Please send your price, lead time and any deviations from the specification within three weeks.")
    para("Yours faithfully,")
    para(d.contact)
    para(f"Facilities Manager, {d.customer}")

    core = doc.core_properties
    core.author = d.contact
    core.last_modified_by = d.contact
    core.title = f"Enquiry {d.enquiry_ref}"
    core.comments = ""
    core.revision = 1
    core.created = FIXED_CORE_TIME
    core.modified = FIXED_CORE_TIME
    core.last_printed = FIXED_CORE_TIME

    buf = io.BytesIO()
    doc.save(buf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalise_zip(buf.getvalue()))
    return marks


def _reworded_values(view: DocView, para, mk) -> None:
    """The value sentences of the letter in other words (reworded set)."""
    d = view.design
    w = Wording(view.reword)  # type: ignore[arg-type]
    sentences = []
    if view.states("system.voltage"):
        t = w.pick([f"Our electricity supply is {w.volts(d.voltage_v)}, three phase.",
                    f"The site has a {w.volts(d.voltage_v)} three-phase supply."])
        sentences.append((t, mk("system.voltage", d.voltage_v, "V", t)))
    if view.states("incomer.rating"):
        t = w.pick([f"For the main incomer we expect an ACB of about {w.amps(d.incomer_rating_a)}.",
                    f"The main breaker should be an air circuit breaker sized at {w.amps(d.incomer_rating_a)}."])
        sentences.append((t, mk("incomer.rating", d.incomer_rating_a, "A", t)))
    t = w.pick([f"In total the board feeds {w.count(len(d.ways))} outgoing circuits.",
                f"Please allow for {w.count(len(d.ways))} outgoing ways."])
    sentences.append((t, mk("ways.count", len(d.ways), None, t)))
    if view.states("enclosure.ip_rating"):
        t = w.pick([f"The room is dusty, so we need {w.ip(d.ip_rating)} as a minimum.",
                    f"Ingress protection of {w.ip(d.ip_rating)} is needed."])
        sentences.append((t, mk("enclosure.ip_rating", d.ip_rating, None, t)))
    if view.states("enclosure.form"):
        t = w.pick([f"The consultant wants {w.form(d.form)} segregation.",
                    f"Internal separation must be {w.form(d.form)}."])
        sentences.append((t, mk("enclosure.form", d.form, None, t)))
    if view.states("enclosure.cable_entry"):
        where = {"bottom": "below", "top": "above"}[d.cable_entry]
        t = w.pick([f"Cables will be brought in from {where}.", f"We plan {d.cable_entry}-entry cabling."])
        sentences.append((t, mk("enclosure.cable_entry", d.cable_entry, None, t)))
    if view.states("metering.meter"):
        t = f"Please include {w.pick(['a', 'one'])} {w.meter(d.meter)} on the incoming supply."
        sentences.append((t, mk("metering.meter", d.meter, None, t)))
    w.rng.shuffle(sentences)
    for t, m in sentences:
        para(t, m)
