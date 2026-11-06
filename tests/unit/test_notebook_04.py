"""Notebook 04 (Colab LLM extraction): numbered cells, no rebuild of the data sets, not run yet."""

from __future__ import annotations

import json
import re

from backend.app.paths import REPO_ROOT

NOTEBOOK = REPO_ROOT / "notebooks" / "04-colab-llm-extraction.ipynb"


def cells() -> list[dict]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def test_every_cell_starts_with_its_number_and_title() -> None:
    for i, cell in enumerate(cells(), 1):
        assert re.match(rf"^# Cell {i}: \S", "".join(cell["source"])), i


def test_uses_the_laptop_zip_and_never_rebuilds() -> None:
    code = "\n".join("".join(c["source"]) for c in cells() if c["cell_type"] == "code")
    assert "laptop-files.zip" in code and "backend.record run" in code
    assert "data_generator build" not in code and "data_generator" not in code


def test_has_no_saved_outputs() -> None:
    assert all(not c.get("outputs") for c in cells() if c["cell_type"] == "code")
