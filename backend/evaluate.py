"""Rules-mode accuracy on the synthetic test projects.

Usage (PowerShell, from the repo folder, after
``python -m data_generator build --set test``)::

    .venv\\Scripts\\python.exe -m backend.evaluate            # all 20 test projects, prints Markdown
    .venv\\Scripts\\python.exe -m backend.evaluate --count 2  # the first two only

Each project is scored twice, as two upload sets:

- **with DXF**: specification, letter, drawing PDF, the two PNG versions and the DXF;
- **without DXF**: the same files minus the DXF. The drawing PDF has no text
  layer and the PNGs need OCR, so no drawing values are read (Stage 4).

The scoring rules are in :mod:`backend.app.evaluation`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from backend.app.evaluation import Score, score, total
from backend.app.pipeline import analyse_file
from backend.app.schemas import ExtractedValue
from backend.app.storage import EXTENSIONS
from data_generator.project import load_answers
from data_generator.sets import DATA, TEST_COUNT, testset_id

UPLOAD = ["specification.pdf", "requirements.docx", "drawing/schematic.pdf", "drawing/schematic_sheet1_scanned.png",
          "drawing/schematic_sheet1_photo.png", "drawing/schematic_sheet2_scanned.png",
          "drawing/schematic_sheet2_photo.png", "drawing/schematic.dxf"]


def project_values(folder: Path, with_dxf: bool) -> list[ExtractedValue]:
    values: list[ExtractedValue] = []
    for name in UPLOAD:
        if name.endswith(".dxf") and not with_dxf:
            continue
        path = folder / name
        values += analyse_file(EXTENSIONS[path.suffix.lower()], path.read_bytes(), name).values
    return values


def run(folders: list[Path], with_dxf: bool) -> tuple[dict[str, Score], float]:
    grouped: dict[str, Score] = {}
    start = time.perf_counter()
    for folder in folders:
        key = load_answers(folder / "answers.json")
        for group, s in score(project_values(folder, with_dxf), key.values).items():
            grouped.setdefault(group, Score()).add(s)
    return grouped, (time.perf_counter() - start) / max(1, len(folders))


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
    parser.add_argument("--count", type=int, default=TEST_COUNT)
    parser.add_argument("--root", type=Path, default=DATA / "projects" / "test")
    args = parser.parse_args(argv)
    folders = [args.root / testset_id(i) for i in range(1, args.count + 1)]
    missing = [f.name for f in folders if not (f / "answers.json").exists()]
    if missing:
        print(f"missing test projects {missing}: run python -m data_generator build --set test", file=sys.stderr)
        return 2
    for with_dxf in (True, False):
        grouped, per_project = run(folders, with_dxf)
        print(f"## Rules mode, {'with' if with_dxf else 'without'} DXF, {len(folders)} projects "
              f"({per_project:.2f} s per project)\n")
        print(table(grouped) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
