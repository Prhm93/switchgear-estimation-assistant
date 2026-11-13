"""One command for the Stage 7 evaluation: every method on a set, written to docs/evaluation.md.

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m data_generator build --set fresh       # once; writes FROZEN.sha256
    .venv\\Scripts\\python.exe -m backend.evaluation_report --set fresh  # the held-out set first
    .venv\\Scripts\\python.exe -m backend.evaluation_report --set test   # then the baseline, added beside it

What it runs, on the frozen **fresh** set (seeds 3001 to 3020, never used for tuning) and, for comparison, on the
**test** set (labelled "not held out", because the rules, the linker and the detector were built while looking
at it):

- field values: precision, recall and F1 per field group and over all fields, for the rules with the DXF, the
  rules without the DXF (drawing not read), the rules plus OCR on each drawing version (no DXF), and the rules
  plus the model (recorded runs; "waiting for Colab recordings" when there are none for the set);
- the symbol detector: precision and recall per drawing version (IoU at least 0.5, the Stage 4 scorer);
- confidence calibration (Stage 6): share right per level, with the DXF and with OCR on the scanned drawing;
- cross-checks with the Stage 6 gate: planted conflicts found and false flags;
- an error analysis: the most common wrong and missed field groups, with examples.

**Nothing is lost when a run stops.** Every project of every row is saved as soon as it is done, in
``data/eval-<set>-partial.json`` (git-ignored); a new run of the same command skips what is saved and carries on.
Rows run in this order: rules, rules plus OCR (clean, scanned, photo: one version at a time), the detector (one
version at a time), then the model rows. Each drawing is read by OCR once per run: calibration and cross-checks
are worked out from the same reading, not read again. Before each project the free memory is checked; under
800 MB the run waits five minutes and checks again (it never stops on its own). ``docs/evaluation.md`` is written
from whatever sets are complete, so the fresh set can be reported before the baseline has run.

Before anything runs on the fresh set its files are checked against ``FROZEN.sha256``; a changed set is refused.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from backend.app import normalise as norm
from backend.app.evaluation import Score, field_group, total
from backend.app.paths import REPO_ROOT

DOC = REPO_ROOT / "docs" / "evaluation.md"
PARTIAL = REPO_ROOT / "data" / "eval-{set}-partial.json"
VERSIONS = ("clean", "scanned", "photo")
WAITING = "waiting for Colab recordings"
MEMORY_FLOOR_MB = 800
MEMORY_WAIT_S = 300
LABELS = {"fresh": "Fresh set, not used for tuning", "test": "Baseline: test set, not held out",
          "reworded": "Reworded set, not held out"}


# --- cells and tables ----------------------------------------------------------------------------------------

def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def cell(s: Score | None) -> str:
    if s is None:
        return WAITING
    return f"{_f(s.precision)}, {_f(s.recall)}, **{_f(s.f1)}** ({s.tp}/{s.fp}/{s.fn})"


def mismatches(extracted: Iterable, truth: Iterable) -> tuple[list, list]:
    """Wrong extracted values and missed answer-key values, by the scorer's own one-to-one rule."""
    pending: dict[tuple, list] = {}
    for t in truth:
        pending.setdefault((t.field, t.source.document.value, t.source.page), []).append(t)
    wrong = []
    for e in extracted:
        candidates = pending.get((e.field, e.source.document.value, e.source.page), [])
        hit = next((t for t in candidates if norm.same(t.value, t.unit, e.value, e.unit)), None)
        if hit is None:
            # what the key says for the same field and page, if anything: the most useful example
            wrong.append((e, candidates[0] if candidates else None))
        else:
            candidates.remove(hit)
    missed = [t for left in pending.values() for t in left]
    return wrong, missed


def plain(wrong: list, missed: list) -> tuple[list[dict], list[dict]]:
    """The mismatches as plain dicts (saved in the partial file, read by :func:`error_analysis`)."""
    w = [{"field": e.field, "value": e.value, "unit": e.unit, "doc": e.source.document.value,
          "page": e.source.page, "method": e.method.value,
          "key": None if t is None else f"{t.value} {t.unit or ''}".strip()} for e, t in wrong]
    m = [{"field": t.field, "value": t.value, "unit": t.unit, "doc": t.source.document.value,
          "page": t.source.page} for t in missed]
    return w, m


