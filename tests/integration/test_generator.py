"""The enquiry generator end to end: determinism, answer keys, boxes, planted problems.

Every check reads the generated files back with independent tools (pypdfium2
for PDF text and rendering, python-docx, ezdxf) instead of trusting the
generator's own records.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import numpy as np
import pypdfium2 as pdfium
import pytest
from docx import Document
from PIL import Image

from data_generator import geometry as g
from data_generator.catalogue import build_catalogue
from data_generator.planted import TEST_PLAN
from data_generator.project import render_pdf_pages, sha256_file
from data_generator.schemas import AnswerKey, DocumentKind, DrawingVersionKind, ProblemKind

V = DrawingVersionKind
INK = 128  # clean renders are black on white


def _norm(s: str) -> str:
    return " ".join(s.split())


def spec_pages(folder: Path) -> list[str]:
    pdf = pdfium.PdfDocument(str(folder / "specification.pdf"))
    try:
        return [_norm(pdf[i].get_textpage().get_text_range()) for i in range(len(pdf))]
    finally:
        pdf.close()


def dxf_texts(folder: Path) -> dict[int, list[str]]:
    doc = ezdxf.readfile(folder / "drawing" / "schematic.dxf")
    out: dict[int, list[str]] = {1: [], 2: []}
    for e in doc.modelspace().query("TEXT"):
        out[int(e.dxf.layer[-1])].append(e.dxf.text)
    return out


def letter_paragraphs(folder: Path) -> list[str]:
    return [p.text for p in Document(str(folder / "requirements.docx")).paragraphs]


# --- determinism --------------------------------------------------------------------------------


def _files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_same_seed_gives_byte_identical_project_files(built, built_again):
    for pid, second in built_again.items():
        a, b = _files(built[pid][0]), _files(second)
        assert a.keys() == b.keys()
        different = [name for name in a if a[name] != b[name]]
        assert not different, f"{pid}: files differ between two builds: {different}"


def test_same_seed_gives_byte_identical_training_files(training_pairs):
    for first, second in training_pairs:
        assert _files(first) == _files(second)


def test_project_has_every_expected_file(built):
    folder, _ = built["T01"]
    names = set(_files(folder))
    assert names == {
        "answers.json", "specification.pdf", "requirements.docx", "drawing/schematic.dxf", "drawing/schematic.pdf",
        "drawing/schematic_sheet1_scanned.png", "drawing/schematic_sheet1_photo.png",
        "drawing/schematic_sheet2_scanned.png", "drawing/schematic_sheet2_photo.png",
    }


# --- answer keys --------------------------------------------------------------------------------


def test_every_answer_key_validates_and_hashes_match(built, training_pairs):
    for pid, (folder, key) in built.items():
        assert AnswerKey.model_validate_json((folder / "answers.json").read_bytes()) == key
        assert key.purpose == "test" and key.origin == "synthetic"
        for doc in key.documents:
            assert sha256_file(folder / doc.file) == doc.sha256, (pid, doc.file)
    for first, _ in training_pairs:
        key = AnswerKey.model_validate_json((first / "answers.json").read_bytes())
        assert key.purpose == "training" and key.values == [] and len(key.drawings) == 3


def test_specification_has_6_to_14_pages(built):
    for pid, (folder, key) in built.items():
        n = len(spec_pages(folder))
        assert 6 <= n <= 14, pid
        assert next(d for d in key.documents if d.kind == DocumentKind.SPECIFICATION).pages == n


def test_specification_source_text_is_on_the_stated_page(built):
    for pid, (folder, key) in built.items():
        pages = spec_pages(folder)
        for v in key.values:
            if v.source.document == DocumentKind.SPECIFICATION:
                assert _norm(v.source.source_text) in pages[v.source.page - 1], (pid, v.field, v.source)


def test_letter_source_text_is_a_sentence_of_the_letter(built):
    for pid, (folder, key) in built.items():
        text = "\n".join(letter_paragraphs(folder))
        for v in key.values:
            if v.source.document == DocumentKind.REQUIREMENTS:
                assert v.source.source_text in text, (pid, v.field)


def test_drawing_source_text_is_a_text_of_the_stated_sheet(built):
    for pid, (folder, key) in built.items():
        texts = dxf_texts(folder)
        for v in key.values:
            if v.source.document == DocumentKind.SCHEMATIC and v.source.source_text is not None:
                assert v.source.source_text in texts[v.source.page], (pid, v.field, v.source.source_text)
                assert {r.version for r in v.source.regions} == set(V), (pid, v.field)


def test_every_way_has_its_values_in_the_spec(built):
    for pid, (_, key) in built.items():
        count = next(v.value for v in key.values_for("ways.count")
                     if v.source.document == DocumentKind.SPECIFICATION)
        for i in range(1, count + 1):
            assert key.values_for(f"way.Q{i}.device"), (pid, i)


def test_estimate_uses_catalogue_codes_only(built):
    codes = {p.code for p in build_catalogue()}
    for pid, (_, key) in built.items():
        assert key.estimate, pid
        assert {line.code for line in key.estimate} <= codes, pid


# --- boxes --------------------------------------------------------------------------------------


def _clean_page(folder: Path, key: AnswerKey, sheet: int) -> np.ndarray:
    dpi = key.drawing(sheet, V.CLEAN).dpi
    return np.asarray(render_pdf_pages(folder / "drawing" / "schematic.pdf", dpi)[sheet - 1])


def _int_box(b) -> tuple[int, int, int, int]:
    return int(np.floor(b[0])), int(np.floor(b[1])), int(np.ceil(b[2])), int(np.ceil(b[3]))


def test_clean_boxes_are_tight_around_their_symbol(built):
    """Ink touches all four edges of every clean box (within 2 px), so boxes are neither loose nor clipped."""
    for pid in ("T01", "T02", "T12"):
        folder, key = built[pid]
        page = _clean_page(folder, key, 1)
        for s in key.drawing(1, V.CLEAN).symbols:
            x0, y0, x1, y1 = _int_box(s.bbox)
            ink = page[y0:y1, x0:x1] < INK
            assert ink.any(), (pid, s.id, s.cls)
            for name, strip in (("left", ink[:, :3]), ("right", ink[:, -3:]), ("top", ink[:3, :]),
                                ("bottom", ink[-3:, :])):
                assert strip.any(), (pid, s.id, s.cls, name, "edge has no ink")


def _warp_ink(page: np.ndarray, box, h: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """The clean ink inside ``box`` only, warped with ``h`` exactly as the image was."""
    mask = np.zeros_like(page, dtype=np.uint8)
    x0, y0, x1, y1 = _int_box(box)
    mask[y0:y1, x0:x1] = np.where(page[y0:y1, x0:x1] < INK, 255, 0)
    out = Image.fromarray(mask).transform(size, Image.Transform.PERSPECTIVE, g.pil_perspective_coeffs(h),
                                          resample=Image.Resampling.BILINEAR)
    return np.asarray(out) > 64


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


@pytest.mark.parametrize("version", [V.SCANNED, V.PHOTO])
def test_degraded_boxes_match_the_transformed_symbol(built, version):
    for pid in ("T01", "T02", "T12"):
        folder, key = built[pid]
        page = _clean_page(folder, key, 1)
        clean = key.drawing(1, V.CLEAN)
        dv = key.drawing(1, version)
        h = np.array(dv.transform_from_clean)
        img = np.asarray(Image.open(folder / dv.file).convert("L"), dtype=np.float32)
        for cs, s in zip(clean.symbols, dv.symbols, strict=True):
            assert (cs.id, cs.cls, cs.way) == (s.id, s.cls, s.way)
            # Inside the image (the schema checks this too).
            assert 0 <= s.bbox[0] < s.bbox[2] <= dv.width_px and 0 <= s.bbox[1] < s.bbox[3] <= dv.height_px
            warped = _warp_ink(page, cs.bbox, h, (dv.width_px, dv.height_px))
            ys, xs = np.nonzero(warped)
            ink_box = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]
            # The warped symbol lies inside its box and fills it.
            assert ink_box[0] >= s.bbox[0] - 2 and ink_box[1] >= s.bbox[1] - 2, (pid, s.id)
            assert ink_box[2] <= s.bbox[2] + 2 and ink_box[3] <= s.bbox[3] + 2, (pid, s.id)
            assert g.iou(ink_box, s.bbox) > 0.75, (pid, s.id, s.cls, ink_box, s.bbox)
            # And the degraded image really has ink where the warped symbol is: inside the box, the
            # symbol's pixels are clearly darker than the paper around them (light is uneven, so the
            # comparison is local).
            x0, y0, x1, y1 = _int_box(s.bbox)
            inside = np.zeros_like(warped)
            inside[y0:y1, x0:x1] = True
            near_paper = inside & ~_dilate(warped, 2)
            assert img[warped].mean() < img[near_paper].mean() - 15, (pid, s.id, "no ink at the box")


def test_value_regions_are_inside_their_image(built):
    for pid, (_, key) in built.items():
        for v in key.values:
            for r in v.source.regions:
                d = key.drawing(r.sheet, r.version)
                assert 0 <= r.bbox[0] < r.bbox[2] <= d.width_px and 0 <= r.bbox[1] < r.bbox[3] <= d.height_px


def test_every_symbol_class_appears(built):
    found = {s.cls.value for _, key in built.values() for s in key.drawing(1, V.CLEAN).symbols}
    assert found == {"busbar", "acb", "mccb", "mcb", "switch_disconnector", "ct", "earth", "meter"}


# --- planted problems ---------------------------------------------------------------------------


def _doc_values(key: AnswerKey, field: str, doc: DocumentKind) -> list:
    return [v for v in key.values_for(field) if v.source.document == doc]


def test_planted_problems_match_the_plan(built):
    for pid, (_, key) in built.items():
        assert [p.kind for p in key.planted] == [k for k, _ in TEST_PLAN[int(pid[1:])]], pid


def test_every_planted_problem_is_present_in_the_documents(built):
    S, D, R = DocumentKind.SPECIFICATION, DocumentKind.SCHEMATIC, DocumentKind.REQUIREMENTS
    for pid, (folder, key) in built.items():
        for p in key.planted:
            if p.kind == ProblemKind.RATING_CONFLICT:
                spec, drw = _doc_values(key, p.field, S), _doc_values(key, p.field, D)
                assert spec and drw and spec[0].value != drw[0].value, (pid, p.id)
                assert {s.document for s in p.sources} == {S, D}
            elif p.kind == ProblemKind.QUANTITY_CONFLICT:
                spec, drw = _doc_values(key, "ways.count", S), _doc_values(key, "ways.count", D)
                assert spec[0].value != drw[0].value, (pid, p.id)
                # The drawing really shows that many breaker symbols.
                ways_drawn = {s.way for s in key.drawing(1, V.CLEAN).symbols if s.way}
                assert len(ways_drawn) == drw[0].value
            elif p.kind == ProblemKind.MISSING_VALUE:
                vals = key.values_for(p.field)
                if p.field.endswith(".rating") and p.field.startswith("way."):  # "TBC" in the specification
                    spec = _doc_values(key, p.field, S)
                    assert spec[0].value is None and spec[0].source.source_text == "TBC", (pid, p.id)
                    assert _doc_values(key, p.field, D)[0].value is not None
                else:
                    assert vals == [], (pid, p.id, "a missing value is stated somewhere")
                    assert any(p.id in line.blocked_by for line in key.estimate), (pid, p.id)
            elif p.kind == ProblemKind.AMBIGUOUS_UNIT:
                vals = key.values_for(p.field)
                assert len(vals) == 1 and vals[0].source.document == S and vals[0].unit is None, (pid, p.id)
                assert any(p.id in line.blocked_by for line in key.estimate)
            elif p.kind == ProblemKind.PROMPT_INJECTION:
                src = p.sources[0]
                assert _norm(src.source_text) in spec_pages(folder)[src.page - 1], (pid, p.id)
            if p.kind != ProblemKind.PROMPT_INJECTION:
                assert any(p.id in line.blocked_by for line in key.estimate), (pid, p.id, "blocks no line")


def test_control_project_has_no_problems_and_no_blocked_lines(built):
    _, key = built["T20"]
    assert key.planted == []
    assert all(line.blocked_by == [] for line in key.estimate)
    for field in ("system.voltage", "incomer.rating", "ways.count"):
        assert len({v.value for v in key.values_for(field)}) == 1, field


def test_identical_across_processes_with_different_hash_seeds(tmp_path):
    """Two separate processes with different PYTHONHASHSEED values write the same bytes.

    Catches anything that depends on set or dict-of-str ordering (it once did: ezdxf's CLASS
    section), which a build twice in one process cannot see.
    """
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    code = ("import sys; from pathlib import Path; from data_generator.project import build_project; "
            "from data_generator.planted import TEST_PLAN; "
            "build_project('T13', 1013, 'test', Path(sys.argv[1]), TEST_PLAN[13], dpi=60.0)")
    outs = []
    for seed in ("1", "987"):
        out = tmp_path / f"hash{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": os.pathsep.join([str(repo / "ai_engine"),
                                                                                    str(repo)])}
        subprocess.run([sys.executable, "-c", code, str(out)], check=True, cwd=repo, env=env)
        outs.append(_files(out))
    assert outs[0].keys() == outs[1].keys()
    assert [n for n in outs[0] if outs[0][n] != outs[1][n]] == []
