"""Stage 4 Part C: the symbol detector interface and the rule-based template detector.

Templates come from training drawings only; the test set is never used to build or tune them.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from backend.app.drawing import symbols as sym
from backend.app.drawing.data import DataMixError, evaluation_drawings
from backend.app.drawing.reading import DetectedSymbol, TextBox
from backend.app.schemas import Confidence, Method
from data_generator.schemas import DrawingVersionKind, SymbolClass


def cross(size: int = 24) -> np.ndarray:
    """A small test shape (ink = 1): a cross with a bar, unlike anything else in the picture."""
    t = np.zeros((size, size // 2), dtype=np.float32)
    t[:, size // 4] = 1
    t[size // 3, :] = 1
    t[2 * size // 3, 2:-2] = 1
    return t


def picture_with(shapes: list[tuple[np.ndarray, int, int]], size=(400, 300)) -> Image.Image:
    """A white picture (answer-key scale) with each shape drawn in black at twice its size."""
    canvas = np.zeros((size[1] // 2, size[0] // 2), dtype=np.float32)
    for shape, x, y in shapes:
        canvas[y:y + shape.shape[0], x:x + shape.shape[1]] = np.maximum(canvas[y:y + shape.shape[0],
                                                                               x:x + shape.shape[1]], shape)
    img = Image.fromarray(((1 - canvas) * 255).astype(np.uint8)).resize(size, Image.Resampling.NEAREST)
    return img


def test_ncc_scores_the_shape_where_it_is_and_nothing_on_blank_paper() -> None:
    t = cross()
    pic = np.zeros((100, 120), dtype=np.float32)
    pic[30:54, 40:52] = t
    score = sym.ncc_map(pic, t)
    y, x = np.unravel_index(np.argmax(score), score.shape)
    assert (y, x) == (30, 40) and score[y, x] == pytest.approx(1.0, abs=1e-3)
    assert np.all(sym.ncc_map(np.zeros((60, 60), np.float32), t) == 0)


def test_the_template_detector_finds_each_shape_once_at_its_size() -> None:
    t = cross()
    templates = {"mccb": t, "mccb__heights": np.array([20, 30], np.float32)}
    small = sym._resize(t, 20, 10)
    image = picture_with([(t, 20, 20), (small, 100, 60)])
    found = sym.TemplateDetector(templates, threshold=0.8, classes=(SymbolClass.MCCB,)).detect(image)
    assert len(found) == 2 and {f.cls for f in found} == {SymbolClass.MCCB}
    boxes = sorted(f.bbox for f in found)
    assert boxes[0][0] == pytest.approx(40, abs=4) and boxes[0][1] == pytest.approx(40, abs=4)
    assert boxes[1][0] == pytest.approx(200, abs=4) and boxes[1][3] - boxes[1][1] == pytest.approx(40, abs=6)
    assert sym.TemplateDetector(templates, threshold=0.8, classes=(SymbolClass.MCCB,)).detect(
        picture_with([])) == []


def test_detectors_are_chosen_by_name_so_a_trained_one_can_be_added() -> None:
    assert sym.make_detector("off") is None
    assert isinstance(sym.make_detector("template"), sym.TemplateDetector)
    with pytest.raises(ValueError, match="unknown symbol detector"):
        sym.make_detector("yolo")

    class Trained:
        name = "trained"

        def detect(self, image):
            return [DetectedSymbol(cls=SymbolClass.ACB, bbox=[1, 1, 5, 9], score=0.9)]

    sym.DETECTORS["trained"] = Trained
    try:
        assert sym.make_detector("trained").detect(None)[0].cls == SymbolClass.ACB
    finally:
        del sym.DETECTORS["trained"]


def test_the_committed_templates_cover_the_four_breaker_classes() -> None:
    templates = sym.load_templates()
    for cls in sym.BREAKER_CLASSES:
        assert templates[cls.value].shape[0] == sym.TEMPLATE_HEIGHT
        lo, hi = templates[f"{cls.value}__heights"]
        assert 0 < lo <= hi


def test_templates_are_never_built_from_test_drawings() -> None:
    from backend.drawings import build_symbol_templates

    with pytest.raises(DataMixError):
        build_symbol_templates(evaluation_drawings("showcase"))


# --- ways and values -------------------------------------------------------------------------------------

def label(text: str, x: float) -> TextBox:
    return TextBox(text=text, bbox=[x - 10, 500, x + 10, 520])


def found(cls: SymbolClass, x: float) -> DetectedSymbol:
    return DetectedSymbol(cls=cls, bbox=[x - 15, 300, x + 15, 400], score=0.7)


def test_symbols_link_to_the_nearest_way_label_or_to_none() -> None:
    labels = [label("Q1", 100), label("Q2", 200), label("Q3", 300)]
    linked = sym.link_to_ways([found(SymbolClass.MCCB, 105), found(SymbolClass.ACB, 250),
                               found(SymbolClass.MCB, 297)], labels)
    assert [s.way for s in linked] == ["Q1", None, "Q3"]  # halfway between two labels is not clear enough
    assert sym.link_to_ways([found(SymbolClass.MCCB, 105)], [])[0].way is None


def test_detector_values_are_low_confidence_devices_for_ways_ocr_left_empty() -> None:
    linked = [s.model_copy(update={"way": w}) for s, w in (
        (found(SymbolClass.MCCB, 100), "Q1"), (found(SymbolClass.SWITCH_DISCONNECTOR, 200), "Q2"),
        (found(SymbolClass.MCCB, 300), "Q3"), (found(SymbolClass.MCB, 310), "Q3"))]
    out = sym.detector_values(linked, file="schematic.pdf", version=DrawingVersionKind.CLEAN, sheet=1,
                              filled={"way.Q1.device"})
    assert [(v.field, v.value) for v in out] == [("way.Q2.device", "switch_disconnector")]  # Q3 has two symbols
    v = out[0]
    assert v.method == Method.DETECTOR and v.confidence == Confidence.LOW and v.unit is None
    assert v.source.regions[0].bbox == [185.0, 300.0, 215.0, 400.0] and v.source.page == 1


def test_symbol_detector_setting_names_a_known_detector() -> None:
    from backend.app.config import Settings

    assert Settings().symbol_detector in ("off", *sym.DETECTORS)
    assert Settings(symbol_detector="off").symbol_detector == "off"
