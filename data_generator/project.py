"""Build one enquiry (or one training drawing) and its answer key.

Project folder layout::

    <project_id>/
      specification.pdf
      requirements.docx
      drawing/schematic.dxf              generator source, not an engineer input
      drawing/schematic.pdf              clean vector PDF, sheet 1 and sheet 2
      drawing/schematic_sheet1_scanned.png
      drawing/schematic_sheet1_photo.png
      drawing/schematic_sheet2_scanned.png
      drawing/schematic_sheet2_photo.png
      answers.json

Training drawings have sheet 1 only, as PNG: ``clean.png``, ``scanned.png``,
``photo.png`` and ``answers.json``.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from data_generator import degrade
from data_generator import geometry as g
from data_generator.catalogue import Part, build_catalogue
from data_generator.design import random_design
from data_generator.estimate import estimate_lines
from data_generator.planted import EXPECTED, Plan, apply_plan
from data_generator.requirements_doc import build_letter
from data_generator.schematic import SHEET_H, DrawingLayout, build_schematic
from data_generator.schemas import (AnswerKey, DocumentInfo, DocumentKind, DrawingVersion, DrawingVersionKind,
                                    PlantedProblem, Region, SourceRef, SymbolBox, TruthValue)
from data_generator.spec_pdf import build_spec
from data_generator.views import DocView

CLEAN_DPI = 150.0
V = DrawingVersionKind

# Where the stamp and the note go, in mm from the top-left of each sheet (empty paper).
MARK_PLACES = {1: ((300.0, 340.0, 16.0, 24.0), (130.0, 170.0, 22.0, 30.0)),
               2: ((30.0, 80.0, 215.0, 225.0), (150.0, 200.0, 228.0, 236.0))}


def seed_for(seed: int, part: str) -> int:
    """A sub-seed for one part of a project, so parts do not share random streams."""
    return int(hashlib.sha256(f"{seed}:{part}".encode()).hexdigest()[:12], 16)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_answers(key: AnswerKey, path: Path) -> None:
    """Write ``answers.json`` with sorted keys and LF endings, so it is byte-stable."""
    text = json.dumps(key.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def load_answers(path: Path) -> AnswerKey:
    return AnswerKey.model_validate_json(path.read_bytes())


def render_pdf_pages(pdf_path: Path, dpi: float) -> list[Image.Image]:
    """Render every page of a PDF to a greyscale image with pypdfium2."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [pdf[i].render(scale=dpi / 72.0, grayscale=True).to_pil().convert("L") for i in range(len(pdf))]
    finally:
        pdf.close()