def error_analysis(examples: list[tuple[str, list[dict], list[dict]]], top: int = 6, per_group: int = 2) -> str:
    """Counts of wrong and missed values per field group, with a few examples each."""
    lines = []
    for label, wrong, missed in examples:
        lines += [f"**{label}**", ""]
        w = Counter(field_group(e["field"]) for e in wrong)
        m = Counter(field_group(t["field"]) for t in missed)
        if not wrong and not missed:
            lines += ["No wrong or missed values.", ""]
            continue
        lines += ["| Field group | Wrong | Missed | Examples |", "|---|---|---|---|"]
        for group, _ in (w + m).most_common(top):
            ex = []
            for e in [x for x in wrong if field_group(x["field"]) == group][:per_group]:
                said = e["key"] if e["key"] is not None else "nothing on that page"
                ex.append(f"read {e['value']} {e['unit'] or ''} on {e['doc']} p{e['page']} ({e['method']}); "
                          f"key: {said}")
            for t in [x for x in missed if field_group(x["field"]) == group][:per_group]:
                ex.append(f"missed {t['value']} {t['unit'] or ''} on {t['doc']} p{t['page']}")
            text = "; ".join(x.replace("|", "/").replace("  ", " ") for x in ex)
            lines.append(f"| {group} | {w[group]} | {m[group]} | {text} |")
        lines.append("")
    return "\n".join(lines)


def per_field(columns: list[tuple[str, dict[str, Score]]]) -> list[str]:
    """F1 (TP/FP/FN) per field group, one column per method."""
    groups = sorted({g for _, grouped in columns for g in grouped})
    out = ["| Field group | " + " | ".join(label for label, _ in columns) + " |", "|---" * (len(columns) + 1) + "|"]
    for g in groups:
        cells = []
        for _, grouped in columns:
            sc = grouped.get(g)
            cells.append("" if sc is None else f"{_f(sc.f1)} ({sc.tp}/{sc.fp}/{sc.fn})")
        out.append(f"| {g} | " + " | ".join(cells) + " |")
    return out


# --- the partial file: one entry per project of every row ----------------------------------------------------

class Partial:
    """``data/eval-<set>-partial.json``: ``{"set": ..., "done": {"<row>|<project>": result}}``, saved after each."""

    def __init__(self, path: Path, set_name: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {"set": set_name, "done": {}}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if loaded.get("set") == set_name:
                self.data = loaded

    def get(self, row: str, project: str) -> Any:
        return self.data["done"].get(f"{row}|{project}")

    def put(self, row: str, project: str, result: Any) -> None:
        self.data["done"][f"{row}|{project}"] = result
        tmp = self.path.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(self.data), encoding="utf-8")
        os.replace(tmp, self.path)  # a stop during the write never leaves half a file

    def rows(self, row: str, projects: list[str]) -> list[Any] | None:
        """The saved results of every project of ``row``, or None if any is missing."""
        out = [self.get(row, p) for p in projects]
        return None if any(x is None for x in out) else out


