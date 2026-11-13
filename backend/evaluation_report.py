"""One command for the Stage 7 evaluation: every method on a set, written to docs/evaluation.md.

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m data_generator build --set fresh       # once; writes FROZEN.sha256
    .venv\\Scripts\\python.exe -m backend.evaluation_report --set fresh --baseline test

What it runs, on the frozen **fresh** set (seeds 3001 to 3020, never used for tuning) and, for comparison, on a
baseline set (labelled "not held out", because the rules, the linker and the detector were built while looking
at it):

- field values: precision, recall and F1 per field group and over all fields, for the rules with the DXF, the
  rules without the DXF (drawing not read), the rules plus OCR on each drawing version (no DXF), and the rules
  plus the model (recorded runs; "waiting for Colab recordings" when there are none for the set);
- the symbol detector: precision and recall per drawing version (IoU at least 0.5, the Stage 4 scorer);
- confidence calibration (Stage 6): share right per level;
- cross-checks with the Stage 6 gate: planted conflicts found and false flags;
- an error analysis: the most common wrong and missed field groups, with examples.

Before anything runs on the fresh set its files are checked against ``FROZEN.sha256``; a changed set is refused.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from backend.app import normalise as norm
from backend.app.evaluation import Score, field_group, total
from backend.app.paths import REPO_ROOT

DOC = REPO_ROOT / "docs" / "evaluation.md"
VERSIONS = ("clean", "scanned", "photo")
WAITING = "waiting for Colab recordings"


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


def error_analysis(examples: list[tuple[str, list, list]], top: int = 6, per_group: int = 2) -> str:
    """Counts of wrong and missed values per field group, with a few examples each."""
    lines = []
    for label, wrong, missed in examples:
        lines += [f"**{label}**", ""]
        w = Counter(field_group(e.field) for e, _ in wrong)
        m = Counter(field_group(t.field) for t in missed)
        if not wrong and not missed:
            lines += ["No wrong or missed values.", ""]
            continue
        lines += ["| Field group | Wrong | Missed | Examples |", "|---|---|---|---|"]
        for group, _ in (w + m).most_common(top):
            ex = []
            for e, t in [x for x in wrong if field_group(x[0].field) == group][:per_group]:
                said = f"{t.value} {t.unit or ''}".strip() if t is not None else "nothing on that page"
                ex.append(f"read {e.value} {e.unit or ''} on {e.source.document.value} p{e.source.page} "
                          f"({e.method.value}); key: {said}")
            for t in [x for x in missed if field_group(x.field) == group][:per_group]:
                ex.append(f"missed {t.value} {t.unit or ''} on {t.source.document.value} p{t.source.page}")
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


def extraction(set_name: str, folders: list[Path], versions: tuple[str, ...]) -> tuple[list[str], list, list[str]]:
    """The all-fields rows, the material for the error analysis, and the per-field table."""
    from backend.evaluate import columns, has_recordings, project_values
    from data_generator.project import load_answers

    keys = {f: load_answers(f / "answers.json") for f in folders}

    def run(label: str, **options) -> tuple[Score, dict[str, Score], list, list]:
        grouped: dict[str, Score] = {}
        wrong_all, missed_all = [], []
        from backend.app.evaluation import score

        for f in folders:
            values = project_values(f, set_name=set_name, **options)
            for group, s in score(values, keys[f].values).items():
                grouped.setdefault(group, Score()).add(s)
            wrong, missed = mismatches(values, keys[f].values)
            wrong_all += wrong
            missed_all += missed
        print(f"  {label}: done", file=sys.stderr)
        return total(grouped), grouped, wrong_all, missed_all

    rows = ["| Method | Drawing | P, R, **F1** (TP/FP/FN) |", "|---|---|---|"]
    examples = []
    fields: list[tuple[str, dict[str, Score]]] = []
    t, g, w, m = run("rules with DXF", with_dxf=True, mode="rules")
    rows.append(f"| Rules | DXF | {cell(t)} |")
    examples.append(("Rules, with the DXF", w, m))
    fields.append(("Rules, DXF", g))
    t, g, _, _ = run("rules without DXF", with_dxf=False, mode="rules")
    rows.append(f"| Rules | none (drawing not read) | {cell(t)} |")
    fields.append(("Rules, no drawing", g))
    for v in versions:
        t, g, w, m = run(f"rules + OCR {v}", with_dxf=False, mode="rules", drawing_reading="ocr", drawing_version=v)
        rows.append(f"| Rules + OCR | {v}, no DXF | {cell(t)} |")
        fields.append((f"Rules + OCR, {v}", g))
        if v == "scanned":
            examples.append(("Rules + OCR, scanned drawing, no DXF", w, m))
    v2 = next(c for c in columns() if c.label == "v2")
    recorded = has_recordings(v2, folders, set_name)
    for dxf in (True, False):
        if recorded:
            t, g, _, _ = run(f"combined dxf={dxf}", with_dxf=dxf, mode="combined", recorded_dir=v2.recorded_dir,
                             prompt_version=v2.prompt_version)
            rows.append(f"| Rules + model (v2, strict) | {'DXF' if dxf else 'none'} | {cell(t)} |")
            fields.append((f"Rules + model, {'DXF' if dxf else 'no drawing'}", g))
        else:
            rows.append(f"| Rules + model | {'DXF' if dxf else 'none'} | {WAITING} |")
    return rows, examples, per_field(fields)


def detector(set_name: str, versions: tuple[str, ...], projects: set[str] | None = None) -> list[str]:
    from backend.app.drawing.data import evaluation_drawings
    from backend.app.drawing.symbols import TemplateDetector
    from backend.drawings import score_symbols

    rows = ["| Version | TP | FP | FN | P | R | F1 | acb found | s/sheet |", "|---|---|---|---|---|---|---|---|---|"]
    det = TemplateDetector()
    for v in versions:
        samples = [s for s in evaluation_drawings(set_name) if s.version.value == v
                   and (projects is None or s.project_id in projects)]
        totals, seconds = score_symbols(samples, det)
        tp, fp, fn = (sum(t[k] for t in totals.values()) for k in ("tp", "fp", "fn"))
        acb = totals.get("acb", {"tp": 0, "fn": 0})
        s = Score(tp=tp, fp=fp, fn=fn)
        rows.append(f"| {v} | {tp} | {fp} | {fn} | {_f(s.precision)} | {_f(s.recall)} | {_f(s.f1)} | "
                    f"{acb['tp']} of {acb['tp'] + acb['fn']} | {statistics.mean(seconds):.2f} |")
        print(f"  detector {v}: done", file=sys.stderr)
    return rows


def section(set_name: str, label: str, versions: tuple[str, ...], count: int | None) -> str:
    from backend.calibration import run as calibration
    from backend.crosschecks import run as crosschecks

    root = REPO_ROOT / "data" / "projects" / set_name
    folders = sorted(p.parent for p in root.glob("*/answers.json"))[:count]
    start = time.perf_counter()
    rows, examples, fields = extraction(set_name, folders, versions)
    det = detector(set_name, versions, {f.name for f in folders})
    cal = calibration(set_name, "rules", count).split("\n", 2)[2]
    cal_ocr = calibration(set_name, "rules", count, "ocr", "scanned").split("\n", 2)[2]
    cross = crosschecks(set_name, "rules", count, gate=True).split("\n")[2]
    minutes = (time.perf_counter() - start) / 60
    return "\n".join([
        f"## {label}", "",
        f"{len(folders)} projects ({folders[0].name} to {folders[-1].name}); run took {minutes:.0f} min on the laptop.", "",
        "### Field values (all fields, micro-averaged)", "", *rows, "",
        "### Field values per field group: F1 (TP/FP/FN)", "", *fields, "",
        "### Symbol detector (template; breaker classes, IoU at least 0.5)", "", *det, "",
        "### Confidence calibration (Stage 6), rules with the DXF", "", cal, "",
        "### Confidence calibration, rules + OCR on the scanned drawing (no DXF)", "", cal_ocr, "",
        "### Cross-checks with the Stage 6 gate, rules with the DXF", "", cross, "",
        "### Error analysis", "", error_analysis(examples)])


def main(argv: list[str] | None = None) -> int:
    from data_generator.sets import check_frozen

    parser = argparse.ArgumentParser(prog="python -m backend.evaluation_report", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", default="fresh", choices=["fresh", "test", "reworded"])
    parser.add_argument("--baseline", default=None, choices=["test", "reworded"])
    parser.add_argument("--versions", nargs="+", default=list(VERSIONS), choices=VERSIONS)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--out", type=Path, default=DOC)
    args = parser.parse_args(argv)
    if args.set_name == "fresh":
        problem = check_frozen(REPO_ROOT / "data" / "projects" / "fresh")
        if problem:
            print(f"the fresh set is not as frozen: {problem}", file=sys.stderr)
            return 2
        manifest = (REPO_ROOT / "data" / "projects" / "fresh" / "FROZEN.sha256").read_text(encoding="utf-8")
        set_hash = manifest.strip().splitlines()[-1].split()[-1]
    versions = tuple(args.versions)
    parts = [section(args.set_name, f"Fresh set, not used for tuning (set hash {set_hash[:16]})"
                     if args.set_name == "fresh" else f"{args.set_name} set", versions, args.count)]
    if args.baseline:
        parts.append(section(args.baseline, f"Baseline: {args.baseline} set, not held out", versions, args.count))
    head = ["# Evaluation", "",
            "Written by `python -m backend.evaluation_report`. Every number below was run on the laptop; a row that "
            f"needs model recordings says \"{WAITING}\". Field cells are P, R, **F1** (TP/FP/FN); a value counts when "
            "its field, file, page, value and unit match the answer key (docs/stage-2.md).", ""]
    args.out.write_text("\n".join(head + parts) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
