"""Drawing values from OCR lines: the DXF drawing rules, read from OCR text and boxes.

The patterns follow the frozen DXF rules (``backend/app/extraction.py``, not
imported or changed): the same texts give the same fields. What differs is
where the text comes from:

- **Character fixes.** Where the pattern needs a digit, the letters Tesseract
  most often reads in place of one are mapped (``O``/``o``/``D`` to 0, ``S``/``s``
  to 5, ``I``/``l``/``|`` to 1; in a cable's core count also ``A`` to 4), and a
  way label read as ``04`` or ``O4`` is taken as ``Q4``. A value read with a
  fix says so in its derivation and has low confidence.
- **Ways by position.** The way labels (Q1, Q2, ...) are the largest row of
  labels on the sheet. A vertical rating or description text belongs to the
  nearest label to its left, and only when it is close to that label (within
  0.6 of the label spacing), so a text whose own label was not read is
  dropped, not given to the way before it.
- **Trailing noise.** Words after the rating grammar ends (pieces of symbols
  read as letters) are dropped, and the value's box covers the kept words.
- **Cable schedule rows.** A schedule row is a way label with a cable on the
  same line; its length is the number just to its right. "Same line" allows
  for a scan turned a little or a photo tilted: the sheet's skew (the median
  slope of its longer text lines) is taken out before rows are compared.

Every value has method ``ocr``, the sheet as its page, the OCR words it was
read from as its source text and their box as a region. Confidence is never above medium:
medium when every word used scored at least :data:`MIN_WORD_CONF` and needed
no fix, low otherwise. The engineer approves each one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from statistics import median

from backend.app import normalise as norm
from backend.app.drawing.ocr import OcrLine, OcrWord, SheetOcr, union
from backend.app.drawing.reading import DrawingReading, TextBox, WayReading
from backend.app.schemas import Confidence, DocumentKind, ExtractedValue, Method, SourceRef
from data_generator.schemas import Region

MIN_WORD_CONF = 80.0  # Tesseract word confidence for a medium-confidence value
MIN_TEXT_CONF = 40.0  # lines below this are left out of the reading's text list (symbol pieces)
DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "S": "5", "s": "5", "I": "1", "l": "1", "|": "1"})
DIGITISH = r"[0-9OoDSsIl|]"

LABEL = re.compile(r"^[Q0O]([1-9][0-9]?)$")
DEVICE = re.compile(r"^(MCCB|MCB|SW-DISC)$")
SUPPLY = re.compile(rf"INCOMING SUPPLY ({DIGITISH}+)V\b.*?\b({DIGITISH}+)Hz\b")
ACB = re.compile(rf"\bACB ({DIGITISH}+)A ({DIGITISH})P\b")
CT = re.compile(rf"\bCT ({DIGITISH}+/{DIGITISH}+) ?A\b")
BUS = re.compile(rf"\bBUSBAR ({DIGITISH}+)A TP&N(?: ({DIGITISH}+)[kK][aA] 1s)?")
WIDTH = re.compile(rf"OVERALL WIDTH ({DIGITISH}+) ?mm - ({DIGITISH}+) SECTIONS")
NOTES = [
    ("enclosure.form", re.compile(r"FORM OF SEPARATION: FORM (\d[a-bA-B]?)\b"), str.lower),
    ("enclosure.ip_rating", re.compile(r"DEGREE OF PROTECTION: (IP\d{2})\b"), str.upper),
    ("enclosure.cable_entry", re.compile(r"CABLE ENTRY: (TOP|BOTTOM)\b"), str.lower),
    ("system.earthing", re.compile(r"EARTHING SYSTEM: (TN-C-S|TN-S|TN-C|TT|IT)\b"), str.upper),
]
CABLE = re.compile(rf"^(?:({DIGITISH})x ?)?({DIGITISH}|A)C ({DIGITISH}+) mm2 (SWA)$")
LENGTH = re.compile(rf"^{DIGITISH}{{1,4}}$")


def digits(raw: str, extra: dict[str, str] | None = None) -> tuple[str, bool]:
    """``raw`` with look-alike letters mapped to digits, and whether anything was mapped."""
    fixed = raw.translate(DIGIT_FIX)
    if extra:
        fixed = fixed.translate(str.maketrans(extra))
    return fixed, fixed != raw


class _Read:
    """Words used for one value: their text, box and whether a character fix was needed."""

    def __init__(self, words: list[OcrWord], fixed: bool = False, note: str | None = None) -> None:
        self.words, self.fixed, self.note = words, fixed, note

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def confidence(self) -> Confidence:
        if self.fixed or min(w.conf for w in self.words) < MIN_WORD_CONF:
            return Confidence.LOW
        return Confidence.MEDIUM


def _centre(box: list[float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def skew(lines: Iterable[OcrLine]) -> float:
    """How much upright text lines climb or fall per pixel across the sheet (a scan is turned a little,
    a photo is tilted): the median slope of lines of three or more words."""
    slopes = []
    for line in lines:
        if line.rotated or len(line.words) < 3:
            continue
        (x0, y0), (x1, y1) = _centre(line.words[0].bbox), _centre(line.words[-1].bbox)
        if x1 - x0 > 50:
            slopes.append((y1 - y0) / (x1 - x0))
    return median(slopes) if slopes else 0.0


class Linker:
    """Builds the values of one OCR'd sheet."""

    def __init__(self, sheet: SheetOcr, file: str) -> None:
        self.sheet, self.file = sheet, file
        self.values: list[ExtractedValue] = []
        self.ways: dict[str, WayReading] = {}
        self.slope = skew(sheet.lines)
        self.labels: list[tuple[str, OcrWord, bool]] = []  # the diagram's way labels, once found

    def level(self, box: list[float]) -> float:
        """A box's height on the page with the sheet's skew taken out, to compare rows across the sheet."""
        cx, cy = _centre(box)
        return cy - self.slope * cx

    # --- output -----------------------------------------------------------------------------------

    def _clip(self, box: list[float]) -> list[float]:
        w, h = self.sheet.width_px, self.sheet.height_px
        x0, y0 = min(max(box[0], 0.0), w - 1), min(max(box[1], 0.0), h - 1)
        return [x0, y0, min(max(box[2], x0 + 1), w), min(max(box[3], y0 + 1), h)]

    def add(self, field: str, value, unit: str | None, read: _Read, rule: str,
            derivation: str | None = None, confidence: Confidence | None = None) -> None:
        notes = [n for n in (derivation, read.note) if n]
        region = Region(version=self.sheet.version, sheet=self.sheet.sheet,
                        bbox=self._clip(union([w.bbox for w in read.words])))
        self.values.append(ExtractedValue(
            field=field, value=value, unit=norm.unit(unit), method=Method.OCR,
            confidence=confidence or read.confidence, rule=rule, derivation="; ".join(notes) or None,
            source=SourceRef(document=DocumentKind.SCHEMATIC, file=self.file, page=self.sheet.sheet,
                             source_text=read.text, regions=[region])))

    # --- sheet facts (upright texts) --------------------------------------------------------------

    def facts(self, lines: Iterable[OcrLine]) -> None:
        for line in lines:
            s = line.text
            if m := SUPPLY.search(s):
                (v, f1), (hz, f2) = digits(m.group(1)), digits(m.group(2))
                if v.isdigit() and hz.isdigit():
                    r = _Read(span_words(line, m), f1 or f2, _fix_note(m.group(1), v) or _fix_note(m.group(2), hz))
                    self.add("system.voltage", int(v), "V", r, "ocr.supply")
                    self.add("system.frequency", int(hz), "Hz", r, "ocr.supply")
            elif m := ACB.search(s):
                (a, f1), (p, f2) = digits(m.group(1)), digits(m.group(2))
                if a.isdigit() and p.isdigit():
                    r = _Read(span_words(line, m), f1 or f2, _fix_note(m.group(1), a) or _fix_note(m.group(2), p))
                    self.add("incomer.device", "acb", None, r, "ocr.incomer")
                    self.add("incomer.rating", int(a), "A", r, "ocr.incomer")
                    self.add("incomer.poles", int(p), None, r, "ocr.incomer")
            elif m := CT.search(s):
                ratio, fixed = digits(m.group(1))
                if re.fullmatch(r"\d+/\d+", ratio):
                    r = _Read(span_words(line, m), fixed, _fix_note(m.group(1), ratio))
                    self.add("metering.ct_ratio", ratio, "A", r, "ocr.ct")
            elif s in ("kWh", "MFM"):
                self.add("metering.meter", s, None, _Read(line.words), "ocr.meter")
            elif m := BUS.search(s):
                a, f1 = digits(m.group(1))
                if a.isdigit():
                    self.add("busbar.rating", int(a), "A", _Read(span_words(line, m), f1, _fix_note(m.group(1), a)),
                             "ocr.busbar")
                if m.group(2):
                    ka, f2 = digits(m.group(2))
                    if ka.isdigit():
                        self.add("system.fault_level", int(ka), "kA",
                                 _Read(span_words(line, m), f2, _fix_note(m.group(2), ka)), "ocr.busbar")
            elif m := WIDTH.search(s):
                (mm, f1), (n, f2) = digits(m.group(1)), digits(m.group(2))
                if mm.isdigit() and n.isdigit():
                    r = _Read(span_words(line, m), f1 or f2, _fix_note(m.group(1), mm) or _fix_note(m.group(2), n))
                    self.add("enclosure.width", int(mm), "mm", r, "ocr.width")
                    self.add("enclosure.sections", int(n), None, r, "ocr.width")
            else:
                for field, pattern, fix in NOTES:
                    if m := pattern.search(s):
                        self.add(field, fix(m.group(1)), None, _Read(span_words(line, m)), "ocr.note")

    # --- way labels -------------------------------------------------------------------------------

    @staticmethod
    def label_words(lines: Iterable[OcrLine]) -> list[tuple[str, OcrWord, bool]]:
        """Every upright word that reads as a way label: (way id, word, whether Q was restored)."""
        out = []
        for line in lines:
            for w in line.words:
                if m := LABEL.match(w.text):
                    out.append((f"Q{m.group(1)}", w, not w.text.startswith("Q")))
        return out

    def label_row(self, labels: list[tuple[str, OcrWord, bool]]) -> list[tuple[str, OcrWord, bool]]:
        """The largest row of labels (the diagram's way labels), left to right; ties go to the top row."""
        if not labels:
            return []
        tol = 0.75 * median(w.bbox[3] - w.bbox[1] for _, w, _ in labels)
        ordered = sorted(labels, key=lambda t: self.level(t[1].bbox))
        rows, row = [], [ordered[0]]
        for item in ordered[1:]:
            if abs(self.level(item[1].bbox) - self.level(row[-1][1].bbox)) <= tol:
                row.append(item)
            else:
                rows.append(row)
                row = [item]
        rows.append(row)
        best = max(rows, key=len)  # max keeps the first (topmost) of equal rows
        seen, out = set(), []
        for item in sorted(best, key=lambda t: t[1].bbox[0]):
            if item[0] not in seen:  # one label per way
                seen.add(item[0])
                out.append(item)
        return out

    # --- vertical way texts -----------------------------------------------------------------------

    @staticmethod
    def rating_words(line: OcrLine) -> tuple[list[OcrWord], list[tuple[str, str, bool]]] | None:
        """The rating grammar from the line start: device word, then rating, poles, breaking capacity or TBC.

        Returns the kept words and the parsed tokens ``(kind, value, fixed)``; None if the line does not
        start with a device word. Words after the first one that fits no token are dropped.
        """
        words = line.words
        first = next((i for i, w in enumerate(words) if DEVICE.match(w.text)), None)
        if first is None or first > 0:
            return None
        kept, tokens = [words[0]], [("device", words[0].text, False)]
        for w in words[1:]:
            t = w.text
            if t == "TBC":
                tokens.append(("tbc", t, False))
            elif m := re.fullmatch(rf"({DIGITISH}+)[kK][aA]", t):
                v, f = digits(m.group(1))
                if not v.isdigit():
                    break
                tokens.append(("ka", v, f))
            elif m := re.fullmatch(rf"({DIGITISH}+)A", t):
                v, f = digits(m.group(1))
                if not v.isdigit():
                    break
                tokens.append(("a", v, f))
            elif m := re.fullmatch(rf"({DIGITISH})[pP]", t):
                v, f = digits(m.group(1))
                if not v.isdigit():
                    break
                tokens.append(("p", v, f or t.endswith("p")))
            else:
                break
            kept.append(w)
        return kept, tokens

    def way_texts(self, rotated: list[OcrLine], labels: list[tuple[str, OcrWord, bool]]) -> bool:
        """Vertical rating and description texts of the ways; False when no rating text belongs to a label
        (then the labels are not the diagram's way labels, as in the DXF rules: for example a front view)."""
        if not labels:
            return False
        xs = [w.bbox[0] for _, w, _ in labels]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        reach = 0.6 * median(gaps) if gaps else 6 * (labels[0][1].bbox[3] - labels[0][1].bbox[1])
        label_bottom = max(w.bbox[3] for _, w, _ in labels)

        def owner(line: OcrLine, words: list[OcrWord]) -> tuple[str, OcrWord, bool] | None:
            box = union([w.bbox for w in words])
            cx = (box[0] + box[2]) / 2
            if box[1] < label_bottom:  # way texts hang below the labels
                return None
            left = [lb for lb in labels if lb[1].bbox[0] <= cx]
            if not left or cx - left[-1][1].bbox[0] > reach:
                return None
            return left[-1]

        ratings: dict[str, tuple[OcrLine, list[OcrWord], list]] = {}
        for line in rotated:
            parsed = self.rating_words(line)
            if parsed is None:
                continue
            kept, tokens = parsed
            lab = owner(line, kept)
            if lab is None:
                continue
            best = ratings.get(lab[0])
            if best is None or sum(w.conf for w in kept) / len(kept) > sum(w.conf for w in best[1]) / len(best[1]):
                ratings[lab[0]] = (line, kept, tokens)
        if not ratings:
            return False
        for way, (_, kept, tokens) in ratings.items():
            f = f"way.{way}"
            fixes = [t for t in tokens if t[2]]
            note = "OCR characters read as digits" if fixes else None
            r = _Read(kept, bool(fixes), note)
            reading = self.ways.setdefault(way, WayReading(way=way))
            reading.sources.append(self._clip(union([w.bbox for w in kept])))
            device = norm.device(tokens[0][1])
            reading.device = device
            self.add(f"{f}.device", device, None, r, "ocr.way_rating")
            for kind, v, _ in tokens[1:]:
                if kind == "a":
                    self.add(f"{f}.rating", int(v), "A", r, "ocr.way_rating")
                    reading.rating_a = float(v) if int(v) > 0 else None
                elif kind == "tbc":
                    self.add(f"{f}.rating", None, None, r, "ocr.way_rating", derivation="stated as TBC: no value given",
                             confidence=Confidence.LOW)
                elif kind == "p":
                    self.add(f"{f}.poles", int(v), None, r, "ocr.way_rating")
                    if 1 <= int(v) <= 4:
                        reading.poles = int(v)
                elif kind == "ka":
                    self.add(f"{f}.breaking_capacity", int(v), "kA", r, "ocr.way_rating")
                    reading.breaking_ka = float(v) if int(v) > 0 else None

        tops = [union([w.bbox for w in kept])[1] for _, kept, _ in ratings.values()]  # never empty here
        height = median(w.bbox[3] - w.bbox[1] for _, w, _ in labels)
        descriptions: dict[str, tuple[float, list[OcrWord]]] = {}
        for line in rotated:
            if self.rating_words(line) is not None:
                continue
            words = list(line.words)
            while words and words[-1].conf < 50:  # symbol pieces after the text
                words.pop()
            if not words or sum(w.conf for w in words) / len(words) < 70:
                continue
            if sum(c.isalpha() for c in "".join(w.text for w in words)) < 2:
                continue
            box = union([w.bbox for w in words])
            if tops and abs(box[1] - median(tops)) > 3 * height:  # way texts start level with the ratings
                continue
            lab = owner(line, words)
            if lab is None:
                continue
            rating = ratings.get(lab[0])
            if rating is not None and (box[0] + box[2]) / 2 <= (union([w.bbox for w in rating[1]])[0]
                                                                 + union([w.bbox for w in rating[1]])[2]) / 2:
                continue  # the description is printed to the right of the rating
            cx = (box[0] + box[2]) / 2
            if lab[0] not in descriptions or cx < descriptions[lab[0]][0]:
                descriptions[lab[0]] = (cx, words)
        for way, (_, words) in descriptions.items():
            r = _Read(words)
            self.add(f"way.{way}.description", r.text, None, r, "ocr.way_description")
            reading = self.ways.setdefault(way, WayReading(way=way))
            reading.description = r.text
            reading.sources.append(self._clip(union([w.bbox for w in words])))
        return True

    def way_count(self, labels: list[tuple[str, OcrWord, bool]]) -> None:
        if not labels:
            return
        ids = [lab[0] for lab in labels]
        numbers = sorted(int(i[1:]) for i in ids)
        complete = numbers == list(range(1, len(numbers) + 1))
        missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
        derivation = f"counted {len(ids)} way labels on sheet {self.sheet.sheet}: {', '.join(ids)}"
        if missing:
            derivation += f"; not read: {', '.join(f'Q{n}' for n in missing)}"
        restored = any(lab[2] for lab in labels)
        r = _Read([lab[1] for lab in labels], restored, "a label read as 0 or O taken as Q" if restored else None)
        self.add("ways.count", len(ids), None, r, "ocr.way_labels", derivation=derivation,
                 confidence=None if complete else Confidence.LOW)

    # --- cable schedule ---------------------------------------------------------------------------

    def schedule(self, upright: list[OcrLine], labels: list[tuple[str, OcrWord, bool]]) -> set[int]:
        """Rows of the cable schedule; returns the ids of the label words used, so they are not way labels."""
        used: set[int] = set()
        cables = []
        for line in upright:
            text = line.text.strip(" '/.|")
            if m := CABLE.match(text):
                cables.append((line, m))
        lengths = [line for line in upright  # a number with at least one real digit, not a lone letter
                   if LENGTH.match(line.text) and re.search(r"\d", line.text) and int(digits(line.text)[0]) > 0]
        for way, word, restored in labels:
            row_y, h = self.level(word.bbox), word.bbox[3] - word.bbox[1]
            row = [(ln, m) for ln, m in cables
                   if abs(self.level(ln.words[0].bbox) - row_y) <= 0.6 * h and ln.bbox[0] > word.bbox[2]]
            if not row:
                continue
            used.add(id(word))
            line, m = min(row, key=lambda t: abs(self.level(t[0].words[0].bbox) - row_y))
            parts = [digits(g, {"A": "4"}) if g else (None, False) for g in m.groups()[:3]]
            (n, f1), (cores, f2), (size, f3) = parts
            if not (cores.isdigit() and size.isdigit() and (n is None or n.isdigit())):
                continue
            cable = f"{n}x {cores}C {size} mm2 {m.group(4)}" if n else f"{cores}C {size} mm2 {m.group(4)}"
            fixed = f1 or f2 or f3 or restored
            note = "OCR characters read as digits" if (f1 or f2 or f3) else None
            if restored:
                note = "; ".join(x for x in (note, "a label read as 0 or O taken as Q") if x)
            self.add(f"way.{way}.cable", cable, None, _Read(line.words, fixed, note), "ocr.schedule",
                     derivation=None if cable == line.text else f"read as {line.text!r}")
            self.ways.setdefault(way, WayReading(way=way)).cable = cable
            right = [ln for ln in lengths
                     if abs(self.level(ln.bbox) - row_y) <= 0.6 * h
                     and 0 <= ln.bbox[0] - line.bbox[2] <= 0.06 * self.sheet.width_px]
            if right:
                ln = min(right, key=lambda t: abs(self.level(t.bbox) - row_y))
                v, f = digits(ln.text)
                self.add(f"way.{way}.cable_length", int(v), "m", _Read(ln.words, f or restored), "ocr.schedule")
        return used

    # --- all --------------------------------------------------------------------------------------

    def run(self) -> list[ExtractedValue]:
        upright = [ln for ln in self.sheet.lines if not ln.rotated]
        rotated = [ln for ln in self.sheet.lines if ln.rotated]
        self.facts(upright)
        all_labels = self.label_words(upright)
        in_schedule = self.schedule(upright, all_labels)
        labels = self.label_row([lab for lab in all_labels if id(lab[1]) not in in_schedule])
        if self.way_texts(rotated, labels):
            self.labels = labels
            self.way_count(labels)
        return self.values


