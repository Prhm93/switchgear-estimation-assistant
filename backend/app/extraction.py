"""Rule-based extraction: ratings, poles, form, IP rating, quantities and part types.

Every rule is a small, named pattern. A value is produced only where its
pattern matches, and it keeps the exact text it was read from and the page.
Nothing is assumed: a rating written "TBC" becomes a value of ``None``, and a
fault level printed without a unit keeps no unit (low confidence) rather
than being taken as kA.

Field names follow the answer key (``data_generator/schemas.py``), so the
results score directly against ``answers.json``.

Source text: for a clause that wraps over two PDF lines, the line break is
replaced by one space; otherwise the text is exactly as extracted.

Confidence in this stage is fixed per rule: a labelled clause, a table cell
under a known heading or a drawing label is ``high``; a value taken from the
customer's free-text letter is ``medium``; a value missing its unit, or a
"TBC", is ``low``. Stage 6 replaces this with agreement-based confidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from backend.app import normalise as norm
from backend.app.reading import DxfText, PageText
from backend.app.schemas import Confidence, DocumentKind, ExtractedValue, SourceRef

H, M, L = Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW


@dataclass
class Ctx:
    """Where the values being extracted come from."""

    document: DocumentKind
    file: str

    def value(self, field: str, value, unit: str | None, page: int, text: str, confidence: Confidence,
              rule: str, derivation: str | None = None) -> ExtractedValue:
        return ExtractedValue(field=field, value=value, unit=norm.unit(unit), confidence=confidence, rule=rule,
                              derivation=derivation,
                              source=SourceRef(document=self.document, file=self.file, page=page, source_text=text))


# --- Specification -------------------------------------------------------------------------------

CLAUSE_START = re.compile(r"^\d+(\.\d+)+\s")
HEADING = re.compile(r"^\d+\s+[A-Z]")
TABLE_CAPTION = re.compile(r"^Table\s+\d")


def paragraphs(page: PageText) -> list[str]:
    """Join wrapped clause lines: a clause starts with a number like ``4.2``; lines after it continue it."""
    out: list[str] = []
    for line in page.lines:
        starts_new = bool(CLAUSE_START.match(line) or HEADING.match(line) or TABLE_CAPTION.match(line))
        if out and not starts_new and CLAUSE_START.match(out[-1]) and not line.startswith("Page "):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


NUM = r"(\d+(?:\.\d+)?)"

# (rule name, field, pattern, unit group or None, value converter)
SPEC_CLAUSES: list[tuple[str, str, re.Pattern[str]]] = [
    ("spec.voltage", "system.voltage", re.compile(rf"Rated operational voltage:\s*{NUM}(?:\s*(V)\b)?")),
    ("spec.frequency", "system.frequency", re.compile(rf"Rated frequency:\s*{NUM}(?:\s*(Hz)\b)?")),
    ("spec.fault_level", "system.fault_level",
     re.compile(rf"Prospective fault level:\s*{NUM}(?:\s*(kA|MVA)\b)?(?:\s+for\s+\d+\s*s)?")),
]
EARTHING = re.compile(r"System earthing:\s*(TN-C-S|TN-S|TN-C|TT|IT)\b")
FORM = re.compile(r"Form of separation:\s*Form\s+(\d[a-b]?)\b")
IP = re.compile(r"Degree of protection:\s*(IP\d{2})\b")
ENTRY = re.compile(r"Cable entry:\s*(top|bottom) entry", re.IGNORECASE)
INCOMER = re.compile(r"Incomer:\s*one (air circuit breaker|moulded-case circuit breaker),\s*(\d+)\s*A,\s*(\d)\s*pole"
                     r"(?:,\s*withdrawable)?")
BUSBAR = re.compile(r"Main busbars:\s*rated\s+(\d+)\s*A(?:,\s*TP&N)?(?:,\s*copper)?")
WAYS = re.compile(r"(?:The board shall have|There are|We need)\s+(\d+)\s+outgoing (?:ways|circuits)")
CTS = re.compile(r"(?:three|\d+) current transformers,\s*ratio\s+(\d+/\d+)\s*(A)?")
METER = re.compile(r"feeding an? (kWh energy meter|multifunction power meter \(MFM\))")


def _spec_text_rules(ctx: Ctx, page: int, text: str) -> Iterator[ExtractedValue]:
    for rule, field, pattern in SPEC_CLAUSES:
        if m := pattern.search(text):
            value, unit = norm.number(m.group(1)), m.group(2)
            yield ctx.value(field, value, unit, page, m.group(0), H if unit else L, rule)
    if m := EARTHING.search(text):
        yield ctx.value("system.earthing", m.group(1), None, page, m.group(0), H, "spec.earthing")
    if m := FORM.search(text):
        yield ctx.value("enclosure.form", m.group(1), None, page, m.group(0), H, "spec.form")
    if m := IP.search(text):
        yield ctx.value("enclosure.ip_rating", m.group(1).upper(), None, page, m.group(0), H, "spec.ip_rating")
    if m := ENTRY.search(text):
        yield ctx.value("enclosure.cable_entry", m.group(1).lower(), None, page, m.group(0), H, "spec.cable_entry")
    if m := INCOMER.search(text):
        src = m.group(0)
        yield ctx.value("incomer.device", norm.device(m.group(1)), None, page, src, H, "spec.incomer")
        yield ctx.value("incomer.rating", int(m.group(2)), "A", page, src, H, "spec.incomer")
        yield ctx.value("incomer.poles", int(m.group(3)), None, page, src, H, "spec.incomer")
    if m := BUSBAR.search(text):
        yield ctx.value("busbar.rating", int(m.group(1)), "A", page, m.group(0), H, "spec.busbar")
    if m := WAYS.search(text):
        yield ctx.value("ways.count", int(m.group(1)), None, page, m.group(0), H, "spec.ways_count")
    if m := CTS.search(text):
        yield ctx.value("metering.ct_ratio", m.group(1), m.group(2), page, m.group(0), H if m.group(2) else L,
                        "spec.ct_ratio")
    if m := METER.search(text):
        yield ctx.value("metering.meter", norm.meter(m.group(1)), None, page, m.group(0), H, "spec.meter")


# Electrical characteristics given as a two-column table: the label decides the field.
CHARACTERISTICS = {
    "rated operational voltage": ("system.voltage", re.compile(rf"^{NUM}(?:\s*(V))?$")),
    "rated frequency": ("system.frequency", re.compile(rf"^{NUM}(?:\s*(Hz))?$")),
    "prospective fault level": ("system.fault_level", re.compile(rf"^{NUM}(?:\s*(kA|MVA))?(?:\s+for\s+\d+\s*s)?$")),
    "system earthing": ("system.earthing", re.compile(r"^(TN-C-S|TN-S|TN-C|TT|IT)$")),
}

# Outgoing-way table: header words -> column role.
WAY_COLUMNS = {"way": "way", "description": "description", "device": "device", "rating": "rating",
               "rating (a)": "rating", "poles": "poles", "breaking capacity": "breaking_capacity",
               "icu (ka)": "breaking_capacity", "cable": "cable"}
HEADER_UNITS = {"rating (a)": "A", "icu (ka)": "kA"}
WAY_ID = re.compile(r"^Q\d+$")
CELL_NUMBER = re.compile(rf"^{NUM}(?:\s*(A|kA))?$")


def _cell(c: str | None) -> str:
    return " ".join((c or "").split())


def _characteristics_table(ctx: Ctx, page: int, rows: list[list[str | None]]) -> Iterator[ExtractedValue]:
    for row in rows:
        if len(row) != 2:
            continue
        label, printed = _cell(row[0]).lower(), _cell(row[1])
        if label not in CHARACTERISTICS:
            continue
        field, pattern = CHARACTERISTICS[label]
        if not (m := pattern.match(printed)):
            continue
        if field == "system.earthing":
            yield ctx.value(field, m.group(1), None, page, printed, H, "spec.table.characteristic")
        else:
            unit = m.group(2)
            yield ctx.value(field, norm.number(m.group(1)), unit, page, printed, H if unit else L,
                            "spec.table.characteristic")


def _ways_table(ctx: Ctx, page: int, rows: list[list[str | None]]) -> Iterator[ExtractedValue]:
    header = [_cell(c).lower() for c in rows[0]]
    roles = [WAY_COLUMNS.get(h) for h in header]
    if "way" not in roles or "device" not in roles:
        return
    for row in rows[1:]:
        cells = {roles[i]: _cell(c) for i, c in enumerate(row) if i < len(roles) and roles[i]}
        way = cells.get("way", "")
        if not WAY_ID.match(way):
            continue
        f = f"way.{way}"
        if desc := cells.get("description"):
            yield ctx.value(f"{f}.description", desc, None, page, desc, H, "spec.table.way")
        if (dev := cells.get("device")) and norm.device(dev):
            yield ctx.value(f"{f}.device", norm.device(dev), None, page, dev, H, "spec.table.way")
        for role, field in (("rating", "rating"), ("poles", "poles"), ("breaking_capacity", "breaking_capacity")):
            text = cells.get(role)
            if not text or text == "-":
                continue
            col_unit = HEADER_UNITS.get(header[roles.index(role)])
            if text.upper() == "TBC":
                yield ctx.value(f"{f}.{field}", None, None, page, text, L, "spec.table.tbc",
                                derivation="stated as TBC: no value given")
                continue
            if m := CELL_NUMBER.match(text):
                unit = None if role == "poles" else (m.group(2) or col_unit)
                yield ctx.value(f"{f}.{field}", norm.number(m.group(1)), unit, page, text,
                                H if (unit or role == "poles") else L, "spec.table.way")
        if cable := cells.get("cable"):
            yield ctx.value(f"{f}.cable", cable, None, page, cable, H, "spec.table.way")


def extract_specification(pages: list[PageText], file: str) -> list[ExtractedValue]:
    ctx = Ctx(DocumentKind.SPECIFICATION, file)
    out: list[ExtractedValue] = []
    for page in pages:
        for para in paragraphs(page):
            out += _spec_text_rules(ctx, page.number, para)
        for table in page.tables:
            if not table:
                continue
            out += _characteristics_table(ctx, page.number, table)
            out += _ways_table(ctx, page.number, table)
    return out


# --- Requirements letter -------------------------------------------------------------------------

LETTER_RULES: list[tuple[str, str, re.Pattern[str], str | None]] = [
    ("letter.voltage", "system.voltage", re.compile(r"(?:supply will be|fed at)\s+(\d+)\s*V\b"), "V"),
    ("letter.incomer_rating", "incomer.rating",
     re.compile(r"(?:(\d+)\s*A air circuit breaker|air circuit breaker rated\s+(\d+)\s*A)"), "A"),
    ("letter.ways_count", "ways.count", re.compile(r"\b(\d+) outgoing (?:ways|circuits)"), None),
    ("letter.ip_rating", "enclosure.ip_rating", re.compile(r"\b(IP\d{2})\b"), None),
    ("letter.form", "enclosure.form", re.compile(r"\bForm (\d[a-b]?) separation"), None),
    ("letter.cable_entry", "enclosure.cable_entry",
     re.compile(r"[Cc]ables?\b.*\bfrom the (top|bottom)\b"), None),
    ("letter.meter", "metering.meter", re.compile(r"\b(kWh|multifunction) meter\b"), None),
]


def extract_letter(pages: list[PageText], file: str) -> list[ExtractedValue]:
    """Free-text letter: the whole sentence is the source; confidence medium."""
    ctx = Ctx(DocumentKind.REQUIREMENTS, file)
    out: list[ExtractedValue] = []
    for page in pages:
        for line in page.lines:
            for rule, field, pattern, unit in LETTER_RULES:
                if not (m := pattern.search(line)):
                    continue
                raw = next(g for g in m.groups() if g)
                if field == "metering.meter":
                    value = norm.meter(f"{raw} meter")
                elif field in ("enclosure.ip_rating",):
                    value = raw.upper()
                elif field == "enclosure.cable_entry":
                    value = raw.lower()
                else:
                    value = norm.number(raw) if norm.number(raw) is not None else raw
                out.append(ctx.value(field, value, unit, page.number, line, M, rule))
    return out


# --- Drawing (DXF text entities) -------------------------------------------------------------

SUPPLY = re.compile(r"^INCOMING SUPPLY (\d+)V\b.*?\b(\d+)Hz$")
D_ACB = re.compile(r"^ACB (\d+)A (\d)P\b")
D_CT = re.compile(r"^CT (\d+/\d+)A$")
D_BUS = re.compile(r"^BUSBAR (\d+)A TP&N(?: (\d+)kA 1s)?$")
D_NOTES = [
    ("enclosure.form", re.compile(r"FORM OF SEPARATION: FORM (\d[a-bA-B]?)$"), str.lower),
    ("enclosure.ip_rating", re.compile(r"DEGREE OF PROTECTION: (IP\d{2})$"), str.upper),
    ("enclosure.cable_entry", re.compile(r"CABLE ENTRY: (TOP|BOTTOM)$"), str.lower),
    ("system.earthing", re.compile(r"EARTHING SYSTEM: (TN-C-S|TN-S|TN-C|TT|IT)$"), str.upper),
]
D_RATING = re.compile(r"^(MCCB|MCB|SW-DISC)\b(.*)$")
D_WIDTH = re.compile(r"^OVERALL WIDTH (\d+) mm - (\d+) SECTIONS$")


def _way_labels(items: list[DxfText]) -> list[DxfText]:
    """Way labels on the diagram (Q1, Q2, ...): upright, above the rotated rating texts."""
    rotated = [t for t in items if abs(t.rotation) > 1 and D_RATING.match(t.text)]
    if not rotated:
        return []
    top = max(t.y for t in rotated)
    return sorted((t for t in items if WAY_ID.match(t.text) and abs(t.rotation) < 1 and t.y > top),
                  key=lambda t: t.x)


def _owner(labels: list[DxfText], x: float) -> DxfText | None:
    """The way a rotated text belongs to: the nearest label to its left."""
    left = [lb for lb in labels if lb.x <= x]
    return left[-1] if left else None


def _schedule(ctx: Ctx, page: int, items: list[DxfText]) -> Iterator[ExtractedValue]:
    """Cable schedule: header row WAY / CABLE / LEN (m), rows grouped by height on the sheet."""
    header = {t.text: t for t in items if t.text in ("WAY", "CABLE", "LEN (m)") and abs(t.rotation) < 1}
    if not {"WAY", "CABLE"} <= header.keys():
        return
    hy = header["WAY"].y
    cols = sorted(t.x for t in items if abs(t.y - hy) < 0.5 and abs(t.rotation) < 1)
    last_width = min(cols[-1] - cols[-2], 15.0) if len(cols) > 1 else 15.0  # LEN (m) holds short numbers

    def column(x: float) -> float | None:
        """The header column a text sits under; None outside the schedule (title block, notes)."""
        if x < cols[0] - 0.5 or x >= cols[-1] + last_width:
            return None
        return max(c for c in cols if c <= x + 0.5)

    rows: dict[float, dict[float, str]] = {}
    for t in items:
        if t.y < hy - 0.5 and abs(t.rotation) < 1 and (col := column(t.x)) is not None:
            rows.setdefault(round(t.y, 1), {})[col] = t.text
    for cells in rows.values():
        way = cells.get(header["WAY"].x, "")
        if not WAY_ID.match(way):
            continue
        if cable := cells.get(header["CABLE"].x):
            yield ctx.value(f"way.{way}.cable", cable, None, page, cable, H, "dxf.schedule")
        if "LEN (m)" in header and (length := cells.get(header["LEN (m)"].x)) and norm.number(length) is not None:
            yield ctx.value(f"way.{way}.cable_length", norm.number(length), "m", page, length, H, "dxf.schedule")


def _sheet(ctx: Ctx, page: PageText) -> Iterator[ExtractedValue]:
    n, items = page.number, page.items
    for t in items:
        s = t.text
        if m := SUPPLY.match(s):
            yield ctx.value("system.voltage", int(m.group(1)), "V", n, s, H, "dxf.supply")
            yield ctx.value("system.frequency", int(m.group(2)), "Hz", n, s, H, "dxf.supply")
        elif m := D_ACB.match(s):
            yield ctx.value("incomer.device", "acb", None, n, s, H, "dxf.incomer")
            yield ctx.value("incomer.rating", int(m.group(1)), "A", n, s, H, "dxf.incomer")
            yield ctx.value("incomer.poles", int(m.group(2)), None, n, s, H, "dxf.incomer")
        elif m := D_CT.match(s):
            yield ctx.value("metering.ct_ratio", m.group(1), "A", n, s, H, "dxf.ct")
        elif s in ("kWh", "MFM"):
            yield ctx.value("metering.meter", s, None, n, s, H, "dxf.meter")
        elif m := D_BUS.match(s):
            yield ctx.value("busbar.rating", int(m.group(1)), "A", n, s, H, "dxf.busbar")
            if m.group(2):
                yield ctx.value("system.fault_level", int(m.group(2)), "kA", n, s, H, "dxf.busbar")
        elif m := D_WIDTH.match(s):
            yield ctx.value("enclosure.width", int(m.group(1)), "mm", n, s, H, "dxf.width")
            yield ctx.value("enclosure.sections", int(m.group(2)), None, n, s, H, "dxf.width")
        else:
            for field, pattern, fix in D_NOTES:
                if m := pattern.search(s):
                    yield ctx.value(field, fix(m.group(1)), None, n, s, H, "dxf.note")

    labels = _way_labels(items)
    for t in items:
        if abs(t.rotation) < 1 or not (owner := _owner(labels, t.x)):
            continue
        f = f"way.{owner.text}"
        if m := D_RATING.match(t.text):
            yield ctx.value(f"{f}.device", norm.device(m.group(1)), None, n, t.text, H, "dxf.way_rating")
            for token in m.group(2).split():
                if tm := re.fullmatch(r"(\d+)A", token):
                    yield ctx.value(f"{f}.rating", int(tm.group(1)), "A", n, t.text, H, "dxf.way_rating")
                elif token == "TBC":
                    yield ctx.value(f"{f}.rating", None, None, n, t.text, L, "dxf.way_rating",
                                    derivation="stated as TBC: no value given")
                elif tm := re.fullmatch(r"(\d)P", token):
                    yield ctx.value(f"{f}.poles", int(tm.group(1)), None, n, t.text, H, "dxf.way_rating")
                elif tm := re.fullmatch(r"(\d+)kA", token):
                    yield ctx.value(f"{f}.breaking_capacity", int(tm.group(1)), "kA", n, t.text, H,
                                    "dxf.way_rating")
        else:
            yield ctx.value(f"{f}.description", t.text, None, n, t.text, H, "dxf.way_description")
    if labels:
        ids = ", ".join(lb.text for lb in labels)
        yield ctx.value("ways.count", len(labels), None, n, labels[-1].text, H, "dxf.way_labels",
                        derivation=f"counted {len(labels)} way labels on sheet {n}: {ids}")
    yield from _schedule(ctx, n, items)


def extract_drawing(pages: list[PageText], file: str) -> list[ExtractedValue]:
    ctx = Ctx(DocumentKind.SCHEMATIC, file)
    out: list[ExtractedValue] = []
    for page in pages:
        out += _sheet(ctx, page)
    return out


def extract(kind: DocumentKind, pages: list[PageText], file: str) -> list[ExtractedValue]:
    """All rule-based values of one read document."""
    if kind == DocumentKind.SPECIFICATION:
        return extract_specification(pages, file)
    if kind == DocumentKind.REQUIREMENTS:
        return extract_letter(pages, file)
    return extract_drawing(pages, file)
