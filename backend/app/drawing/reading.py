"""DrawingReading: what one method read from one drawing image.

The same model holds the output of every drawing method (Stage 4 OCR, a vision
model, a symbol detector), so each can be scored the same way and shown on the
drawing. Boxes are ``[x0, y0, x1, y1]`` in pixels of the image that was read,
which for the answer key's versions are the answer key's own coordinates.

Counts (ways, symbols per class) are always computed here from the listed
items; a method never supplies a count of its own.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas import Method
from data_generator.schemas import BBox, DrawingVersionKind, SymbolClass, check_bbox

WAY_PATTERN = r"^Q[1-9][0-9]?$"  # Q1 to Q99, the answer key's way names
DRAWING_METHODS = {Method.OCR, Method.VISION, Method.DETECTOR}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextBox(_Strict):
    """One line of text read from the drawing, with its box."""

    text: str = Field(min_length=1)
    bbox: BBox
    confidence: float | None = Field(default=None, ge=0, le=100)  # the reader's own score, 0 to 100

    @field_validator("bbox")
    @classmethod
    def _has_size(cls, box: list[float]) -> list[float]:
        return check_bbox(box)


class DetectedSymbol(_Strict):
    """One symbol found on the drawing."""

    cls: SymbolClass
    bbox: BBox
    score: float = Field(ge=0, le=1)
    way: str | None = Field(default=None, pattern=WAY_PATTERN)

    @field_validator("bbox")
    @classmethod
    def _has_size(cls, box: list[float]) -> list[float]:
        return check_bbox(box)


class WayReading(_Strict):
    """What was read for one outgoing way. Each value keeps the boxes of the text it came from."""

    way: str = Field(pattern=WAY_PATTERN)
    description: str | None = None
    device: str | None = None
    rating_a: float | None = Field(default=None, gt=0)
    poles: int | None = Field(default=None, ge=1, le=4)
    breaking_ka: float | None = Field(default=None, gt=0)
    cable: str | None = None
    sources: list[BBox] = Field(default_factory=list)


class DrawingReading(_Strict):
    """The reading of one drawing image (one version of one sheet) by one method."""

    file: str
    version: DrawingVersionKind
    sheet: int = Field(ge=1)
    method: Method
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    texts: list[TextBox] = Field(default_factory=list)
    labels: list[TextBox] = Field(default_factory=list)  # the way labels read on the diagram (Q1, Q2, ...)
    symbols: list[DetectedSymbol] = Field(default_factory=list)
    ways: list[WayReading] = Field(default_factory=list)
    seconds: float | None = Field(default=None, ge=0)

    @field_validator("method")
    @classmethod
    def _drawing_method(cls, method: Method) -> Method:
        if method not in DRAWING_METHODS:
            raise ValueError(f"a drawing reading comes from ocr, vision or detector, not {method}")
        return method

    @model_validator(mode="after")
    def _boxes_inside(self) -> DrawingReading:
        boxes = [t.bbox for t in self.texts + self.labels] + [s.bbox for s in self.symbols] + [b for w in self.ways
                                                                                  for b in w.sources]
        for x0, y0, x1, y1 in boxes:
            if x0 < 0 or y0 < 0 or x1 > self.width_px or y1 > self.height_px:
                raise ValueError(f"box {[x0, y0, x1, y1]} is outside the {self.width_px}x{self.height_px} image")
        return self

    @property
    def way_count(self) -> int:
        """Distinct ways read, counted here."""
        return len({w.way for w in self.ways})

    def symbol_counts(self) -> dict[SymbolClass, int]:
        """Symbols per class, counted here."""
        return dict(Counter(s.cls for s in self.symbols))
