"""Accuracy on the synthetic test projects: rules, recorded LLM, or both combined.

Usage (PowerShell, from the repo folder, after
``python -m data_generator build --set test``)::

    .venv\\Scripts\\python.exe -m backend.evaluate            # all 20 test projects, prints Markdown
    .venv\\Scripts\\python.exe -m backend.evaluate --count 2  # the first two only
    .venv\\Scripts\\python.exe -m backend.evaluate --set reworded  # the held-out reworded set, R01 to R20
    .venv\\Scripts\\python.exe -m backend.evaluate --mode llm       # recorded LLM values only (data/recorded/)
    .venv\\Scripts\\python.exe -m backend.evaluate --mode combined  # rules and recorded LLM together

Each project is scored twice, as two upload sets:

- **with DXF**: specification, letter, drawing PDF, the two PNG versions and the DXF;
- **without DXF**: the same files minus the DXF. The drawing PDF has no text
  layer and the PNGs need OCR, so no drawing values are read (Stage 4).

In ``llm`` and ``combined`` mode each read file (specification, letter, DXF)
needs its recording in ``data/recorded/<set>/<project>/``; a recording made for
other bytes is refused. Files without a recording count as not run, and the
heading says how many files had one. With no recording at all the command
prints NOT RUN YET instead of a table.

The scoring rules are in :mod:`backend.app.evaluation`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from backend.app.evaluation import Score, score, total
from backend.app.pipeline import analyse_file
from backend.app.recordings import named_recording
from backend.app.schemas import ExtractedValue
from backend.app.storage import EXTENSIONS
from data_generator.project import load_answers
from data_generator.sets import DATA, REWORDED_COUNT, TEST_COUNT, reworded_id, testset_id
from estimation_assistant.providers import make_provider

UPLOAD = ["specification.pdf", "requirements.docx", "drawing/schematic.pdf", "drawing/schematic_sheet1_scanned.png",
          "drawing/schematic_sheet1_photo.png", "drawing/schematic_sheet2_scanned.png",
          "drawing/schematic_sheet2_photo.png", "drawing/schematic.dxf"]
# The files with a text layer: the only ones the LLM reads (and so the only ones recorded) in Stage 3.
READ_FILES = ["specification.pdf", "requirements.docx", "drawing/schematic.dxf"]
RECORDED_DIR = DATA / "recorded"
SETS = {"test": (TEST_COUNT, testset_id), "reworded": (REWORDED_COUNT, reworded_id)}


class Coverage:
    """How many read files had a recording (llm and combined modes)."""

    def __init__(self) -> None:
        self.files = 0
        self.recorded = 0


def project_values(folder: Path, with_dxf: bool, mode: str = "rules", set_name: str = "test",
                   recorded_dir: Path = RECORDED_DIR, coverage: Coverage | None = None) -> list[ExtractedValue]:
    values: list[ExtractedValue] = []
    for name in UPLOAD:
        if name.endswith(".dxf") and not with_dxf:
            continue
        path = folder / name
        data = path.read_bytes()
        provider = None
        if mode != "rules" and name in READ_FILES:
            recording = named_recording(recorded_dir, set_name, folder.name, name, data)  # refused on other bytes
            if coverage is not None:
                coverage.files += 1
                coverage.recorded += recording is not None
            provider = make_provider("recorded", recording=recording) if recording else None
        analysis = analyse_file(EXTENSIONS[path.suffix.lower()], data, name, provider)
        if mode == "llm":
            values += analysis.llm.values if analysis.llm else []
        else:
            values += analysis.values  # rules mode, or combined (rules alone where a file has no recording)
    return values


def run(folders: list[Path], with_dxf: bool, mode: str = "rules", set_name: str = "test",
        recorded_dir: Path = RECORDED_DIR) -> tuple[dict[str, Score], float, Coverage]:
    grouped: dict[str, Score] = {}
    coverage = Coverage()
    start = time.perf_counter()
    for folder in folders:
        key = load_answers(folder / "answers.json")
        values = project_values(folder, with_dxf, mode, set_name, recorded_dir, coverage)
        for group, s in score(values, key.values).items():
            grouped.setdefault(group, Score()).add(s)
    return grouped, (time.perf_counter() - start) / max(1, len(folders)), coverage


def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def table(grouped: dict[str, Score]) -> str:
    lines = ["| Field | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for group in sorted(grouped):
        s = grouped[group]
        lines.append(f"| `{group}` | {s.tp} | {s.fp} | {s.fn} | {_f(s.precision)} | {_f(s.recall)} | {_f(s.f1)} |")
    t = total(grouped)
    lines.append(f"| **all fields** | {t.tp} | {t.fp} | {t.fn} | {_f(t.precision)} | {_f(t.recall)} | {_f(t.f1)} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.evaluate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", choices=sorted(SETS), default="test")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--root", type=Path, default=None, help="folder of the set (default: data/projects/<set>)")
    parser.add_argument("--mode", choices=["rules", "llm", "combined"], default="rules")
    parser.add_argument("--recorded", type=Path, default=RECORDED_DIR, help="folder of the recordings")
    args = parser.parse_args(argv)
    root = args.root or DATA / "projects" / args.set_name
    full_count, ids = SETS[args.set_name]
    folders = [root / ids(i) for i in range(1, (args.count or full_count) + 1)]
    missing = [f.name for f in folders if not (f / "answers.json").exists()]
    if missing:
        print(f"missing projects {missing}: run python -m data_generator build --set {args.set_name}",
              file=sys.stderr)
        return 2
    title = {"rules": "Rules mode", "llm": "LLM (recorded)", "combined": "Combined rules + LLM (recorded)"}
    for with_dxf in (True, False):
        grouped, per_project, coverage = run(folders, with_dxf, args.mode, args.set_name, args.recorded)
        heading = (f"## {title[args.mode]}, {args.set_name} set, {'with' if with_dxf else 'without'} DXF, "
                   f"{len(folders)} projects ({per_project:.2f} s per project)")
        if args.mode != "rules":
            if coverage.recorded == 0:
                print(f"{heading}\n\nNOT RUN YET: no recording in {args.recorded} for these files.\n")
                continue
            heading += f", recordings for {coverage.recorded} of {coverage.files} read files"
        print(heading + "\n")
        print(table(grouped) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
