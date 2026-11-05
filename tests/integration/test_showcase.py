"""The committed showcase project: valid, and rebuilt from its seed with the same content.

In the environment it was built in (``build-info.json``: same Python zlib and
Pillow zlib), the rebuild must be byte-identical. Elsewhere, deflate output
differs between zlib builds (zlib-ng on Windows Python 3.14, zlib on Linux),
so the rebuild must have identical *content*: the same DXF bytes, the same PDF
text and rendered pixels, the same DOCX entries, the same PNG pixels, and the
same answer key apart from the document hashes.
"""

from __future__ import annotations

import io
import json
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image, features

from data_generator import sets
from data_generator.diagnose import clean_render_hashes, pixel_diff
from data_generator.project import build_project, load_answers, sha256_file
from data_generator.schemas import ProblemKind

SHOWCASE = sets.DATA / "projects" / "showcase"
PNGS = [f"drawing/schematic_sheet{s}_{v}.png" for s in (1, 2) for v in ("scanned", "photo")]
DEFLATED = ["specification.pdf", "drawing/schematic.pdf", "requirements.docx", *PNGS]

pytestmark = pytest.mark.skipif(not (SHOWCASE / "answers.json").exists(), reason="showcase not generated")


def same_zlib_as_build() -> bool:
    info = json.loads((SHOWCASE / "build-info.json").read_text(encoding="utf-8"))
    return info["python_zlib"] == zlib.ZLIB_VERSION and info["pillow_zlib"] == str(features.version("zlib"))


def test_showcase_key_validates_and_matches_its_files():
    key = load_answers(SHOWCASE / "answers.json")
    assert key.purpose == "showcase" and key.seed == sets.SHOWCASE_SEED
    for doc in key.documents:
        assert sha256_file(SHOWCASE / doc.file) == doc.sha256
    assert [p.kind for p in key.planted] == [ProblemKind.RATING_CONFLICT]
    assert {v.source.document.value for v in key.values_for("ways.count")} == {
        "specification", "schematic", "requirements"}


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory) -> Path:
    job = sets.showcase_job()  # same seed, plan and size as the committed one; written elsewhere
    out = tmp_path_factory.mktemp("rebuilt") / "showcase"
    build_project(job.item_id, job.seed, job.purpose, out, list(job.plan), n_ways=job.n_ways)
    return out


def test_dxf_is_byte_identical_everywhere(rebuilt):
    name = "drawing/schematic.dxf"
    assert (rebuilt / name).read_bytes() == (SHOWCASE / name).read_bytes()


@pytest.mark.parametrize("name", ["answers.json", *DEFLATED])
def test_byte_identical_in_the_build_environment(rebuilt, name):
    if not same_zlib_as_build():
        pytest.skip("different zlib build from build-info.json; content is compared instead")
    assert (rebuilt / name).read_bytes() == (SHOWCASE / name).read_bytes(), name


def _pdf_content(path: Path) -> tuple[list[str], list[np.ndarray]]:
    pdf = pdfium.PdfDocument(str(path))
    try:
        texts = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
        pixels = [np.asarray(pdf[i].render(scale=60 / 72, grayscale=True).to_pil()) for i in range(len(pdf))]
    finally:
        pdf.close()
    return texts, pixels


@pytest.mark.parametrize("name", ["specification.pdf", "drawing/schematic.pdf"])
def test_pdf_content_is_identical(rebuilt, name):
    (ta, pa), (tb, pb) = _pdf_content(rebuilt / name), _pdf_content(SHOWCASE / name)
    assert ta == tb
    assert len(pa) == len(pb) and all(np.array_equal(a, b) for a, b in zip(pa, pb))


def test_docx_entries_are_identical(rebuilt):
    za = zipfile.ZipFile(io.BytesIO((rebuilt / "requirements.docx").read_bytes()))
    zb = zipfile.ZipFile(io.BytesIO((SHOWCASE / "requirements.docx").read_bytes()))
    assert za.namelist() == zb.namelist()
    assert all(za.read(n) == zb.read(n) for n in za.namelist())
    assert [i.date_time for i in za.infolist()] == [i.date_time for i in zb.infolist()]


def test_clean_render_matches_the_build_machine_exactly(rebuilt):
    """The committed vector PDF, rendered here at 150 dpi, has exactly the pixels it had on the build machine."""
    info = json.loads((SHOWCASE / "build-info.json").read_text(encoding="utf-8"))
    assert clean_render_hashes(SHOWCASE) == info["clean_render_sha256"]
    assert clean_render_hashes(rebuilt) == info["clean_render_sha256"]


@pytest.mark.parametrize("name", PNGS)
def test_png_pixels_are_identical(rebuilt, name):
    a = np.asarray(Image.open(rebuilt / name))
    b = np.asarray(Image.open(SHOWCASE / name))
    assert a.shape == b.shape
    d = pixel_diff(name, a, b)
    assert d.differing == 0, (f"{name}: {d.differing} of {d.values} values differ ({d.share:.6%}), "
                              f"max difference {d.max_abs}, histogram {d.histogram}")


def test_answer_key_is_identical_apart_from_hashes(rebuilt):
    def strip(path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in data["documents"]:
            d.pop("sha256")
        return data

    assert strip(rebuilt / "answers.json") == strip(SHOWCASE / "answers.json")
