"""Confidence calibration (Stage 6): does each confidence level match how often values are right?

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m backend.calibration --set test --mode rules
    .venv\\Scripts\\python.exe -m backend.calibration --set reworded --mode combined

Each project is read as the app reads an upload with the DXF (:func:`backend.evaluate.project_values`), every
value gets its Stage 6 level (:func:`backend.app.confidence.assess`, over all values of the project), and the
scorer's own rule marks it right or wrong (:func:`backend.app.evaluation.correct_flags`: same field, file,
page, value and unit; one to one). A well calibrated level is right more often than the level below it.
Nothing is tuned here: the levels and their rules were fixed before this was run.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

from backend.app.confidence import assess
from backend.app.crosscheck import seen_from_values
from backend.app.evaluation import correct_flags
from backend.app.paths import REPO_ROOT

LEVELS = ["high", "medium", "low", "conflict"]


def tally(pairs: Iterable[tuple[str, bool]]) -> dict[str, list[int]]:
    """``{level: [right, all]}``."""
    out: dict[str, list[int]] = {}
    for level, ok in pairs:
        c = out.setdefault(level, [0, 0])
        c[0] += ok
        c[1] += 1
    return out


def calibration_table(counts: dict[str, list[int]], label: str = "Level") -> str:
    lines = [f"| {label} | Values | Right | Share right |", "|---|---|---|---|"]
    for level in [x for x in LEVELS if x in counts] + sorted(set(counts) - set(LEVELS)):
        right, n = counts[level]
        lines.append(f"| {level} | {n} | {right} | {right / n:.3f} |")
    return "\n".join(lines)


def project_pairs(values: list, truth: list) -> list[tuple[str, str, bool]]:
    """(level, method, right) for every value with a value (TBC values are not scored for calibration)."""
    seen = seen_from_values(values)
    levels = assess(seen)
    flags = correct_flags(values, truth)
    out = []
    for ref, (v, ok) in enumerate(zip(values, flags, strict=True)):
        if v.value is None or ref not in levels:
            continue
        out.append((levels[ref].level, v.method.value, ok))
    return out


def run(set_name: str, mode: str, count: int | None = None, drawing_reading: str = "off",
        drawing_version: str = "clean") -> str:
    from backend.evaluate import project_values
    from data_generator.project import load_answers

    root = REPO_ROOT / "data" / "projects" / set_name
    folders = sorted(p.parent for p in root.glob("*/answers.json"))[:count]
    if not folders:
        return f"no projects in {root}: build the set with python -m data_generator build --set {set_name}"
    pairs: list[tuple[str, str, bool]] = []
    for folder in folders:
        key = load_answers(folder / "answers.json")
        values = project_values(folder, with_dxf=drawing_reading == "off", mode=mode, set_name=set_name,
                                drawing_reading=drawing_reading, drawing_version=drawing_version)
        pairs += project_pairs(values, key.values)
    by_level = tally((lv, ok) for lv, _, ok in pairs)
    by_method = tally((f"{m}, {lv}", ok) for lv, m, ok in pairs)
    where = "with the DXF" if drawing_reading == "off" else f"{drawing_reading} on the {drawing_version} drawing"
    return "\n".join([f"## Calibration, {set_name} set, {mode} mode, {where} ({len(folders)} projects)", "",
                      calibration_table(by_level), "", calibration_table(by_method, "Method, level")])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.calibration", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", choices=["test", "reworded", "fresh"], default="test")
    parser.add_argument("--mode", choices=["rules", "combined"], default="rules")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--drawing-reading", choices=["off", "ocr"], default="off",
                        help="off: read the DXF; ocr: no DXF, OCR on one drawing version")
    parser.add_argument("--drawing-version", choices=["clean", "scanned", "photo"], default="clean")
    args = parser.parse_args(argv)
    print(run(args.set_name, args.mode, args.count, args.drawing_reading, args.drawing_version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
