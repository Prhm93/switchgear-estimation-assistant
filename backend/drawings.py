"""Drawing data reports and the OCR measurement (Stage 4).

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m backend.drawings counts                 # the 300 training drawings
    .venv\\Scripts\\python.exe -m backend.drawings counts --set test      # the 20 test projects
    .venv\\Scripts\\python.exe -m backend.drawings counts --set reworded
    .venv\\Scripts\\python.exe -m backend.drawings ocr --set test --version scanned --dpi 300
    .venv\\Scripts\\python.exe -m backend.drawings vision --set test --version scanned  # recorded answers

``counts`` prints the symbol classes per drawing version (clean, scanned,
photo) as a Markdown table. Training data comes only from ``data/training/``;
test sets only from ``data/projects/test`` and ``data/projects/reworded``.

``ocr`` reads every sheet of one drawing version of a test set by OCR and
scores the drawing values alone against the answer key (same rules as
:mod:`backend.app.evaluation`), per field group, plus:

- the four summary groups: ratings (way, incomer and busbar ratings), poles,
  breaking capacity, and way labels (each diagram label read, as a way id,
  against the ways of that sheet in the answer key);
- the frozen DXF rules on the same sheets, for reference (what reading the
  DXF text gives);
- seconds per sheet (rendering and both OCR passes), and peak memory of this
  Python process and of the largest Tesseract run.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

from backend.app.drawing.data import DATA, DrawingSample, class_counts, count_table, evaluation_drawings, training_drawings
from backend.app.evaluation import Score, score, total
from backend.app.storage import FileType

SUMMARY = {
    "ratings": ("way.*.rating", "incomer.rating", "busbar.rating"),
    "poles": ("way.*.poles", "incomer.poles"),
    "breaking capacity": ("way.*.breaking_capacity",),
}


# --- memory ------------------------------------------------------------------------------------------

class PeakMemory:
    """Peak resident memory of this process and of the largest child process (Tesseract), in MB."""

    def __init__(self) -> None:
        self.child_mb = 0.0

    @staticmethod
    def _windows_peak(handle: int) -> float:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        c = Counters()
        c.cb = ctypes.sizeof(c)
        fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not fn(handle, ctypes.byref(c), c.cb):
            return 0.0
        return c.PeakWorkingSetSize / 1e6

    def watch_children(self) -> None:
        """Record the peak of every child process started through pytesseract (Windows only)."""
        if sys.platform != "win32":
            return
        import pytesseract.pytesseract as pt

        meter = self

        class Measured(subprocess.Popen):
            def wait(self, timeout=None):  # noqa: ANN001, ANN202 - same signature as Popen.wait
                code = super().wait(timeout)
                meter.child_mb = max(meter.child_mb, meter._windows_peak(int(self._handle)))
                return code

        pt.subprocess = type(sys)("subprocess_measured")  # a module-like object: pytesseract's own reference
        for name in dir(subprocess):
            setattr(pt.subprocess, name, getattr(subprocess, name))
        pt.subprocess.Popen = Measured

    def self_mb(self) -> float:
        if sys.platform == "win32":
            import ctypes

            return self._windows_peak(ctypes.windll.kernel32.GetCurrentProcess())
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3  # KB on Linux

    def children_mb(self) -> float:
        if sys.platform == "win32":
            return self.child_mb
        import resource

        return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1e3


# --- OCR measurement ---------------------------------------------------------------------------------

def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def _row(name: str, s: Score) -> str:
    return f"| {name} | {s.tp} | {s.fp} | {s.fn} | {_f(s.precision)} | {_f(s.recall)} | {_f(s.f1)} |"


def _summary(grouped: dict[str, Score]) -> dict[str, Score]:
    out = {}
    for name, groups in SUMMARY.items():
        s = Score()
        for g in groups:
            if g in grouped:
                s.add(grouped[g])
        out[name] = s
    return out


def measure_ocr(samples: list[DrawingSample], dpi: int) -> str:
    from backend.app.drawing.link import link_sheet
    from backend.app.drawing.ocr import ocr_drawing, tesseract_version
    from backend.app.pipeline import analyse_file

    version = tesseract_version()
    if version is None:
        raise SystemExit("Tesseract not found: install it (docs/stage-4.md) or set TESSERACT_CMD")
    meter = PeakMemory()
    meter.watch_children()
    ocr_grouped: dict[str, Score] = {}
    dxf_grouped: dict[str, Score] = {}
    labels = Score()
    seconds: list[float] = []
    dxf_cache: dict = {}
    for s in samples:
        file_type = FileType.PDF if s.path.suffix.lower() == ".pdf" else FileType.PNG
        start = time.perf_counter()
        sheets = ocr_drawing(file_type, s.path.read_bytes(), s.path.name, dpi=dpi)
        sheet = next(x for x in sheets if x.sheet == s.sheet)
        if file_type == FileType.PDF:
            seconds.append(sheet.seconds)  # the PDF is read once for both sheets; each sheet has its own time
        else:
            seconds.append(time.perf_counter() - start)
        values, reading = link_sheet(sheet, s.path.name)
        for g, sc in score(values, s.values).items():
            ocr_grouped.setdefault(g, Score()).add(sc)
        truth_ways = {sym.way for sym in s.symbols if sym.way}
        read_ways = {t.text for t in reading.labels}
        labels.add(Score(tp=len(read_ways & truth_ways), fp=len(read_ways - truth_ways),
                         fn=len(truth_ways - read_ways)))
        dxf = s.path.parent / "schematic.dxf"
        if dxf not in dxf_cache:
            dxf_cache[dxf] = analyse_file(FileType.DXF, dxf.read_bytes(), "schematic.dxf").values
        sheet_dxf = [v for v in dxf_cache[dxf] if v.source.page == s.sheet]
        for g, sc in score(sheet_dxf, s.values).items():
            dxf_grouped.setdefault(g, Score()).add(sc)

    head = "| Field | TP | FP | FN | Precision | Recall | F1 |\n|---|---|---|---|---|---|---|"
    out = [f"Tesseract {version}; {len(samples)} sheets; dpi {dpi}"
           + (" (images enlarged twice)" if dpi == 300 else ""),
           f"seconds per sheet: mean {statistics.mean(seconds):.2f}, max {max(seconds):.2f}; "
           f"peak memory: Python {meter.self_mb():.0f} MB, largest Tesseract run {meter.children_mb():.0f} MB", ""]
    out += ["### Summary: OCR, and the DXF rules on the same sheets for reference", "",
            "| Group | OCR TP | FP | FN | P | R | F1 | DXF rules F1 |", "|---|---|---|---|---|---|---|---|"]
    ocr_s, dxf_s = _summary(ocr_grouped), _summary(dxf_grouped)
    for name in SUMMARY:
        a, b = ocr_s[name], dxf_s[name]
        out.append(f"| {name} | {a.tp} | {a.fp} | {a.fn} | {_f(a.precision)} | {_f(a.recall)} | {_f(a.f1)} | "
                   f"{_f(b.f1)} |")
    out.append(f"| way labels | {labels.tp} | {labels.fp} | {labels.fn} | {_f(labels.precision)} | "
               f"{_f(labels.recall)} | {_f(labels.f1)} | n/a |")
    a, b = total(ocr_grouped), total(dxf_grouped)
    out.append(f"| **all drawing fields** | {a.tp} | {a.fp} | {a.fn} | {_f(a.precision)} | {_f(a.recall)} | "
               f"{_f(a.f1)} | {_f(b.f1)} |")
    out += ["", "### OCR per field group", "", head]
    out += [_row(f"`{g}`", ocr_grouped[g]) for g in sorted(ocr_grouped)]
    return "\n".join(out)


def measure_vision(samples: list[DrawingSample], folder: Path) -> str:
    """Score the recorded vision answers alone (no OCR) against the answer keys, as for OCR.

    Sheets without a recording are counted and listed as missing, never scored as empty readings.
    """
    import hashlib

    from backend.app.drawing.vision import RecordedVisionClient, VisionUnavailable, vision_values

    try:
        client = RecordedVisionClient(folder)
    except VisionUnavailable as error:
        return f"NOT RUN YET: {error}. Make the recordings on Colab (docs/stage-4-colab-vision.md)."
    grouped: dict[str, Score] = {}
    missing = 0
    for s in samples:
        data = s.path.read_bytes()
        try:
            output = client.read(file_sha256=hashlib.sha256(data).hexdigest(), sheet=s.sheet, image=lambda: b"")
        except VisionUnavailable:
            missing += 1
            continue
        values = vision_values(output, file=s.path.name, version=s.version, sheet=s.sheet, ocr_text="", filled=set())
        for g, sc in score(values, s.values).items():
            grouped.setdefault(g, Score()).add(sc)
    out = [f"{len(samples) - missing} of {len(samples)} sheets have a recording ({client.label})", "",
           "| Group | TP | FP | FN | P | R | F1 |", "|---|---|---|---|---|---|---|"]
    for name, s in _summary(grouped).items():
        out.append(f"| {name} | {s.tp} | {s.fp} | {s.fn} | {_f(s.precision)} | {_f(s.recall)} | {_f(s.f1)} |")
    a = total(grouped)
    out.append(f"| **all vision fields** | {a.tp} | {a.fp} | {a.fn} | {_f(a.precision)} | {_f(a.recall)} | {_f(a.f1)} |")
    return "\n".join(out)


def _sheet(sample: DrawingSample):
    from backend.app.drawing.render import sheet_image

    file_type = FileType.PDF if sample.path.suffix.lower() == ".pdf" else FileType.PNG
    return sheet_image(file_type, sample.path.read_bytes(), sample.page or 1)


def build_symbol_templates(samples: list[DrawingSample], per_class: int = 60) -> dict:
    """Average crops of the breaker classes from training drawings (clean versions only)."""
    from backend.app.drawing.data import DataMixError
    from backend.app.drawing.symbols import BREAKER_CLASSES, WORK_SCALE, build_templates, ink

    if any(s.purpose != "training" for s in samples):
        raise DataMixError("templates are built from training drawings only")
    crops: dict = {c: [] for c in BREAKER_CLASSES}
    for s in samples:
        if s.version.value != "clean" or not any(sym.cls in crops for sym in s.symbols):
            continue
        if all(len(v) >= per_class for v in crops.values()):
            break
        picture = ink(_sheet(s))
        for sym in s.symbols:
            if sym.cls in crops and len(crops[sym.cls]) < per_class:
                x0, y0, x1, y1 = (round(v * WORK_SCALE) for v in sym.bbox)
                crops[sym.cls].append(picture[y0:y1, x0:x1].copy())
    return build_templates(crops)


def score_symbols(samples: list[DrawingSample], detector) -> tuple[dict, list[float]]:
    """Per-class box scores (IoU at least 0.5) of the breaker classes, and seconds per sheet."""
    from backend.app.drawing.boxes import Box, match_boxes
    from backend.app.drawing.symbols import BREAKER_CLASSES

    keep = {c.value for c in BREAKER_CLASSES}
    totals: dict = {}
    seconds = []
    for s in samples:
        image = _sheet(s)
        start = time.perf_counter()
        found = detector.detect(image)
        seconds.append(time.perf_counter() - start)
        pred = [Box(f.cls.value, f.bbox, f.score) for f in found if f.cls.value in keep]
        truth = [Box(t.cls.value, t.bbox) for t in s.symbols if t.cls.value in keep]
        for cls, sc in match_boxes(pred, truth).items():
            t = totals.setdefault(cls, {"tp": 0, "fp": 0, "fn": 0, "iou": []})
            t["tp"] += sc.tp
            t["fp"] += sc.fp
            t["fn"] += sc.fn
            if sc.mean_iou is not None:
                t["iou"] += [sc.mean_iou] * sc.tp
    return totals, seconds


def symbol_confusion(samples: list[DrawingSample], detector) -> tuple[dict, dict, dict]:
    """Box by box: which class each breaker answer box was given, and what sits inside the missed ones.

    Returns the confusion table (:func:`boxes.confusion`, IoU at least 0.5 whatever the class), for each
    missed answer box the class of a prediction whose centre lies inside it (``"(none)"`` if none), and the
    mean IoU of predictions with the centre inside a missed box, per (answer class, predicted class).
    """
    from backend.app.drawing.boxes import Box, confusion, iou
    from backend.app.drawing.symbols import BREAKER_CLASSES

    keep = {c.value for c in BREAKER_CLASSES}
    table: dict = {}
    inside: dict = {}
    inside_iou: dict = {}
    for s in samples:
        found = detector.detect(_sheet(s))
        pred = [Box(f.cls.value, f.bbox, f.score) for f in found if f.cls.value in keep]
        truth = [Box(t.cls.value, t.bbox) for t in s.symbols if t.cls.value in keep]
        part = confusion(pred, truth)
        for k, n in part.items():
            table[k] = table.get(k, 0) + n
        for t in truth:  # a missed answer box: no prediction of any class reached IoU 0.5
            best = max((iou(p.bbox, t.bbox) for p in pred), default=0.0)
            if best >= 0.5:
                continue
            hits = [p for p in pred if t.bbox[0] <= (p.bbox[0] + p.bbox[2]) / 2 <= t.bbox[2]
                    and t.bbox[1] <= (p.bbox[1] + p.bbox[3]) / 2 <= t.bbox[3]]
            hit = max(hits, key=lambda p: p.score, default=None)
            key = (t.cls, hit.cls if hit else "(none)")
            inside[key] = inside.get(key, 0) + 1
            if hit:
                inside_iou.setdefault(key, []).append(iou(hit.bbox, t.bbox))
    return table, inside, {k: statistics.mean(v) for k, v in inside_iou.items()}


def confusion_table(table: dict) -> str:
    """A markdown table: rows are answer classes, columns the class the detector gave."""
    from backend.app.drawing.boxes import MISSED, NOTHING_THERE

    rows = sorted({k[0] for k in table} - {NOTHING_THERE}) + [NOTHING_THERE]
    cols = sorted({k[1] for k in table} - {MISSED}) + [MISSED]
    lines = ["| Answer / given | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for r in rows:
        lines.append(f"| {r} | " + " | ".join(str(table.get((r, c), 0)) for c in cols) + " |")
    return "\n".join(lines)


def symbol_table(totals: dict) -> str:
    def prf(t):
        p = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else None
        r = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else None
        f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
        return p, r, f
    lines = ["| Class | TP | FP | FN | P | R | F1 | mean IoU |", "|---|---|---|---|---|---|---|---|"]
    allt = {"tp": 0, "fp": 0, "fn": 0, "iou": []}
    for cls in sorted(totals):
        t = totals[cls]
        for k in ("tp", "fp", "fn", "iou"):
            allt[k] += t[k]
        p, r, f = prf(t)
        iou = statistics.mean(t["iou"]) if t["iou"] else None
        lines.append(f"| {cls} | {t['tp']} | {t['fp']} | {t['fn']} | {_f(p)} | {_f(r)} | {_f(f)} | {_f(iou)} |")
    p, r, f = prf(allt)
    iou = statistics.mean(allt["iou"]) if allt["iou"] else None
    lines.append(f"| **all four** | {allt['tp']} | {allt['fp']} | {allt['fn']} | {_f(p)} | {_f(r)} | {_f(f)} | {_f(iou)} |")
    return "\n".join(lines)


def _symbol_training(args) -> int:
    """``templates`` and ``tune-symbols``: training drawings only, never a test set."""
    from backend.app.drawing.symbols import TEMPLATES, TemplateDetector, save_templates

    projects = sorted({s.project_id for s in training_drawings()})[:args.count]
    samples = [s for s in training_drawings() if s.project_id in projects]
    if not samples:
        print("no training drawings: build them with python -m data_generator build --set training", file=sys.stderr)
        return 2
    if args.command == "templates":
        templates = build_symbol_templates(samples)
        save_templates(templates)
        sizes = {k: v.shape for k, v in templates.items() if "__" not in k}
        print(f"templates from {len(projects)} training projects written to {TEMPLATES.name}: {sizes}")
        return 0
    if args.version != "all":
        samples = [s for s in samples if s.version.value == args.version]
    print(f"## Threshold on training drawings ({len(projects)} projects, {len(samples)} sheets)\n")
    from backend.app.drawing.boxes import Box, match_boxes
    from backend.app.drawing.symbols import BREAKER_CLASSES, ink

    thresholds = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)
    keep = {c.value for c in BREAKER_CLASSES}
    detector = TemplateDetector(threshold=min(thresholds))
    counts = {t: [0, 0, 0] for t in thresholds}
    for s in samples:  # candidates once per sheet at the lowest threshold, then filtered: the same peaks
        image = _sheet(s)
        found = detector.candidates(ink(image))
        truth = [Box(t.cls.value, t.bbox) for t in s.symbols if t.cls.value in keep]
        for threshold in thresholds:
            pred = [Box(f.cls.value, f.bbox, f.score) for f in detector.select(found, image.size, threshold)]
            for sc in match_boxes(pred, truth).values():
                counts[threshold][0] += sc.tp
                counts[threshold][1] += sc.fp
                counts[threshold][2] += sc.fn
    print("| Threshold | TP | FP | FN | F1 |\n|---|---|---|---|---|")
    for threshold, (tp, fp, fn) in counts.items():
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        print(f"| {threshold:.2f} | {tp} | {fp} | {fn} | {f1:.3f} |")
    return 0


def _symbol_confusion(args) -> int:
    """``symbol-confusion``: a diagnosis only; nothing is tuned on what it prints.

    On training drawings it uses the LAST projects, which neither the templates (first 80) nor the
    threshold (first 10) used.
    """
    from backend.app.drawing.symbols import TemplateDetector

    if args.set_name == "training":
        pool = training_drawings()
        projects = sorted({s.project_id for s in pool})[-(args.count or 20):]
    else:
        pool = evaluation_drawings(args.set_name)
        projects = sorted({s.project_id for s in pool})[:args.count] if args.count else sorted({s.project_id for s in pool})
    samples = [s for s in pool if s.project_id in projects and s.version.value == args.version]
    if not samples:
        print(f"no drawings for {args.set_name}", file=sys.stderr)
        return 2
    table, inside, inside_iou = symbol_confusion(samples, TemplateDetector())
    print(f"## Symbol confusion (template), {args.set_name} set, {args.version} ({len(projects)} projects, "
          f"{projects[0]} to {projects[-1]}, {len(samples)} sheets)\n")
    print(confusion_table(table))
    print("\nMissed answer boxes (IoU below 0.5 with every prediction): class of the best prediction whose "
          "centre lies inside the box, and its mean IoU with the box\n")
    print("| Answer | Inside it | Count | mean IoU |\n|---|---|---|---|")
    for key in sorted(inside):
        mi = inside_iou.get(key)
        print(f"| {key[0]} | {key[1]} | {inside[key]} | {_f(mi)} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.drawings", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("counts", help="symbol classes per drawing version")
    c.add_argument("--set", dest="set_name", choices=["training", "test", "reworded", "showcase"],
                   default="training")
    o = sub.add_parser("ocr", help="OCR one drawing version of a test set and score it")
    o.add_argument("--set", dest="set_name", choices=["test", "reworded", "showcase"], default="test")
    o.add_argument("--version", choices=["clean", "scanned", "photo"], default="clean")
    o.add_argument("--dpi", type=int, choices=[150, 300], default=300)
    o.add_argument("--count", type=int, default=None, help="first N projects only")
    v = sub.add_parser("vision", help="score the recorded vision answers of one drawing version")
    v.add_argument("--set", dest="set_name", choices=["test", "reworded", "showcase"], default="test")
    v.add_argument("--version", choices=["clean", "scanned", "photo"], default="scanned")
    v.add_argument("--count", type=int, default=None, help="first N projects only")
    v.add_argument("--recorded", type=Path, default=DATA / "recorded-vision")
    t = sub.add_parser("templates", help="rebuild the symbol templates from training drawings only")
    t.add_argument("--count", type=int, default=80, help="training projects to read at most")
    u = sub.add_parser("tune-symbols", help="detector F1 per threshold on training drawings only")
    u.add_argument("--count", type=int, default=10)
    u.add_argument("--version", choices=["clean", "scanned", "photo", "all"], default="all")
    d = sub.add_parser("symbols", help="score the symbol detector on one drawing version of a test set")
    d.add_argument("--set", dest="set_name", choices=["test", "reworded", "fresh", "showcase"], default="test")
    d.add_argument("--version", choices=["clean", "scanned", "photo"], default="clean")
    d.add_argument("--count", type=int, default=None, help="first N projects only")
    k = sub.add_parser("symbol-confusion", help="box by box: which class each breaker answer box was given")
    k.add_argument("--set", dest="set_name", choices=["training", "test", "reworded", "showcase"], default="training")
    k.add_argument("--version", choices=["clean", "scanned", "photo"], default="clean")
    k.add_argument("--count", type=int, default=None, help="first N projects only (training: the LAST N)")
    args = parser.parse_args(argv)
    if args.command == "symbol-confusion":
        return _symbol_confusion(args)
    if args.command in ("templates", "tune-symbols"):
        return _symbol_training(args)
    if args.command == "counts":
        samples = training_drawings() if args.set_name == "training" else evaluation_drawings(args.set_name)
    else:
        samples = [s for s in evaluation_drawings(args.set_name) if s.version.value == args.version]
        if args.count:
            keep = sorted({s.project_id for s in samples})[:args.count]
            samples = [s for s in samples if s.project_id in keep]
    if not samples:
        print(f"no drawings found for {args.set_name}: build the set with python -m data_generator build",
              file=sys.stderr)
        return 2
    projects = len({s.project_id for s in samples})
    if args.command == "counts":
        print(f"## Symbol classes, {args.set_name} ({projects} projects, {len(samples)} drawing images)\n")
        print(count_table(class_counts(samples)))
        return 0
    if args.command == "symbols":
        from backend.app.drawing.symbols import TemplateDetector

        meter = PeakMemory()
        totals, seconds = score_symbols(samples, TemplateDetector())
        print(f"## Symbol detector (template), {args.set_name} set, {args.version} drawings ({projects} projects)\n")
        print(f"{len(samples)} sheets; seconds per sheet: mean {statistics.mean(seconds):.2f}, max {max(seconds):.2f}; "
              f"peak memory: Python {meter.self_mb():.0f} MB\n")
        print(symbol_table(totals))
        return 0
    if args.command == "vision":
        print(f"## Vision (recorded), {args.set_name} set, {args.version} drawings ({projects} projects)\n")
        print(measure_vision(samples, args.recorded))
        return 0
    print(f"## OCR, {args.set_name} set, {args.version} drawings ({projects} projects)\n")
    print(measure_ocr(samples, args.dpi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