def span_words(line: OcrLine, m: re.Match[str]) -> list[OcrWord]:
    """The words of ``line`` from where a match on ``line.text`` starts to the end of the line.

    Symbol pieces read before the text are left out; the rest of the line is kept, as a DXF text keeps
    its whole string (``ACB 2500A 4P 50kA`` for the incomer rating). Words are joined by single spaces.
    """
    out, start = [], 0
    for w in line.words:
        end = start + len(w.text)
        if end > m.start():
            out.append(w)
        start = end + 1
    return out or line.words


def _fix_note(raw: str, fixed: str) -> str | None:
    return f"OCR text {raw!r} read as {fixed!r}" if raw != fixed else None


def link_sheet(sheet: SheetOcr, file: str) -> tuple[list[ExtractedValue], DrawingReading]:
    """Values of one OCR'd sheet, and its :class:`DrawingReading` (texts with boxes, ways)."""
    linker = Linker(sheet, file)
    values = linker.run()
    texts = []
    for line in sheet.lines:
        if line.conf < MIN_TEXT_CONF or not re.search(r"[A-Za-z0-9]{2}", line.text):
            continue
        texts.append(TextBox(text=line.text, bbox=linker._clip(line.bbox), confidence=round(line.conf, 1)))
    labels = [TextBox(text=way, bbox=linker._clip(w.bbox), confidence=w.conf) for way, w, _ in linker.labels]
    reading = DrawingReading(file=file, version=sheet.version, sheet=sheet.sheet, method=Method.OCR,
                             width_px=sheet.width_px, height_px=sheet.height_px, texts=texts, labels=labels,
                             ways=sorted(linker.ways.values(), key=lambda w: int(w.way[1:])),
                             seconds=round(sheet.seconds, 3))
    return values, reading
