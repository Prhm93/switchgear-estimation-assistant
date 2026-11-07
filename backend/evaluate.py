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
needs its recording; a recording made for other bytes is refused. Files
without a recording count as not run, and each column says how many files had
one. The output has three result columns, side by side:

- **v1, old parser**: the Stage 3 Part A recordings (``data/recorded-v1/``,
  prompt ``llm-extract-1``) scored as in Part A: a reply that is not valid
  JSON loses its whole page;
- **v1, new parser**: the same recordings, keeping every complete item of a
  reply that was cut off;
- **v2**: the current recordings (``data/recorded/``, prompt
  :data:`backend.app.llm.prompt.PROMPT_VERSION`), with the new parser.

A column with no recording at all reads NOT RUN YET. Above the table, each
column reports its replies: how many were cut off (empty replies counted
among them), how many were otherwise invalid, and Ollama's ``done_reason``
where the recording has it (schema 1.1).

The scoring rules are in :mod:`backend.app.evaluation`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from backend.app.evaluation import Score, score, total
from backend.app.llm.extract import ReplyInfo, ReplyStatus
from backend.app.llm.prompt import PROMPT_VERSION
from backend.app.paths import REPO_ROOT
from backend.app.pipeline import analyse_file
from backend.app.recordings import named_recording, recording_path
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
RECORDED_DIR = DATA / "recorded"  # current recordings (prompt PROMPT_VERSION)
RECORDED_V1_DIR = DATA / "recorded-v1"  # Stage 3 Part A recordings (prompt llm-extract-1), kept for comparison
SETS = {"test": (TEST_COUNT, testset_id), "reworded": (REWORDED_COUNT, reworded_id)}


class Column(BaseModel):
    """One way of scoring recorded runs: which recordings, and how they are replayed."""

    label: str
    recorded_dir: Path
    salvage: bool  # False: the Part A parser (a reply that is not valid JSON loses its whole page)
    own_prompt: bool  # True: replay with the recording's own system prompt (an older prompt version)
    prompt_version: str | None = None  # only recordings made with this prompt version count


def columns(recorded: Path = RECORDED_DIR, recorded_v1: Path = RECORDED_V1_DIR) -> list[Column]:
    """The three result columns: Part A recordings with the old and the new parser, and the current recordings."""
    return [Column(label="v1, old parser", recorded_dir=recorded_v1, salvage=False, own_prompt=True),
            Column(label="v1, new parser", recorded_dir=recorded_v1, salvage=True, own_prompt=True),
            Column(label="v2", recorded_dir=recorded, salvage=True, own_prompt=False, prompt_version=PROMPT_VERSION)]


class Coverage:
    """How many read files had a recording, and how the model's replies ended (llm and combined modes)."""

    def __init__(self) -> None:
        self.files = 0
        self.recorded = 0
        self.replies: list[ReplyInfo] = []

    def reply_counts(self) -> str:
        """For example "266 replies: 41 cut off (3 of them empty), 0 invalid; done_reason: length 41, stop 225"."""
        status = Counter(r.status for r in self.replies)
        cut = status[ReplyStatus.CUT_OFF] + status[ReplyStatus.EMPTY]
        text = (f"{len(self.replies)} replies: {cut} cut off ({status[ReplyStatus.EMPTY]} of them empty), "
                f"{status[ReplyStatus.INVALID]} invalid")
        reasons = Counter(r.done_reason for r in self.replies if r.done_reason is not None)
        if not reasons:
            return text + "; done_reason not recorded"
        text += "; done_reason: " + ", ".join(f"{k} {n}" for k, n in sorted(reasons.items()))
        empty = Counter(r.done_reason or "not recorded" for r in self.replies if r.status == ReplyStatus.EMPTY)
        if empty:
            text += "; done_reason of the empty replies: " + ", ".join(f"{k} {n}" for k, n in sorted(empty.items()))
        return text


def has_recordings(column: Column, folders: list[Path], set_name: str) -> bool:
    """True if at least one read file of these projects has a recording for this column.

    Only the files' names and prompt versions are looked at (nothing is read or
    replayed), so a column without recordings costs nothing.
    """
    for folder in folders:
        for name in READ_FILES:
            path = recording_path(column.recorded_dir, set_name, folder.name, name)
            if not path.exists():
                continue
            if column.prompt_version is None:
                return True
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("prompt_version") == column.prompt_version:
                    return True
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
    return False


