"""The schematic: a two-sheet DXF drawing rendered to a vector PDF.

Sheet 1 is the single-line diagram (incomer, metering, busbar, outgoing ways,
earth, notes, cable schedule, revision table, title block). Sheet 2 is the
front-view general arrangement of the panel sections.

Rendering path: ezdxf builds the DXF; ezdxf's *matplotlib* drawing backend
renders it; matplotlib writes the PDF. ezdxf's PyMuPDF backend is not used
(PyMuPDF is AGPL). Text is drawn as glyph outlines from the fonts in
``data_generator/fonts`` only, so the output does not depend on the fonts
installed on the machine.

Every symbol and every value-bearing text is recorded with its extents in
sheet millimetres while it is drawn; nothing is measured afterwards.
"""

from __future__ import annotations

import io
import random
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402
from ezdxf.fonts import fonts as ezfonts  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from data_generator import symbols as sym  # noqa: E402
from data_generator.design import DEVICE_LABEL, Way  # noqa: E402
from data_generator.names import INITIALS, PANEL_BUILDER  # noqa: E402
from data_generator.views import DocView  # noqa: E402
from data_generator.wording import Wording  # noqa: E402

FONT_DIR = Path(__file__).parent / "fonts"
SHEET_W, SHEET_H = 420.0, 297.0  # A3 landscape, mm
SHEET_SPACING = 500.0  # sheet 2 sits to the right of sheet 1 in model space

# Drawing fonts: (regular, bold) per family. All SIL OFL 1.1.
DRAWING_FONTS = {
    "plex-condensed": ("IBMPlexSansCondensed-Regular.ttf", "IBMPlexSansCondensed-Medium.ttf"),
    "plex-mono": ("IBMPlexMono-Regular.ttf", "IBMPlexMono-Regular.ttf"),
    "plex-serif": ("IBMPlexSerif-Regular.ttf", "IBMPlexSerif-Bold.ttf"),
}

PDF_METADATA = {"Creator": None, "Producer": None, "CreationDate": None, "ModDate": None,
                "Title": "Schematic", "Author": PANEL_BUILDER}

_fonts_ready = False


def setup_fonts() -> None:
    """Point ezdxf at the repo fonts only (no system fonts, no cache file)."""
    global _fonts_ready
    if not _fonts_ready:
        ezfonts.font_manager.clear()
        ezfonts.font_manager.build([str(FONT_DIR)], support_dirs=False)
        ezdxf.options.write_fixed_meta_data_for_testing = True  # fixed header dates and GUIDs
        _fonts_ready = True


Box = tuple[float, float, float, float]


@dataclass
class ValueMark:
    """A value-bearing text (or area) on a sheet."""

    field: str
    value: object
    unit: str | None
    text: str | None
    sheet: int
    box: Box


@dataclass
class SymbolMark:
    cls: str
    way: str | None
    sheet: int
    box: Box


@dataclass
class DrawingLayout:
    """What was drawn, in sheet millimetres."""

    symbols: list[SymbolMark] = field(default_factory=list)
    values: list[ValueMark] = field(default_factory=list)
    font_family: str = ""
    symbol_scale: float = 1.0


