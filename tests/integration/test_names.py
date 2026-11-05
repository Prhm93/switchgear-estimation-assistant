"""No real company names in generated files.

Two checks:

1. Allowlist (always runs): every company-like name ("... Ltd", "... Trust",
   ...) in the generated text must be one of the invented names in
   ``data_generator/names.py``.
2. Denylist (local only): real manufacturer names are kept out of the repo,
   in the git-ignored file ``data/external/denylist.txt`` (one name per line,
   ``#`` for comments). When the file is missing the check is skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import ezdxf
import pypdfium2 as pdfium
import pytest
from docx import Document

from data_generator import degrade
from data_generator.names import COMPANY_ALLOWLIST

REPO = Path(__file__).resolve().parents[2]
DENYLIST = REPO / "data" / "external" / "denylist.txt"
SUFFIXES = r"(?:Ltd|Limited|plc|PLC|LLP|LLC|Inc|GmbH|AG|S\.A\.|SA|SpA|BV|Trust|Group|Corporation|Corp|Company)"
COMPANY = re.compile(rf"\b((?:[A-Z][A-Za-z&'\-]*\s+){{1,6}}){SUFFIXES}\b")


def project_texts(folder: Path) -> list[str]:
    """All human-readable text of one generated project or training drawing."""
    out = []
    spec = folder / "specification.pdf"
    if spec.exists():
        pdf = pdfium.PdfDocument(str(spec))
        out += [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
        pdf.close()
    letter = folder / "requirements.docx"
    if letter.exists():
        doc = Document(str(letter))
        out += [p.text for p in doc.paragraphs]
        cp = doc.core_properties
        out += [cp.author or "", cp.title or "", cp.last_modified_by or ""]
    dxf = folder / "drawing" / "schematic.dxf"
    if dxf.exists():
        out += [e.dxf.text for e in ezdxf.readfile(dxf).modelspace().query("TEXT")]
    out.append((folder / "answers.json").read_text(encoding="utf-8"))
    return out


def fixed_texts() -> list[str]:
    """Committed data and the text painted onto scanned and photo images."""
    texts = [(REPO / "data" / "catalogue" / "catalogue.csv").read_text(encoding="utf-8"),
             (REPO / "data" / "projects" / "test" / "PLANTED.md").read_text(encoding="utf-8")]
    texts += [" ".join(pair) for pair in degrade.STAMP_LINES] + degrade.NOTES
    showcase = REPO / "data" / "projects" / "showcase"
    if (showcase / "answers.json").exists():
        texts += project_texts(showcase)
    return texts


@pytest.fixture(scope="module")
def corpus(built, training_pairs) -> list[str]:
    texts = fixed_texts()
    for folder, _ in built.values():
        texts += project_texts(folder)
    for first, _ in training_pairs:
        texts += project_texts(first)
    return texts


def company_names(text: str) -> set[str]:
    return {m.group(0) for m in COMPANY.finditer(" ".join(text.split()))}


def test_the_pattern_finds_company_names():
    found = company_names("Client: Ashvale Example Estates Ltd. Panels by Made Up Switchgear GmbH")
    assert found == {"Ashvale Example Estates Ltd", "Made Up Switchgear GmbH"}
    assert company_names("MCCB 250A 4P 36kA, cable 4C 95 mm2 SWA") == set()


def test_every_company_name_is_an_invented_one(corpus):
    unknown = set()
    for text in corpus:
        for name in company_names(text):
            if not any(name.endswith(allowed) for allowed in COMPANY_ALLOWLIST):
                unknown.add(name)
    assert not unknown, f"company-like names not in the allowlist: {sorted(unknown)}"


def test_every_invented_name_is_clearly_fictional():
    assert all("Example" in n or "Sample" in n for n in COMPANY_ALLOWLIST)


def test_no_denylisted_real_name_appears(corpus):
    if not DENYLIST.exists():
        pytest.skip("data/external/denylist.txt not found. Create it locally (it is git-ignored) with one "
                    "real manufacturer name per line to run this check.")
    names = [line.strip() for line in DENYLIST.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert names, "denylist.txt is empty"
    hits = set()
    for text in corpus:
        for name in names:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE):
                hits.add(name)
    # Report how many names matched, not which, so the names stay out of test logs too.
    assert not hits, f"{len(hits)} denylisted name(s) found in generated files"
