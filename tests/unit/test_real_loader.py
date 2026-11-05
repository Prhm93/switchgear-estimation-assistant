"""Real drawings use the synthetic answer-key format; the loader checks keys against their files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from data_generator.project import render_pdf_pages, sha256_file  # noqa: E402
from data_generator.real import AnswerKeyError, discover, load_project  # noqa: E402
from data_generator.schemas import AnswerKey  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "docs" / "real-drawings.md"


def _tiny_pdf(path: Path) -> None:
    fig = plt.figure(figsize=(4, 3))
    fig.add_axes((0, 0, 1, 1)).plot([0.1, 0.9], [0.5, 0.5], "k-")
    fig.savefig(path, format="pdf", metadata={"CreationDate": None, "Producer": None})
    plt.close(fig)


def _real_project(folder: Path) -> dict:
    folder.mkdir(parents=True)
    _tiny_pdf(folder / "sld.pdf")
    w, h = render_pdf_pages(folder / "sld.pdf", 100)[0].size
    key = {
        "project_id": "R01", "origin": "real", "purpose": "real",
        "documents": [{"kind": "schematic", "file": "sld.pdf", "pages": 1, "sha256": sha256_file(folder / "sld.pdf")}],
        "drawings": [{"sheet": 1, "version": "clean", "file": "sld.pdf", "page": 1, "dpi": 100, "width_px": w,
                      "height_px": h, "symbols": [{"id": "S01", "cls": "busbar", "bbox": [40, 140, 360, 160]}]}],
        "values": [{"field": "busbar.rating", "value": 630, "unit": "A", "source": {
            "document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "BUSBAR 630A",
            "regions": [{"version": "clean", "sheet": 1, "bbox": [200, 120, 300, 138]}]}}],
    }
    (folder / "answers.json").write_text(json.dumps(key), encoding="utf-8")
    return key


def test_loader_accepts_a_matching_key(tmp_path):
    _real_project(tmp_path / "R01")
    project = load_project(tmp_path / "R01")
    assert project.key.origin == "real" and project.key.drawings[0].symbols[0].cls == "busbar"
    assert [p.key.project_id for p in discover(tmp_path)] == ["R01"]


def test_loader_rejects_a_changed_file(tmp_path):
    _real_project(tmp_path / "R01")
    with (tmp_path / "R01" / "sld.pdf").open("ab") as f:
        f.write(b"\n% edited")
    with pytest.raises(AnswerKeyError, match="SHA-256"):
        load_project(tmp_path / "R01")


def test_loader_rejects_a_wrong_image_size(tmp_path):
    key = _real_project(tmp_path / "R01")
    key["drawings"][0]["width_px"] += 50
    (tmp_path / "R01" / "answers.json").write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(AnswerKeyError, match="px"):
        load_project(tmp_path / "R01")


def test_loader_rejects_a_synthetic_key(tmp_path):
    key = _real_project(tmp_path / "R01")
    key["origin"], key["purpose"] = "synthetic", "test"
    (tmp_path / "R01" / "answers.json").write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(AnswerKeyError, match="origin"):
        load_project(tmp_path / "R01")


def test_discover_on_a_missing_folder_is_empty(tmp_path):
    assert discover(tmp_path / "nothing-here") == []


def test_worked_example_in_the_guide_validates():
    blocks = re.findall(r"```json\n(.*?)```", GUIDE.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert blocks, "docs/real-drawings.md has no json example"
    key = AnswerKey.model_validate_json(blocks[0])
    assert key.origin == "real" and key.values and key.drawings[0].symbols