def project_values(folder: Path, with_dxf: bool, mode: str = "rules", set_name: str = "test",
                   recorded_dir: Path = RECORDED_DIR, coverage: Coverage | None = None, *, salvage: bool = True,
                   own_prompt: bool = False, prompt_version: str | None = None) -> list[ExtractedValue]:
    values: list[ExtractedValue] = []
    for name in UPLOAD:
        if name.endswith(".dxf") and not with_dxf:
            continue
        path = folder / name
        data = path.read_bytes()
        provider = None
        recording = None
        if mode != "rules" and name in READ_FILES:
            recording = named_recording(recorded_dir, set_name, folder.name, name, data)  # refused on other bytes
            if recording is not None and prompt_version is not None and recording.prompt_version != prompt_version:
                recording = None  # made with another prompt version: not part of this column
            if coverage is not None:
                coverage.files += 1
                coverage.recorded += recording is not None
            provider = make_provider("recorded", recording=recording) if recording else None
        system_prompt = recording.system_prompt if (recording is not None and own_prompt) else None
        analysis = analyse_file(EXTENSIONS[path.suffix.lower()], data, name, provider, system_prompt=system_prompt,
                                salvage=salvage)
        if coverage is not None and analysis.llm is not None:
            coverage.replies += analysis.llm.replies
        if mode == "llm":
            values += analysis.llm.values if analysis.llm else []
        else:
            values += analysis.values  # rules mode, or combined (rules alone where a file has no recording)
    return values


def run(folders: list[Path], with_dxf: bool, mode: str = "rules", set_name: str = "test",
        recorded_dir: Path = RECORDED_DIR, column: Column | None = None) -> tuple[dict[str, Score], float, Coverage]:
    grouped: dict[str, Score] = {}
    coverage = Coverage()
    options: dict = {}
    if column is not None:
        recorded_dir = column.recorded_dir
        options = {"salvage": column.salvage, "own_prompt": column.own_prompt,
                   "prompt_version": column.prompt_version}
    start = time.perf_counter()
    for folder in folders:
        key = load_answers(folder / "answers.json")
        values = project_values(folder, with_dxf, mode, set_name, recorded_dir, coverage, **options)
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


def _cell(s: Score | None) -> str:
    return "n/a (0/0/0)" if s is None else f"{_f(s.f1)} ({s.tp}/{s.fp}/{s.fn})"


def compare_table(results: list[tuple[Column, dict[str, Score] | None]]) -> str:
    """F1 (TP/FP/FN) per field group, one column per way of scoring; NOT RUN YET where nothing was recorded."""
    lines = ["| Field | " + " | ".join(f"{c.label}: F1 (TP/FP/FN)" for c, _ in results) + " |",
             "|---|" + "---|" * len(results)]
    for group in sorted({g for _, grouped in results if grouped for g in grouped}):
        cells = ["NOT RUN YET" if grouped is None else _cell(grouped.get(group)) for _, grouped in results]
        lines.append(f"| `{group}` | " + " | ".join(cells) + " |")
    cells = ["NOT RUN YET" if grouped is None else f"**{_cell(total(grouped))}**" for _, grouped in results]
    lines.append("| **all fields** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.evaluate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", choices=sorted(SETS), default="test")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--root", type=Path, default=None, help="folder of the set (default: data/projects/<set>)")
    parser.add_argument("--mode", choices=["rules", "llm", "combined"], default="rules")
    parser.add_argument("--recorded", type=Path, default=RECORDED_DIR,
                        help="folder of the current recordings (the v2 column)")
    parser.add_argument("--recorded-v1", type=Path, default=RECORDED_V1_DIR,
                        help="folder of the Stage 3 Part A recordings (the two v1 columns)")
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
        what = f"{args.set_name} set, {'with' if with_dxf else 'without'} DXF, {len(folders)} projects"
        if args.mode == "rules":
            grouped, per_project, _ = run(folders, with_dxf, args.mode, args.set_name)
            print(f"## {title[args.mode]}, {what} ({per_project:.2f} s per project)\n")
            print(table(grouped) + "\n")
            continue
        print(f"## {title[args.mode]}, {what}\n")
        results: list[tuple[Column, dict[str, Score] | None]] = []
        for column in columns(args.recorded, args.recorded_v1):
            folder = column.recorded_dir.resolve()
            shown = folder.relative_to(REPO_ROOT).as_posix() if folder.is_relative_to(REPO_ROOT) else folder.as_posix()
            where = shown + (f", prompt {column.prompt_version}" if column.prompt_version else "")
            if not has_recordings(column, folders, args.set_name):  # skipped: no file is read for this column
                print(f"- {column.label}: NOT RUN YET (no recording in {where})")
                results.append((column, None))
                continue
            grouped, _, coverage = run(folders, with_dxf, args.mode, args.set_name, column=column)
            if coverage.recorded == 0:
                print(f"- {column.label}: NOT RUN YET (no recording in {where})")
                results.append((column, None))
                continue
            print(f"- {column.label}: recordings for {coverage.recorded} of {coverage.files} read files ({where}); "
                  f"{coverage.reply_counts()}")
            results.append((column, grouped))
        print("\n" + compare_table(results) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
