"""Where recorded model runs live and how a file finds its own.

Layout: ``data/recorded/<set>/<project>/<file>.json``, for example
``data/recorded/test/T03/specification.pdf.json`` or
``data/recorded/reworded/R08/drawing__schematic.dxf.json`` ("/" in a file path
becomes "__"). Each file is a :class:`estimation_assistant.providers.Recording`.

The app finds a recording by the SHA-256 of the uploaded bytes, never by the
file name (every project has a "specification.pdf"). Loading a recording
always checks the hash again, and a recording asked for by name for a file
with other bytes is refused (:class:`RecordingMismatch`).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import backend.app.llm  # noqa: F401  (makes the AI engine importable)
from estimation_assistant.providers import Recording, RecordingMismatch, load_recording, sha256_bytes

log = logging.getLogger(__name__)


def recording_path(recorded_dir: Path, set_name: str, project: str, file: str) -> Path:
    return recorded_dir / set_name / project / (file.replace("/", "__") + ".json")


def index(recorded_dir: Path) -> dict[str, Path]:
    """Map input SHA-256 to recording file, for every recording under ``recorded_dir``."""
    found: dict[str, Path] = {}
    if not recorded_dir.is_dir():
        return found
    for path in sorted(recorded_dir.rglob("*.json")):
        try:
            sha = json.loads(path.read_text(encoding="utf-8")).get("input_sha256")
        except (OSError, json.JSONDecodeError, AttributeError):
            log.warning("skipping unreadable recording %s", path)
            continue
        if isinstance(sha, str):
            found[sha] = path
    return found


def find_recording(recorded_dir: Path, data: bytes) -> Recording | None:
    """The recording made for exactly these bytes, or None."""
    path = index(recorded_dir).get(sha256_bytes(data))
    return load_recording(path, data) if path else None


def named_recording(recorded_dir: Path, set_name: str, project: str, file: str, data: bytes) -> Recording | None:
    """The recording of one file of a data set; None if there is none, refused if its hash differs."""
    path = recording_path(recorded_dir, set_name, project, file)
    if not path.exists():
        return None
    return load_recording(path, data)  # raises RecordingMismatch on other bytes


__all__ = ["RecordingMismatch", "find_recording", "index", "named_recording", "recording_path"]
