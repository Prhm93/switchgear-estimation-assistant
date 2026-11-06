"""The rule extractor is frozen for Stage 3.

The rules were written after reading the generator templates, so they are
scored on a held-out reworded set as well. To keep that score honest, the
rule files were frozen (data/rules/rules-freeze.json) before the reworded set
was generated, and must not change after seeing it.
"""

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FREEZE = REPO / "data" / "rules" / "rules-freeze.json"


def test_rule_files_match_the_frozen_hashes() -> None:
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))["files"]
    for name, digest in frozen.items():
        data = (REPO / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, f"{name} changed after the rules were frozen"
