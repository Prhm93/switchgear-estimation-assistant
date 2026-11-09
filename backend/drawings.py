"""Drawing data reports and the OCR measurement (Stage 4).

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m backend.drawings counts                 # the 300 training drawings
    .venv\\Scripts\\python.exe -m backend.drawings counts --set test      # the 20 test projects
    .venv\\Scripts\\python.exe -m backend.drawings counts --set reworded
    .venv\\Scripts\\python.exe -m backend.drawings ocr --set test --version scanned --dpi 300

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

from backend.app.drawing.data import DrawingSample, class_counts, count_table, evaluation_drawings, training_drawings
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
    args = parser.parse_args(argv)
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
    print(f"## OCR, {args.set_name} set, {args.version} drawings ({projects} projects)\n")
    print(measure_ocr(samples, args.dpi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