def free_memory_mb() -> float | None:
    """Free physical memory in MB (Windows and Linux), or None when it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            s = Status()
            s.dwLength = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return s.ullAvailPhys / 2**20
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024
    except Exception:  # noqa: BLE001 - the guard must never stop the run
        return None
    return None


def wait_for_memory(read: Callable[[], float | None] = free_memory_mb, sleep: Callable[[float], None] = time.sleep,
                    floor: float = MEMORY_FLOOR_MB, pause: float = MEMORY_WAIT_S) -> int:
    """Wait (``pause`` seconds at a time) until at least ``floor`` MB are free. Returns how many waits."""
    waits = 0
    while (free := read()) is not None and free < floor:
        print(f"  free memory {free:.0f} MB, under {floor:.0f} MB: waiting {pause / 60:.0f} min", file=sys.stderr)
        gc.collect()
        sleep(pause)
        waits += 1
    return waits


# --- running the rows ----------------------------------------------------------------------------------------

def _scores(grouped: dict[str, Score]) -> dict[str, list[int]]:
    return {g: [s.tp, s.fp, s.fn] for g, s in grouped.items()}


def _grouped(saved: list[dict]) -> dict[str, Score]:
    out: dict[str, Score] = {}
    for r in saved:
        for g, (tp, fp, fn) in r["scores"].items():
            out.setdefault(g, Score()).add(Score(tp=tp, fp=fp, fn=fn))
    return out


READINGS: dict[str, dict[str, Any]] = {
    "rules_dxf": {"with_dxf": True, "mode": "rules"},
    "rules_nodxf": {"with_dxf": False, "mode": "rules"},
    **{f"ocr_{v}": {"with_dxf": False, "mode": "rules", "drawing_reading": "ocr", "drawing_version": v}
       for v in VERSIONS},
}


def read_project(set_name: str, folder: Path, row: str, options: dict[str, Any]) -> dict:
    """One project read one way: its scores, mismatches and, where used, calibration and cross-check counts."""
    from backend.app.evaluation import score
    from backend.calibration import project_pairs
    from backend.crosschecks import score_project
    from backend.evaluate import project_values
    from data_generator.project import load_answers

    key = load_answers(folder / "answers.json")
    start = time.perf_counter()
    values = project_values(folder, set_name=set_name, **options)
    seconds = time.perf_counter() - start
    wrong, missed = plain(*mismatches(values, key.values))
    result: dict[str, Any] = {"scores": _scores(score(values, key.values)), "wrong": wrong, "missed": missed,
                              "seconds": round(seconds, 2)}
    if row in ("rules_dxf", "ocr_scanned"):
        result["calibration"] = [[lv, ok] for lv, _, ok in project_pairs(values, key.values)]
    if row == "rules_dxf":
        cc = score_project(key, values, gate=True)
        result["cross"] = {k: len(v) for k, v in cc.items()}
    return result


def detect_project(samples: list, detector) -> dict:
    from backend.drawings import score_symbols

    totals, seconds = score_symbols(samples, detector)
    return {"classes": {c: [t["tp"], t["fp"], t["fn"]] for c, t in totals.items()}, "seconds": seconds}


def run_set(set_name: str, folders: list[Path], versions: tuple[str, ...], partial: Partial,
            guard: Callable[[], Any] = wait_for_memory) -> None:
    """Every row of the set, project by project, skipping what the partial file already holds."""
    names = [f.name for f in folders]

    def each(row: str, work: Callable[[Path], Any]) -> None:
        todo = [f for f in folders if partial.get(row, f.name) is None]
        if not todo:
            print(f"  {row}: saved", file=sys.stderr)
            return
        for f in todo:
            guard()
            partial.put(row, f.name, work(f))
            gc.collect()
        print(f"  {row}: done ({len(names)} projects)", file=sys.stderr)

    for row in ("rules_dxf", "rules_nodxf", *(f"ocr_{v}" for v in versions)):
        each(row, lambda f, row=row: read_project(set_name, f, row, READINGS[row]))
    detector = None
    for v in versions:
        row = f"detector_{v}"
        if all(partial.get(row, n) is not None for n in names):
            print(f"  {row}: saved", file=sys.stderr)
            continue
        from backend.app.drawing.data import evaluation_drawings
        from backend.app.drawing.symbols import TemplateDetector

        detector = detector or TemplateDetector()
        samples = [s for s in evaluation_drawings(set_name) if s.version.value == v]
        each(row, lambda f, samples=samples: detect_project([s for s in samples if s.project_id == f.name], detector))
        del samples
    from backend.evaluate import columns, has_recordings

    v2 = next(c for c in columns() if c.label == "v2")
    if has_recordings(v2, folders, set_name):
        for dxf in (True, False):
            row = f"combined_{'dxf' if dxf else 'nodxf'}"
            each(row, lambda f, dxf=dxf, row=row: read_project(
                set_name, f, row, {"with_dxf": dxf, "mode": "combined", "recorded_dir": v2.recorded_dir,
                                   "prompt_version": v2.prompt_version}))


# --- writing the report from the saved rows -------------------------------------------------------------------

def _calibration(saved: list[dict]) -> str:
    from backend.calibration import calibration_table, tally

    return calibration_table(tally((lv, ok) for r in saved for lv, ok in r["calibration"]))


def section(set_name: str, label: str, names: list[str], versions: tuple[str, ...], partial: Partial) -> str | None:
    """The report section of one set, or None while a row of it is still missing."""
    needed = ["rules_dxf", "rules_nodxf", *(f"ocr_{v}" for v in versions), *(f"detector_{v}" for v in versions)]
    got = {row: partial.rows(row, names) for row in needed}
    if any(v is None for v in got.values()):
        return None
    rows = ["| Method | Drawing | P, R, **F1** (TP/FP/FN) |", "|---|---|---|"]
    fields: list[tuple[str, dict[str, Score]]] = []
    examples = []
    seconds = 0.0

    def add(row: str, method: str, drawing: str, column: str) -> None:
        nonlocal seconds
        grouped = _grouped(got[row])
        seconds += sum(r["seconds"] for r in got[row])
        rows.append(f"| {method} | {drawing} | {cell(total(grouped))} |")
        fields.append((column, grouped))

    add("rules_dxf", "Rules", "DXF", "Rules, DXF")
    examples.append(("Rules, with the DXF", [w for r in got["rules_dxf"] for w in r["wrong"]],
                     [m for r in got["rules_dxf"] for m in r["missed"]]))
    add("rules_nodxf", "Rules", "none (drawing not read)", "Rules, no drawing")
    for v in versions:
        add(f"ocr_{v}", "Rules + OCR", f"{v}, no DXF", f"Rules + OCR, {v}")
    if "ocr_scanned" in got:
        examples.append(("Rules + OCR, scanned drawing, no DXF", [w for r in got["ocr_scanned"] for w in r["wrong"]],
                         [m for r in got["ocr_scanned"] for m in r["missed"]]))
    for dxf in ("dxf", "nodxf"):
        saved = partial.rows(f"combined_{dxf}", names)
        drawing = "DXF" if dxf == "dxf" else "none"
        if saved is None:
            rows.append(f"| Rules + model | {drawing} | {WAITING} |")
        else:
            got[f"combined_{dxf}"] = saved
            add(f"combined_{dxf}", "Rules + model (v2, strict)", drawing, f"Rules + model, {drawing}")
    det = ["| Version | TP | FP | FN | P | R | F1 | acb found | s/sheet |", "|---|---|---|---|---|---|---|---|---|"]
    for v in versions:
        classes: dict[str, list[int]] = {}
        secs: list[float] = []
        for r in got[f"detector_{v}"]:
            secs += r["seconds"]
            for c, (tp, fp, fn) in r["classes"].items():
                t = classes.setdefault(c, [0, 0, 0])
                t[0], t[1], t[2] = t[0] + tp, t[1] + fp, t[2] + fn
        tp, fp, fn = (sum(t[i] for t in classes.values()) for i in range(3))
        acb = classes.get("acb", [0, 0, 0])
        s = Score(tp=tp, fp=fp, fn=fn)
        seconds += sum(secs)
        det.append(f"| {v} | {tp} | {fp} | {fn} | {_f(s.precision)} | {_f(s.recall)} | {_f(s.f1)} | "
                   f"{acb[0]} of {acb[0] + acb[2]} | {statistics.mean(secs) if secs else 0:.2f} |")
    cross = {k: sum(r["cross"][k] for r in got["rules_dxf"]) for k in got["rules_dxf"][0]["cross"]}
    tp, fp = cross["found"], cross["false"]
    cal_ocr = (_calibration(got["ocr_scanned"]) if "ocr_scanned" in got
               else "Not run (the scanned version was not in this run).")
    return "\n".join([
        f"## {label}", "",
        f"{len(names)} projects ({names[0]} to {names[-1]}); {seconds / 60:.0f} min of reading on the laptop.", "",
        "### Field values (all fields, micro-averaged)", "", *rows, "",
        "### Field values per field group: F1 (TP/FP/FN)", "", *per_field(fields), "",
        "### Symbol detector (template; breaker classes, IoU at least 0.5)", "", *det, "",
        "### Confidence calibration (Stage 6), rules with the DXF", "", _calibration(got["rules_dxf"]), "",
        "### Confidence calibration, rules + OCR on the scanned drawing (no DXF)", "", cal_ocr, "",
        "### Cross-checks with the Stage 6 gate, rules with the DXF", "",
        f"Planted conflicts found: {tp} of {cross['planted']}; false flags: {fp}. Planted missing values listed: "
        f"{cross['missing_found']} of {cross['missing_planted']}.", "",
        "### Error analysis", "", error_analysis(examples)])


def folders_of(set_name: str, count: int | None) -> list[Path]:
    root = REPO_ROOT / "data" / "projects" / set_name
    return sorted(p.parent for p in root.glob("*/answers.json"))[:count]


def write_doc(out: Path, versions: tuple[str, ...], count: int | None, set_hash: str | None,
              partial_path: str = str(PARTIAL)) -> list[str]:
    """docs/evaluation.md from every complete set (fresh first, then the baseline). Returns the sets written."""
    parts, written = [], []
    for set_name in ("fresh", "test", "reworded"):
        path = Path(partial_path.format(set=set_name))
        names = [f.name for f in folders_of(set_name, count)]
        if not path.exists() or not names:
            continue
        label = LABELS[set_name] + (f" (set hash {set_hash[:16]})" if set_name == "fresh" and set_hash else "")
        text = section(set_name, label, names, versions, Partial(path, set_name))
        if text:
            parts.append(text)
            written.append(set_name)
    head = ["# Evaluation", "",
            "Written by `python -m backend.evaluation_report`. Every number below was run on the laptop; a row that "
            f"needs model recordings says \"{WAITING}\". Field cells are P, R, **F1** (TP/FP/FN); a value counts when "
            "its field, file, page, value and unit match the answer key (docs/stage-2.md).", ""]
    if parts:
        out.write_text("\n".join(head + parts) + "\n", encoding="utf-8")
    return written


def main(argv: list[str] | None = None) -> int:
    from data_generator.sets import check_frozen

    parser = argparse.ArgumentParser(prog="python -m backend.evaluation_report", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", default="fresh", choices=["fresh", "test", "reworded"])
    parser.add_argument("--versions", nargs="+", default=list(VERSIONS), choices=VERSIONS)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--out", type=Path, default=DOC)
    parser.add_argument("--write-only", action="store_true", help="write the report from the saved rows, run nothing")
    args = parser.parse_args(argv)
    fresh = REPO_ROOT / "data" / "projects" / "fresh"
    problem = check_frozen(fresh) if (fresh / "FROZEN.sha256").exists() else "FROZEN.sha256 is missing"
    if args.set_name == "fresh" and problem:
        print(f"the fresh set is not as frozen: {problem}", file=sys.stderr)
        return 2
    set_hash = None if problem else (fresh / "FROZEN.sha256").read_text(encoding="utf-8").strip().splitlines()[-1].split()[-1]
    versions = tuple(args.versions)
    if not args.write_only:
        folders = folders_of(args.set_name, args.count)
        if not folders:
            print(f"build the set first: python -m data_generator build --set {args.set_name}", file=sys.stderr)
            return 2
        path = Path(str(PARTIAL).format(set=args.set_name))
        print(f"{args.set_name}: {len(folders)} projects; saved rows in {path}", file=sys.stderr)
        run_set(args.set_name, folders, versions, Partial(path, args.set_name))
    written = write_doc(args.out, versions, args.count, set_hash)
    print(f"wrote {args.out} ({', '.join(written) or 'no complete set yet'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
