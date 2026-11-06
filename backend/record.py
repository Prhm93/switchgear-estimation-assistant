"""Pack laptop-built files, and record model runs on them (for recorded mode).

Recordings must match the SHA-256 of the files the laptop built: Windows and
Linux builds of the same seed differ in their compressed bytes, so the GPU
machine never rebuilds a set. It gets a zip of the laptop's files instead.

Step 1, on the laptop (PowerShell)::

    .venv\\Scripts\\python.exe -m backend.record pack --out laptop-files.zip

  writes the read files (specification, letter, DXF) of the showcase, the 20
  test projects and the 20 reworded projects, plus ``manifest.json`` with the
  SHA-256 of every file.

Step 2, on Colab (notebooks/04-colab-llm-extraction.ipynb)::

    python -m backend.record run --zip laptop-files.zip --mode ollama --out data/recorded

  checks every file against the manifest (a file with other bytes is refused),
  runs LLM extraction through Ollama and saves one recording per file in
  ``data/recorded/<set>/<project>/<file>.json``.

Step 3, back on the laptop: unzip the recordings into ``data/recorded/`` and
run ``python -m backend.evaluate --mode llm`` and ``--mode combined``.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

from backend.app.paths import REPO_ROOT
from backend.app.llm.prompt import PROMPT_TEMPLATE, PROMPT_VERSION, SYSTEM_PROMPT
from backend.app.pipeline import analyse_file
from backend.app.recordings import recording_path
from backend.app.storage import EXTENSIONS
from estimation_assistant.providers import (ModelProvider, RecordingMismatch, RecordingProvider, make_provider,
                                            save_recording, sha256_bytes)

DATA = REPO_ROOT / "data"
READ_FILES = ["specification.pdf", "requirements.docx", "drawing/schematic.dxf"]
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # zip entry time, so the same files give the same zip


def set_folders(sets: list[str]) -> list[tuple[str, str, Path]]:
    """(set, project id, folder) for the chosen sets."""
    # The generator is needed only to pack on the laptop; "run" on Colab needs the app requirements only.
    from data_generator.sets import REWORDED_COUNT, TEST_COUNT, reworded_id, testset_id

    out = []
    if "showcase" in sets:
        out.append(("showcase", "SHOWCASE", DATA / "projects" / "showcase"))
    if "test" in sets:
        out += [("test", testset_id(i), DATA / "projects" / "test" / testset_id(i)) for i in range(1, TEST_COUNT + 1)]
    if "reworded" in sets:
        out += [("reworded", reworded_id(i), DATA / "projects" / "reworded" / reworded_id(i))
                for i in range(1, REWORDED_COUNT + 1)]
    return out


def pack(out: Path, sets: list[str]) -> dict:
    """Zip the read files of the sets with a manifest of their SHA-256."""
    from data_generator.sets import build_info

    entries = []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for set_name, project, folder in set_folders(sets):
            for file in READ_FILES:
                path = folder / file
                if not path.exists():
                    raise FileNotFoundError(f"{path} is missing: build the set with python -m data_generator "
                                            f"build --set {set_name}")
                data = path.read_bytes()
                name = f"{set_name}/{project}/{file}"
                z.writestr(zipfile.ZipInfo(name, FIXED_TIME), data)
                entries.append({"set": set_name, "project": project, "file": file, "sha256": sha256_bytes(data),
                                "bytes": len(data)})
        manifest = {"built_on": build_info(), "files": entries}
        z.writestr(zipfile.ZipInfo("manifest.json", FIXED_TIME), json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def record_file(set_name: str, project: str, file: str, data: bytes, provider: ModelProvider,
                out_dir: Path, fake: bool = False) -> tuple[Path, int, int, float]:
    """Run LLM extraction on one file and save its recording. Returns path, kept, rejected, seconds.

    ``fake`` labels a recording made by a test with a scripted provider, never by a model.
    """
    recorder = RecordingProvider(provider)
    start = time.perf_counter()
    analysis = analyse_file(EXTENSIONS[Path(file).suffix.lower()], data, file, recorder)
    seconds = time.perf_counter() - start
    if analysis.llm is None:
        raise RuntimeError(analysis.llm_error or f"{file} has no readable text")
    recording = recorder.recording(input_name=f"{project}/{file}", data=data, prompt_version=PROMPT_VERSION,
                                   system_prompt=SYSTEM_PROMPT, prompt_template=PROMPT_TEMPLATE)
    recording.fake = fake
    path = recording_path(out_dir, set_name, project, file)
    save_recording(recording, path)
    return path, len(analysis.llm.values), len(analysis.llm.rejected), seconds


def run(zip_path: Path, mode: str, out_dir: Path, url: str, model: str, sets: list[str]) -> int:
    provider = make_provider(mode, url=url, model=model)
    if provider is None:
        print("rules mode calls no model; nothing to record", file=sys.stderr)
        return 2
    failures = 0
    with zipfile.ZipFile(zip_path) as z:
        manifest = json.loads(z.read("manifest.json"))
        for entry in manifest["files"]:
            if entry["set"] not in sets:
                continue
            name = f"{entry['set']}/{entry['project']}/{entry['file']}"
            data = io.BytesIO(z.read(name)).getvalue()
            if sha256_bytes(data) != entry["sha256"]:
                print(f"REFUSED {name}: SHA-256 differs from the manifest", file=sys.stderr)
                failures += 1
                continue
            try:
                path, kept, rejected, seconds = record_file(entry["set"], entry["project"], entry["file"], data,
                                                            provider, out_dir)
            except (RuntimeError, RecordingMismatch) as error:
                print(f"FAILED {name}: {error}", file=sys.stderr)
                failures += 1
                continue
            print(f"{name}: {kept} kept, {rejected} rejected, {seconds:.1f} s -> {path}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.record", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack", help="zip the laptop-built files with their SHA-256")
    p.add_argument("--out", type=Path, default=Path("laptop-files.zip"))
    p.add_argument("--sets", nargs="+", default=["showcase", "test", "reworded"])
    r = sub.add_parser("run", help="record model runs on the files of a packed zip")
    r.add_argument("--zip", type=Path, required=True)
    r.add_argument("--mode", choices=["ollama", "ollama-local"], default="ollama")
    r.add_argument("--out", type=Path, default=DATA / "recorded")
    r.add_argument("--url", default="http://127.0.0.1:11434")
    r.add_argument("--model", default="gemma4:e2b")
    r.add_argument("--sets", nargs="+", default=["showcase", "test", "reworded"])
    args = parser.parse_args(argv)
    if args.command == "pack":
        manifest = pack(args.out, args.sets)
        print(f"{len(manifest['files'])} files -> {args.out}")
        return 0
    return run(args.zip, args.mode, args.out, args.url, args.model, args.sets)


if __name__ == "__main__":
    sys.exit(main())