def _place(rng: np.random.Generator, spot: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, x1, y0, y1 = spot
    return float(rng.uniform(x0, x1)), float(rng.uniform(y0, y1))


def _drawing_versions(layout: DrawingLayout, sheet: int, clean: Image.Image, seed: int, date: str,
                      files: dict[V, str], page: int | None, out_root: Path, dpi: float,
                      photo_scale: float = 0.8) -> tuple[list[DrawingVersion], dict[V, np.ndarray]]:
    """Make the scanned and photo images for one sheet; return all three versions with boxes."""
    hs: dict[V, np.ndarray] = {V.CLEAN: np.eye(3)}
    images: dict[V, Image.Image] = {V.CLEAN: clean}
    for kind, fn in ((V.SCANNED, degrade.scanned), (V.PHOTO, degrade.photo)):
        rng = np.random.default_rng(seed_for(seed, f"{kind.value}{sheet}"))
        stamp, note = (_place(rng, s) for s in MARK_PLACES[sheet])
        kw = {"out_scale": photo_scale} if kind == V.PHOTO else {}
        res = fn(clean, rng, dpi, date, stamp_at_mm=stamp, note_at_mm=note, **kw)
        hs[kind], images[kind] = res.h, res.image
        target = out_root / files[kind]
        target.parent.mkdir(parents=True, exist_ok=True)
        res.image.save(target, format="PNG", optimize=False, compress_level=6)
    versions = []
    for kind in (V.CLEAN, V.SCANNED, V.PHOTO):
        w, h = images[kind].size
        boxes = []
        for i, s in enumerate(m for m in layout.symbols if m.sheet == sheet):
            box = g.mm_box_to_px(s.box, SHEET_H, dpi)
            box = g.round_box(g.clip_box(g.transform_box(hs[kind], box), w, h))
            boxes.append(SymbolBox(id=f"S{i + 1:02d}", cls=s.cls, way=s.way, bbox=box))
        versions.append(DrawingVersion(
            sheet=sheet, version=kind, file=files[kind], page=page if kind == V.CLEAN else None,
            width_px=w, height_px=h, dpi=dpi if kind == V.CLEAN else None, symbols=boxes,
            transform_from_clean=None if kind == V.CLEAN else [[round(float(v), 10) for v in row]
                                                               for row in hs[kind]]))
    return versions, hs


def _regions(box_mm, sheet: int, hs: dict[V, np.ndarray], sizes: dict[V, tuple[int, int]], dpi: float) -> list[Region]:
    px = g.mm_box_to_px(box_mm, SHEET_H, dpi)
    out = []
    for kind in (V.CLEAN, V.SCANNED, V.PHOTO):
        w, h = sizes[kind]
        out.append(Region(version=kind, sheet=sheet,
                          bbox=g.round_box(g.clip_box(g.transform_box(hs[kind], px), w, h))))
    return out


def build_project(project_id: str, seed: int, purpose: str, out_dir: Path, plan: Plan,
                  n_ways: int | None = None, parts: list[Part] | None = None, dpi: float = CLEAN_DPI) -> AnswerKey:
    """Write every file of one enquiry into ``out_dir`` and return its answer key."""
    parts = parts if parts is not None else build_catalogue()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    design = random_design(seed_for(seed, "design"), project_id, n_ways)
    views = apply_plan(design, plan, random.Random(seed_for(seed, "planted")))

    spec_file, letter_file = "specification.pdf", "requirements.docx"
    dxf_file, pdf_file = "drawing/schematic.dxf", "drawing/schematic.pdf"
    spec_marks, spec_pages, injection = build_spec(views.specification, seed_for(seed, "spec"), out_dir / spec_file)
    letter_marks = build_letter(views.requirements, seed_for(seed, "letter"), out_dir / letter_file)
    schem = build_schematic(views.schematic, seed_for(seed, "schematic"), out_dir / dxf_file, out_dir / pdf_file)

    drawings: list[DrawingVersion] = []
    hs_by_sheet: dict[int, dict[V, np.ndarray]] = {}
    sizes_by_sheet: dict[int, dict[V, tuple[int, int]]] = {}
    for sheet, clean in enumerate(render_pdf_pages(out_dir / pdf_file, dpi), start=1):
        files = {V.CLEAN: pdf_file, V.SCANNED: f"drawing/schematic_sheet{sheet}_scanned.png",
                 V.PHOTO: f"drawing/schematic_sheet{sheet}_photo.png"}
        versions, hs = _drawing_versions(schem.layout, sheet, clean, seed, design.issue_date, files, sheet,
                                         out_dir, dpi)
        drawings += versions
        hs_by_sheet[sheet] = hs
        sizes_by_sheet[sheet] = {v.version: (v.width_px, v.height_px) for v in versions}

    values: list[TruthValue] = []
    for m in spec_marks:
        if m.field == "injection":
            continue
        values.append(TruthValue(field=m.field, value=m.value, unit=m.unit, source=SourceRef(
            document=DocumentKind.SPECIFICATION, file=spec_file, page=m.page, source_text=m.text)))
    for m in schem.layout.values:
        values.append(TruthValue(field=m.field, value=m.value, unit=m.unit, source=SourceRef(
            document=DocumentKind.SCHEMATIC, file=pdf_file, page=m.sheet, source_text=m.text,
            regions=_regions(m.box, m.sheet, hs_by_sheet[m.sheet], sizes_by_sheet[m.sheet], dpi))))
    for m in letter_marks:
        values.append(TruthValue(field=m.field, value=m.value, unit=m.unit, source=SourceRef(
            document=DocumentKind.REQUIREMENTS, file=letter_file, page=m.page, source_text=m.text)))

    problems: list[PlantedProblem] = []
    for i, p in enumerate(views.problems, start=1):
        if p.kind.value == "prompt_injection":
            assert injection is not None
            sources = [SourceRef(document=DocumentKind.SPECIFICATION, file=spec_file, page=injection[0],
                                 source_text=injection[1])]
        else:
            sources = [v.source for v in values if v.field == p.field and v.source.document in p.documents]
        problems.append(PlantedProblem(id=f"{project_id}-P{i}", kind=p.kind, field=p.field,
                                       description=p.description, expected=EXPECTED[p.kind], sources=sources))

    documents = [
        DocumentInfo(kind=DocumentKind.SPECIFICATION, file=spec_file, pages=spec_pages,
                     sha256=sha256_file(out_dir / spec_file)),
        DocumentInfo(kind=DocumentKind.SCHEMATIC, file=pdf_file, pages=2, sha256=sha256_file(out_dir / pdf_file)),
        DocumentInfo(kind=DocumentKind.REQUIREMENTS, file=letter_file, pages=1,
                     sha256=sha256_file(out_dir / letter_file)),
    ]
    key = AnswerKey(project_id=project_id, origin="synthetic", purpose=purpose, seed=seed, documents=documents,
                    drawings=drawings, values=values, planted=problems,
                    estimate=estimate_lines(design, parts, problems))
    write_answers(key, out_dir / "answers.json")
    return key


def build_training_drawing(drawing_id: str, seed: int, out_dir: Path, dpi: float = 100.0) -> AnswerKey:
    """One training drawing: sheet 1 only, clean, scanned and photo PNGs, boxes for every symbol."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    rng = random.Random(seed_for(seed, "design"))
    design = random_design(seed_for(seed, "design"), drawing_id, n_ways=rng.randint(2, 15))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        schem = build_schematic(DocView(design=design), seed_for(seed, "schematic"), t / "s.dxf", t / "s.pdf",
                                sheets=(1,))
        clean = render_pdf_pages(t / "s.pdf", dpi)[0]
    clean.save(out_dir / "clean.png", format="PNG", compress_level=6)
    files = {V.CLEAN: "clean.png", V.SCANNED: "scanned.png", V.PHOTO: "photo.png"}
    versions, _ = _drawing_versions(schem.layout, 1, clean, seed, design.issue_date, files, None, out_dir, dpi,
                                    photo_scale=0.9)
    versions[0] = versions[0].model_copy(update={"page": None})
    key = AnswerKey(project_id=drawing_id, origin="synthetic", purpose="training", seed=seed, drawings=versions)
    write_answers(key, out_dir / "answers.json")
    return key
