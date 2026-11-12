"""Make vision-model recordings of drawing pictures (Stage 4 Part B). Run on Colab, not on the laptop.

Usage (Colab, after the test sets are unzipped from the laptop-built files)::

    python -m backend.record_vision --set test --version scanned
    python -m backend.record_vision --set reworded --version photo --count 2

Each sheet of each drawing version of the set is sent to the vision model on
the Ollama server (``--url``, ``--model``; ``gemma4:e2b`` by default) and its
answer is saved as one JSON file under ``data/recorded-vision/<set>/<project>/``
(git-ignored, never committed). A file that already has a recording is skipped,
so a stopped run can be started again. Each recording keeps the model name,
the date, the prompt, the SHA-256 of the file's bytes and the sheet, so the app
replays it only for exactly that file (:class:`RecordedVisionClient`).

The files must be the laptop-built ones (from the uploaded zip): rebuilding the
sets on Colab gives other bytes, and their recordings would never match.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.drawing.data import DATA, DrawingSample, evaluation_drawings
from backend.app.drawing.vision import (
    VISION_PROMPT,
    VISION_PROMPT_VERSION,
    OllamaVisionClient,
    VisionClient,
    VisionRecording,
    VisionUnavailable,
)
from backend.app.pipeline import _sheet_png
from backend.app.storage import FileType

OUT = DATA / "recorded-vision"


def recording_path(out: Path, set_name: str, sample: DrawingSample) -> Path:
    stem = sample.path.stem
    return out / set_name / sample.project_id / f"{stem}-sheet{sample.sheet}.json"


def record(samples: list[DrawingSample], client: VisionClient, out: Path, set_name: str, *, model: str,
           model_version: str | None = None, fake: bool = False) -> tuple[int, int, list[str]]:
    """Record every sheet not recorded yet. Returns (made, skipped, failures)."""
    made, skipped, failed = 0, 0, []
    for s in samples:
        path = recording_path(out, set_name, s)
        if path.exists():
            skipped += 1
            continue
        data = s.path.read_bytes()
        file_type = FileType.PDF if s.path.suffix.lower() == ".pdf" else FileType.PNG
        start = time.perf_counter()
        try:
            output = client.read(file_sha256=hashlib.sha256(data).hexdigest(), sheet=s.sheet,
                                 image=_sheet_png(file_type, data, s.page or 1))  # an image has one sheet
        except VisionUnavailable as error:
            failed.append(f"{s.project_id} {s.path.name} sheet {s.sheet}: {error}")
            continue
        rec = VisionRecording(model=model, model_version=model_version, date=datetime.now(UTC).date().isoformat(),
                              prompt_version=VISION_PROMPT_VERSION, prompt=VISION_PROMPT,
                              input_name=f"{s.project_id}/{s.path.relative_to(s.path.parents[1]).as_posix()}",
                              input_sha256=hashlib.sha256(data).hexdigest(), sheet=s.sheet, output=output,
                              seconds=round(time.perf_counter() - start, 2), fake=fake)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rec.model_dump_json(indent=1), encoding="utf-8")
        made += 1
    return made, skipped, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.record_vision", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", choices=["test", "reworded", "showcase"], default="test")
    parser.add_argument("--version", choices=["clean", "scanned", "photo"], default="scanned")
    parser.add_argument("--count", type=int, default=None, help="first N projects only")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:e2b")
    args = parser.parse_args(argv)
    samples = [s for s in evaluation_drawings(args.set_name) if s.version.value == args.version]
    if args.count:
        keep = sorted({s.project_id for s in samples})[:args.count]
        samples = [s for s in samples if s.project_id in keep]
    if not samples:
        print(f"no drawings for {args.set_name}: unzip the laptop-built set first", file=sys.stderr)
        return 2
    made, skipped, failed = record(samples, OllamaVisionClient(args.model, args.url), args.out, args.set_name,
                                   model=args.model)
    print(f"{made} recorded, {skipped} already there, {len(failed)} failed")
    for line in failed:
        print("  " + line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
