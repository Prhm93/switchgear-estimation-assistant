"""``backend.record run --resume``: files already recorded are skipped, everything else is recorded.

No model is called: a scripted FAKE provider stands in for Ollama, and every
recording it leaves is labelled fake.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.recordings import recording_path
from backend.record import pack, record_file, run
from data_generator import sets
from estimation_assistant.providers import load_recording
from tests.fakes import ScriptedProvider

SHOWCASE = sets.DATA / "projects" / "showcase"
PROJECT = "SHOWCASE"  # the project id pack() gives the showcase


def test_resume_skips_recorded_files_and_records_the_rest(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "laptop-files.zip"
    pack(zip_path, ["showcase"])
    out = tmp_path / "recorded"

    # Already done before the "interruption": the specification, with the current prompt version.
    spec = (SHOWCASE / "specification.pdf").read_bytes()
    done, *_ = record_file("showcase", PROJECT, "specification.pdf", spec, ScriptedProvider({}), out, fake=True)
    before = done.read_bytes()
    # Recorded with an older prompt version: must be recorded again.
    letter = (SHOWCASE / "requirements.docx").read_bytes()
    old, *_ = record_file("showcase", PROJECT, "requirements.docx", letter, ScriptedProvider({}), out, fake=True)
    old.write_text(old.read_text(encoding="utf-8").replace('"prompt_version": "llm-extract-2"',
                                                           '"prompt_version": "llm-extract-1"'), encoding="utf-8")

    fake = ScriptedProvider({})
    assert run(zip_path, "ollama", out, "unused", "unused", ["showcase"], resume=True, provider=fake) == 0
    printed = capsys.readouterr().out

    assert "SKIPPED showcase/SHOWCASE/specification.pdf" in printed
    assert done.read_bytes() == before  # untouched
    assert "SKIPPED showcase/SHOWCASE/requirements.docx" not in printed
    assert load_recording(old, letter).prompt_version == "llm-extract-2"  # recorded again
    dxf = SHOWCASE / "drawing" / "schematic.dxf"
    assert recording_path(out, "showcase", PROJECT, "drawing/schematic.dxf").exists()
    assert load_recording(recording_path(out, "showcase", PROJECT, "drawing/schematic.dxf"), dxf.read_bytes())
    # Only the two files that were not done went to the model.
    asked = {prompt.split("\n", 1)[0] for _, prompt in fake.prompts}
    assert asked == {"Document type: requirements", "Document type: schematic"}


def test_without_resume_every_file_is_recorded_again(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "laptop-files.zip"
    pack(zip_path, ["showcase"])
    out = tmp_path / "recorded"
    spec = (SHOWCASE / "specification.pdf").read_bytes()
    record_file("showcase", PROJECT, "specification.pdf", spec, ScriptedProvider({}), out, fake=True)
    assert run(zip_path, "ollama", out, "unused", "unused", ["showcase"], provider=ScriptedProvider({})) == 0
    assert "SKIPPED" not in capsys.readouterr().out