class Sheet:
    """Draws on one sheet in sheet-local millimetres and records what it drew."""

    def __init__(self, msp, number: int, font: str, bold_font: str):
        self.msp = msp
        self.number = number
        self.ox = (number - 1) * SHEET_SPACING
        self.layer = f"SHEET{number}"
        self.font_file, self.bold_file = font, bold_font
        self._font_cache: dict[tuple[str, float], object] = {}

    def _p(self, p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] + self.ox, p[1])

    def line(self, p1, p2, lw: int = 35) -> None:
        self.msp.add_line(self._p(p1), self._p(p2), dxfattribs={"layer": self.layer, "lineweight": lw})

    def rect(self, x0, y0, x1, y1, lw: int = 35) -> None:
        pts = [self._p(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        self.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": self.layer, "lineweight": lw})

    def thick(self, p1, p2, width: float) -> None:
        pl = self.msp.add_lwpolyline([self._p(p1), self._p(p2)], dxfattribs={"layer": self.layer})
        pl.dxf.const_width = width

    def circle(self, c, r: float, lw: int = 35) -> None:
        self.msp.add_circle(self._p(c), r, dxfattribs={"layer": self.layer, "lineweight": lw})

    def dashed(self, p1, p2, dash: float = 1.6, gap: float = 1.0) -> None:
        """A dashed line drawn as short segments, so every renderer shows the same dashes."""
        (x1, y1), (x2, y2) = p1, p2
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        t = 0.0
        while t < length:
            t2 = min(t + dash, length)
            self.line((x1 + (x2 - x1) * t / length, y1 + (y2 - y1) * t / length),
                      (x1 + (x2 - x1) * t2 / length, y1 + (y2 - y1) * t2 / length), lw=25)
            t = t2 + gap

    def _font(self, h: float, bold: bool = False):
        key = (self.bold_file if bold else self.font_file, h)
        if key not in self._font_cache:
            self._font_cache[key] = ezfonts.make_font(key[0], h)
        return self._font_cache[key]

    def text_width(self, s: str, h: float, bold: bool = False) -> float:
        return float(self._font(h, bold).text_width(s))

    def text(self, s: str, x: float, y: float, h: float, rot: float = 0.0, bold: bool = False) -> Box:
        """Left-aligned text with its baseline start at ``(x, y)``; returns its box.

        ``rot`` is 0 or 90 degrees (90 reads bottom to top).
        """
        style = "BOLD" if bold else "BODY"
        t = self.msp.add_text(s, height=h, rotation=rot, dxfattribs={"layer": self.layer, "style": style})
        t.set_placement(self._p((x, y)))
        w = self.text_width(s, h, bold)
        down, up = 0.35 * h, 1.15 * h  # descender and ascender allowance around the cap height
        if rot == 0:
            return (x, y - down, x + w, y + up)
        if rot == 90:
            return (x - up, y, x + down, y + w)
        raise ValueError("text rotation must be 0 or 90")


def _new_doc(font: str, bold: str):
    doc = ezdxf.new("R2010", setup=False)
    doc.header["$INSUNITS"] = 4  # millimetres
    # The default "Standard" style names a CAD font we do not ship; point it at ours so the
    # renderer never looks for a system font.
    doc.styles.get("Standard").dxf.font = font
    doc.styles.add("BODY", font=font)
    doc.styles.add("BOLD", font=bold)
    for n in (1, 2):
        doc.layers.add(f"SHEET{n}")
    return doc


def rating_text(w: Way, view: DocView, variant: int, words: Wording | None = None) -> str:
    """The rating string printed beside a way, e.g. ``MCCB 250A 4P 36kA``."""
    if words is not None:  # reworded set
        rating = "TBC" if f"way.{w.id}.rating" in view.tbc else words.amps_short(w.rating_a)
        parts = [words.device_label(w.device), rating, words.poles_short(w.poles).upper()]
        if words.rng.random() < 0.5:
            parts = [parts[1], parts[0], parts[2]]
        if w.breaking_ka is not None:
            parts.append(words.pick([f"{w.breaking_ka}kA", f"Icu={w.breaking_ka}kA", f"{w.breaking_ka} KA"]))
        return " ".join(parts)
    label = DEVICE_LABEL[w.device]
    rating = "TBC" if f"way.{w.id}.rating" in view.tbc else f"{w.rating_a}A"
    parts = [label, rating, f"{w.poles}P"] if variant == 0 else [label, f"{w.poles}P", rating]
    if w.breaking_ka is not None:
        parts.append(f"{w.breaking_ka}kA")
    return " ".join(parts)


def _way_values(w: Way, text: str, box: Box) -> list[ValueMark]:
    vals = [
        ValueMark(f"way.{w.id}.device", w.device.value, None, text, 1, box),
        ValueMark(f"way.{w.id}.rating", w.rating_a, "A", text, 1, box),
        ValueMark(f"way.{w.id}.poles", w.poles, None, text, 1, box),
    ]
    if w.breaking_ka is not None:
        vals.append(ValueMark(f"way.{w.id}.breaking_capacity", w.breaking_ka, "kA", text, 1, box))
    return vals


def draw_sheet1(s: Sheet, view: DocView, rng: random.Random, layout: DrawingLayout, revision: str,
                drawing_no: str, drawn: str, checked: str) -> None:
    d = view.design
    sc = layout.symbol_scale
    h = rng.choice([2.2, 2.5, 2.8])  # main text height
    variant = rng.randrange(2)
    words = Wording(view.reword) if view.reword is not None else None

    _frame(s, d, h, drawing_no, revision, drawn, checked, sheet_title="SINGLE LINE DIAGRAM", rng=rng)

    # Incomer, metering and busbar.
    x_in = rng.uniform(30, 36)
    y_bus = rng.uniform(205, 222)
    supply = f"INCOMING SUPPLY {d.voltage_v}V 3PH+N {d.frequency_hz}Hz"
    if words:
        supply = words.pick([f"SUPPLY {d.voltage_v} V 3PH 4W {d.frequency_hz} HZ",
                             f"LV SUPPLY {d.voltage_v}V TPN {d.frequency_hz}Hz", f"{d.voltage_v}V 50HZ 3PH+N INCOMER"
                             if d.frequency_hz == 50 else f"{d.voltage_v}V {d.frequency_hz}HZ 3PH+N INCOMER"])
    box = s.text(supply, x_in + 3, 277, h)
    layout.values += [ValueMark("system.voltage", d.voltage_v, "V", supply, 1, box),
                      ValueMark("system.frequency", d.frequency_hz, "Hz", supply, 1, box)]
    L_acb = 20 * sc
    acb_top = 270
    s.line((x_in, 281), (x_in, acb_top))
    layout.symbols.append(SymbolMark("acb", None, 1, sym.acb(s, x_in, acb_top, L_acb)))
    acb_txt = f"ACB {d.incomer_rating_a}A {d.incomer_poles}P 50kA"
    if words:
        acb_txt = words.pick([f"{d.incomer_rating_a}A ACB {d.incomer_poles} POLE",
                              f"ACB In={d.incomer_rating_a}A {d.incomer_poles}P",
                              f"AIR CB {d.incomer_rating_a} A {d.incomer_poles}-POLE"])
    box = s.text(acb_txt, x_in + 4, acb_top - L_acb / 2 - h / 2, h)
    layout.values += [ValueMark("incomer.device", "acb", None, acb_txt, 1, box),
                      ValueMark("incomer.rating", d.incomer_rating_a, "A", acb_txt, 1, box),
                      ValueMark("incomer.poles", d.incomer_poles, None, acb_txt, 1, box)]
    ct_r = 3.0 * sc
    ct_y = acb_top - L_acb - 4 - ct_r
    s.line((x_in, acb_top - L_acb), (x_in, y_bus))
    layout.symbols.append(SymbolMark("ct", None, 1, sym.current_transformer(s, x_in, ct_y, ct_r)))
    ct_txt = f"CT {d.ct_ratio}A"
    if words:
        ct_txt = words.pick([f"CTs {d.ct_ratio}", f"3 x CT {d.ct_ratio}A", f"CT RATIO {d.ct_ratio.replace('/', ':')}"])
    box = s.text(ct_txt, x_in + 2.6 * ct_r, ct_y + ct_r + 1.2, h * 0.9)
    layout.values.append(ValueMark("metering.ct_ratio", d.ct_ratio, "A", ct_txt, 1, box))
    m_r = 4.5 * sc
    m_x = x_in + 2.3 * ct_r + 6 + m_r
    s.dashed((x_in + 2.3 * ct_r, ct_y), (m_x - m_r, ct_y))
    layout.symbols.append(SymbolMark("meter", None, 1, sym.meter(s, m_x, ct_y, m_r, d.meter, h * 0.8)))
    mh = h * 0.8  # the meter type is written inside the circle by sym.meter
    mw = s.text_width(d.meter, mh)
    box = (m_x - mw / 2, ct_y - mh / 2 - 0.35 * mh, m_x + mw / 2, ct_y - mh / 2 + 1.15 * mh)
    layout.values.append(ValueMark("metering.meter", d.meter, None, d.meter, 1, box))

    x_bus0, x_bus1 = 20.0, rng.uniform(398, 405)
    s.thick((x_bus0, y_bus), (x_bus1, y_bus), width=1.2)
    layout.symbols.append(SymbolMark("busbar", None, 1, (x_bus0, y_bus - 0.6, x_bus1, y_bus + 0.6)))
    bus_txt = f"BUSBAR {d.busbar_rating_a}A TP&N"
    fault_stated = view.states("system.fault_level")
    if fault_stated:
        bus_txt += f" {d.fault_level_ka}kA 1s"
    if words:
        bus_txt = words.pick([f"MAIN BUSBARS {d.busbar_rating_a} A", f"{d.busbar_rating_a}A TPN BUSBAR",
                              f"BB RATING {d.busbar_rating_a}A"])
        if fault_stated:
            bus_txt += words.pick([f" {d.fault_level_ka}kA/1s", f" Icw {d.fault_level_ka} kA 1 SEC"])
    box = s.text(bus_txt, x_bus1 - s.text_width(bus_txt, h), y_bus + 2.2, h)
    layout.values.append(ValueMark("busbar.rating", d.busbar_rating_a, "A", bus_txt, 1, box))
    if fault_stated:
        layout.values.append(ValueMark("system.fault_level", d.fault_level_ka, "kA", bus_txt, 1, box))

    # Main earth bar, under the left end of the busbar.
    x_e = x_bus0 + 4
    layout.symbols.append(SymbolMark("earth", None, 1, sym.earth(s, x_e, y_bus - 10, 12 * sc)))
    s.text("MET", x_e + 4.5 * sc, y_bus - 14, h * 0.8)

    # Outgoing ways.
    n = len(d.ways)
    x0 = x_in + 2.3 * ct_r + 2 * m_r + 22
    x1 = x_bus1 - 12
    pitch = min(34.0, (x1 - x0) / max(1, n - 1))
    L = 16 * sc
    way_boxes: list[Box] = []
    for i, w in enumerate(d.ways):
        x = x0 + i * pitch
        top = y_bus - 7
        s.line((x, y_bus), (x, top))
        box = sym.BREAKERS[w.device.value](s, x, top, L)
        layout.symbols.append(SymbolMark(w.device.value, w.id, 1, box))
        way_boxes.append(box)
        bottom = top - L
        end = bottom - 9
        s.line((x, bottom), (x, end))
        s.line((x - 1.2, end + 2), (x, end))  # outgoing arrow
        s.line((x + 1.2, end + 2), (x, end))
        lbl_w = s.text_width(w.id, h, bold=True)
        s.text(w.id, x - lbl_w - 1.4, y_bus - 5.6, h, bold=True)
        rt = rating_text(w, view, variant, words)
        rbox = s.text(rt, x + 0.45 * h, end - 2 - s.text_width(rt, h), h, rot=90)
        layout.values += _way_values(w, rt, rbox)
        desc = w.description.upper()
        dh = h * 0.9
        dbox = s.text(desc, x + 2.1 * h, end - 2 - s.text_width(desc, dh), dh, rot=90)
        layout.values.append(ValueMark(f"way.{w.id}.description", w.description, None, desc, 1, dbox))
    if way_boxes:
        area = (min(b[0] for b in way_boxes), min(b[1] for b in way_boxes),
                max(b[2] for b in way_boxes), max(b[3] for b in way_boxes))
        layout.values.append(ValueMark("ways.count", n, None, None, 1, area))

    _notes(s, view, h, layout, words)
    _cable_schedule(s, view, h, layout)


def _frame(s: Sheet, d, h: float, drawing_no: str, revision: str, drawn: str, checked: str,
           sheet_title: str, rng: random.Random) -> None:
    """Border, title block and revision table."""
    s.rect(10, 10, SHEET_W - 10, SHEET_H - 10, lw=50)
    tx0, tx1, ty0, ty1 = 250.0, SHEET_W - 10, 10.0, 48.0
    s.rect(tx0, ty0, tx1, ty1, lw=50)
    s.line((tx0, 36), (tx1, 36))
    s.line((tx0, 24), (tx1, 24))
    s.line((330, ty0), (330, 24))
    s.text(PANEL_BUILDER, tx0 + 3, 39.5, 4.0, bold=True)
    s.text(sheet_title, tx0 + 3, 29.5, 3.0, bold=True)
    s.text(f"{d.board_name}  {d.customer}", tx0 + 3, 26, 2.0)
    s.text(f"DRAWING No. {drawing_no}", tx0 + 3, 19, 2.2)
    s.text(f"REV {revision}", tx0 + 3, 14, 2.2)
    s.text(f"DATE {d.issue_date}", tx0 + 30, 14, 2.2)
    s.text(f"DRAWN {drawn}", 333, 19, 2.2)
    s.text(f"CHECKED {checked}", 333, 14, 2.2)
    s.text(f"SHEET {s.number} OF 2   SCALE NTS", 365, 19, 2.0)
    # Revision table above the title block.
    ry = ty1
    rows = [("A", "FIRST ISSUE FOR TENDER"), ("B", "UPDATED TO CLIENT COMMENTS")][: 1 + (revision == "B")]
    s.rect(tx0, ry, tx1, ry + 5 * (len(rows) + 1))
    cols = (tx0 + 2, tx0 + 12, tx0 + 36, tx1 - 12)
    for cx, title in zip(cols, ("REV", "DATE", "DESCRIPTION", "BY")):
        s.text(title, cx, ry + 5 * len(rows) + 1.5, 2.0, bold=True)
    first_issue = f"{d.issue_date[:8]}{max(1, int(d.issue_date[8:]) - rng.randint(3, 20) % 27):02d}"
    for i, (rev, text) in enumerate(reversed(rows)):
        y = ry + 5 * (len(rows) - 1 - i) + 1.5
        date = d.issue_date if rev == revision else first_issue
        for cx, cell in zip(cols, (rev, date, text, drawn)):
            s.text(cell, cx, y, 2.0)


def _notes(s: Sheet, view: DocView, h: float, layout: DrawingLayout, words: Wording | None = None) -> None:
    d = view.design
    x, y = 15.0, 84.0
    s.text("NOTES:", x, y, h, bold=True)
    notes: list[tuple[str | None, object, str | None, str]] = [
        ("enclosure.form", d.form, None, f"FORM OF SEPARATION: FORM {d.form}"),
        ("enclosure.ip_rating", d.ip_rating, None, f"DEGREE OF PROTECTION: {d.ip_rating}"),
        ("enclosure.cable_entry", d.cable_entry, None, f"CABLE ENTRY: {d.cable_entry.upper()}"),
        ("system.earthing", d.earthing, None, f"EARTHING SYSTEM: {d.earthing}"),
        (None, None, None, "ALL DIMENSIONS IN mm UNLESS STATED"),
        (None, None, None, "DO NOT SCALE FROM THIS DRAWING"),
    ]
    if words:  # reworded set
        below = {"bottom": "BELOW", "top": "ABOVE"}[d.cable_entry]
        notes = [
            ("enclosure.form", d.form, None, words.pick([f"SEGREGATION {words.form(d.form).upper()}",
                                                          f"INTERNAL SEPARATION {d.form}"])),
            ("enclosure.ip_rating", d.ip_rating, None, words.pick([f"ENCLOSURE {words.ip(d.ip_rating)}",
                                                                  f"IP RATING {words.ip(d.ip_rating)}"])),
            ("enclosure.cable_entry", d.cable_entry, None, words.pick([f"CABLES ENTER FROM {below}",
                                                                      f"{d.cable_entry.upper()} CABLE ENTRY"])),
            ("system.earthing", d.earthing, None, words.pick([f"SYSTEM {d.earthing}", f"EARTHING TO {d.earthing}"])),
            (None, None, None, "DIMENSIONS IN MILLIMETRES"),
            (None, None, None, "NOT TO SCALE"),
        ]
        words.rng.shuffle(notes)
    k = 1
    for fld, value, unit, text in notes:
        if fld is not None and not view.states(fld):
            continue
        y -= h * 2.0
        full = f"{k}. {text}"
        box = s.text(full, x, y, h * 0.9)
        if fld is not None:
            layout.values.append(ValueMark(fld, value, unit, full, 1, box))
        k += 1


def _cable_schedule(s: Sheet, view: DocView, h: float, layout: DrawingLayout) -> None:
    d = view.design
    x0, x1 = 112.0, 246.0
    th = 2.0
    row_h = 4.2
    cols = [x0, x0 + 10, x0 + 50, x0 + 82, x0 + 118, x1]
    y_top = 14 + row_h * (len(d.ways) + 2)
    s.text("CABLE SCHEDULE", x0, y_top + 1.5, h, bold=True)
    s.rect(x0, 14, x1, y_top)
    for cx in cols[1:-1]:
        s.line((cx, 14), (cx, y_top), lw=25)
    s.line((x0, y_top - row_h), (x1, y_top - row_h), lw=25)
    for cx, title in zip(cols, ["WAY", "DESCRIPTION", "DEVICE", "CABLE", "LEN (m)"]):
        s.text(title, cx + 1, y_top - row_h + 1.2, th, bold=True)
    for i, w in enumerate(d.ways):
        y = y_top - row_h * (i + 2) + 1.2
        s.text(w.id, cols[0] + 1, y, th)
        s.text(w.description.upper(), cols[1] + 1, y, th)
        s.text(DEVICE_LABEL[w.device], cols[2] + 1, y, th)
        cbox = s.text(w.cable, cols[3] + 1, y, th)
        layout.values.append(ValueMark(f"way.{w.id}.cable", w.cable, None, w.cable, 1, cbox))
        lbox = s.text(str(w.cable_length_m), cols[4] + 1, y, th)
        layout.values.append(ValueMark(f"way.{w.id}.cable_length", w.cable_length_m, "m",
                                       str(w.cable_length_m), 1, lbox))


def draw_sheet2(s: Sheet, view: DocView, rng: random.Random, layout: DrawingLayout, revision: str,
                drawing_no: str, drawn: str, checked: str) -> None:
    """Front-view general arrangement: one rectangle per section, one cut-out per device."""
    d = view.design
    h = 2.5
    _frame(s, d, h, drawing_no, revision, drawn, checked, sheet_title="GENERAL ARRANGEMENT - FRONT VIEW",
           rng=rng)
    k = min(0.07, 370.0 / d.width_mm)
    x = 20.0 + rng.uniform(0, 380.0 - d.width_mm * k)
    base = 112.0
    top = base + 2200 * k
    # Incomer section.
    widths = [800] + [600] * d.outgoing_sections
    sections: list[list[Way]] = [[] for _ in range(d.outgoing_sections)]
    units = 0
    for w in d.ways:
        sections[min(units // 4, d.outgoing_sections - 1)].append(w)
        units += w.units
    for i, wmm in enumerate(widths):
        w_draw = wmm * k
        s.rect(x, base, x + w_draw, top, lw=50)
        s.text(f"SECTION {i + 1}", x + 2, top + 2, h * 0.9, bold=True)
        s.text(f"W{wmm}", x + w_draw / 2 - 3, base - 5, h * 0.8)
        if i == 0:
            s.rect(x + 0.15 * w_draw, top - 0.45 * (top - base), x + 0.85 * w_draw, top - 0.15 * (top - base))
            s.text("ACB", x + 0.15 * w_draw + 1.5, top - 0.3 * (top - base), h * 0.8)
        else:
            ways = sections[i - 1]
            slot = (top - base - 8) / 4
            used = 0
            for w in ways:
                y_hi = top - 4 - used * slot
                y_lo = y_hi - w.units * slot + 2
                s.rect(x + 0.12 * w_draw, y_lo, x + 0.88 * w_draw, y_hi)
                s.text(w.id, x + 0.12 * w_draw + 1.5, y_lo + 1.5, h * 0.8)
                used += w.units
        x += w_draw
    dim = f"OVERALL WIDTH {d.width_mm} mm - {d.sections} SECTIONS"
    box = s.text(dim, 20.0, base - 14, h, bold=True)
    layout.values += [ValueMark("enclosure.width", d.width_mm, "mm", dim, 2, box),
                      ValueMark("enclosure.sections", d.sections, None, dim, 2, box)]
    s.text("HEIGHT 2200 mm", 20.0, base - 20, h)


@dataclass
class SchematicFiles:
    dxf: Path
    pdf: Path
    layout: DrawingLayout


def build_schematic(view: DocView, seed: int, dxf_path: Path, pdf_path: Path,
                    sheets: tuple[int, ...] = (1, 2)) -> SchematicFiles:
    """Write the DXF and the vector PDF for ``view``. Same inputs, same bytes."""
    setup_fonts()
    rng = random.Random(seed)
    family = rng.choice(sorted(DRAWING_FONTS))
    font, bold = DRAWING_FONTS[family]
    layout = DrawingLayout(font_family=family, symbol_scale=round(rng.uniform(0.85, 1.2), 3))
    doc = _new_doc(font, bold)
    msp = doc.modelspace()
    revision = rng.choice(["A", "B"])
    drawing_no = f"EPL-{view.design.project_id}-SLD"
    drawn, checked = rng.sample(INITIALS, 2)
    if 1 in sheets:
        draw_sheet1(Sheet(msp, 1, font, bold), view, rng, layout, revision, drawing_no, drawn, checked)
    if 2 in sheets:
        draw_sheet2(Sheet(msp, 2, font, bold), view, rng, layout, revision, drawing_no, drawn, checked)
    dxf_path.parent.mkdir(parents=True, exist_ok=True)
    # Written through a string buffer so lines end in LF on every platform (saveas uses the
    # platform's text mode, which gives CRLF on Windows).
    # ezdxf collects the CLASS entries from sets, whose order changes with Python's per-process
    # hash seed. Register them now in sorted order; the writer keeps classes it already has.
    doc.classes.add_required_classes(doc.dxfversion)
    doc.classes.classes = OrderedDict(sorted(doc.classes.classes.items()))
    buf = io.StringIO()
    doc.write(buf)
    dxf_path.write_bytes(doc.encode(buf.getvalue()))
    _render_pdf(doc, pdf_path, sheets)
    return SchematicFiles(dxf_path, pdf_path, layout)


def _render_pdf(doc, pdf_path: Path, sheets: tuple[int, ...]) -> None:
    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                           lineweight_scaling=1.0)
    msp = doc.modelspace()
    with PdfPages(pdf_path, metadata=PDF_METADATA) as pdf:
        for n in sheets:
            fig = plt.figure(figsize=(SHEET_W / 25.4, SHEET_H / 25.4))
            ax = fig.add_axes((0, 0, 1, 1))
            backend = MatplotlibBackend(ax, adjust_figure=False)
            layer = f"SHEET{n}"
            Frontend(RenderContext(doc), backend, config=config).draw_layout(
                msp, finalize=True, filter_func=lambda e, layer=layer: e.dxf.layer == layer)
            ox = (n - 1) * SHEET_SPACING
            ax.set_xlim(ox, ox + SHEET_W)
            ax.set_ylim(0, SHEET_H)
            ax.set_aspect("auto")
            pdf.savefig(fig)
            plt.close(fig)
