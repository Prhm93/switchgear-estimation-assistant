"""Answer-key schema shared by synthetic and real enquiries.

An answer key holds ground truth only: what each document really says and
where it says it. It has no method, confidence or review status; those belong
to *extracted* values, which Stage 2 builds on the same base model
(:class:`SourcedValue`), so an extracted value can be scored against a truth
value field by field.

Coordinates
-----------
Boxes are in pixels of the image they belong to, origin at the top-left
corner, x to the right and y down, as ``[x0, y0, x1, y1]`` with
``x0 < x1`` and ``y0 < y1``. For the clean vector PDF, pixels are those of the
page rendered at :attr:`DrawingVersion.dpi`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    """Base for every answer-key model: unknown keys are an error."""

    model_config = ConfigDict(extra="forbid")


class DocumentKind(StrEnum):
    """The three documents of a customer enquiry."""

    SPECIFICATION = "specification"
    SCHEMATIC = "schematic"
    REQUIREMENTS = "requirements"


class DrawingVersionKind(StrEnum):
    """How a drawing reached us."""

    CLEAN = "clean"  # the vector PDF as exported from CAD
    SCANNED = "scanned"  # printed and scanned
    PHOTO = "photo"  # photographed with a phone


class SymbolClass(StrEnum):
    """Symbol classes drawn on a single-line diagram (IEC 60617 style)."""

    BUSBAR = "busbar"
    ACB = "acb"
    MCCB = "mccb"
    MCB = "mcb"
    SWITCH_DISCONNECTOR = "switch_disconnector"
    CT = "ct"
    EARTH = "earth"
    METER = "meter"


class ProblemKind(StrEnum):
    """Problems planted in test enquiries."""

    QUANTITY_CONFLICT = "quantity_conflict"
    RATING_CONFLICT = "rating_conflict"
    MISSING_VALUE = "missing_value"
    AMBIGUOUS_UNIT = "ambiguous_unit"
    PROMPT_INJECTION = "prompt_injection"


BBox = Annotated[list[float], Field(min_length=4, max_length=4)]


def check_bbox(box: list[float]) -> list[float]:
    """Raise ``ValueError`` unless ``box`` is ``[x0, y0, x1, y1]`` with positive size."""
    x0, y0, x1, y1 = box
    if not (x1 > x0 and y1 > y0):
        raise ValueError(f"box must have x0 < x1 and y0 < y1, got {box}")
    return box


class Region(StrictModel):
    """A box on one version of one drawing sheet."""

    version: DrawingVersionKind
    sheet: int = Field(ge=1)
    bbox: BBox

    @model_validator(mode="after")
    def _box_has_size(self) -> Region:
        check_bbox(self.bbox)
        return self


class SourceRef(StrictModel):
    """Where a value is stated: a text span on a page, or regions of a drawing."""

    document: DocumentKind
    file: str  # path relative to the project folder, with forward slashes
    page: int | None = Field(default=None, ge=1)  # 1-based; None only for whole-file facts
    source_text: str | None = None  # the exact text as it appears in the document
    regions: list[Region] = Field(default_factory=list)  # one per drawing version

    @model_validator(mode="after")
    def _has_text_or_region(self) -> SourceRef:
        if self.source_text is None and not self.regions:
            raise ValueError("a source needs source_text, regions or both")
        return self


Scalar = str | int | float | None


class SourcedValue(StrictModel):
    """A value with its unit and its source. Shared base for truth and extracted values.

    ``value`` is ``None`` when the document states the item but gives no usable
    value (for example "TBC").
    """

    value: Scalar
    unit: str | None = None
    source: SourceRef


class TruthValue(SourcedValue):
    """What one document really states for one field.

    The same field can appear in several documents; each statement is its own
    ``TruthValue``. When two documents disagree, both are recorded and a
    planted problem points at them.

    Field names are dotted paths, for example ``system.fault_level`` or
    ``way.Q3.rating``. See ``docs/stage-1.md`` for the full list.
    """

    field: str


class SymbolBox(StrictModel):
    """One symbol on one drawing version."""

    id: str  # stable across versions, e.g. "S07"
    cls: SymbolClass
    way: str | None = None  # the outgoing way it belongs to, e.g. "Q3"
    bbox: BBox

    @model_validator(mode="after")
    def _box_has_size(self) -> SymbolBox:
        check_bbox(self.bbox)
        return self


class DrawingVersion(StrictModel):
    """One sheet of a drawing in one version, with every symbol box on it."""

    sheet: int = Field(ge=1)
    version: DrawingVersionKind
    file: str
    page: int | None = Field(default=None, ge=1)  # page of a PDF; None for images
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    dpi: float | None = Field(default=None, gt=0)  # render resolution of a clean PDF
    symbols: list[SymbolBox] = Field(default_factory=list)
    # 3x3 homography from clean pixels to this version's pixels (None for the clean version
    # and for real drawings). Ground truth for the geometric distortion that was applied.
    transform_from_clean: list[list[float]] | None = None

    @model_validator(mode="after")
    def _boxes_inside(self) -> DrawingVersion:
        for s in self.symbols:
            x0, y0, x1, y1 = s.bbox
            if x0 < 0 or y0 < 0 or x1 > self.width_px or y1 > self.height_px:
                raise ValueError(f"symbol {s.id} box {s.bbox} is outside the {self.width_px}x{self.height_px} image")
        return self


class DocumentInfo(StrictModel):
    """A file of the enquiry and its SHA-256 hash."""

    kind: DocumentKind
    file: str
    pages: int | None = Field(default=None, ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlantedProblem(StrictModel):
    """A problem planted on purpose, and what a correct system should do about it."""

    id: str  # e.g. "T03-P1"
    kind: ProblemKind
    field: str | None = None
    description: str
    expected: str  # the behaviour a correct system shows
    sources: list[SourceRef] = Field(default_factory=list)


class EstimateLine(StrictModel):
    """One line of the correct draft estimate. Prices come from the catalogue, not from here."""

    code: str = Field(pattern=r"^PRT-\d{4}$")
    description: str
    quantity: float = Field(gt=0)
    unit: str
    basis: list[str]  # the fields the line depends on
    blocked_by: list[str] = Field(default_factory=list)  # planted problem ids


class AnswerKey(StrictModel):
    """Everything that is true about one enquiry (or one training drawing)."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: str
    origin: Literal["synthetic", "real"]
    purpose: Literal["showcase", "test", "training", "real"]
    seed: int | None = None
    documents: list[DocumentInfo] = Field(default_factory=list)
    drawings: list[DrawingVersion] = Field(default_factory=list)
    values: list[TruthValue] = Field(default_factory=list)
    planted: list[PlantedProblem] = Field(default_factory=list)
    estimate: list[EstimateLine] = Field(default_factory=list)

    def values_for(self, field: str) -> list[TruthValue]:
        """All statements of ``field``, in document order."""
        return [v for v in self.values if v.field == field]

    def drawing(self, sheet: int, version: DrawingVersionKind) -> DrawingVersion:
        """The drawing entry for one sheet and version."""
        for d in self.drawings:
            if d.sheet == sheet and d.version == version:
                return d
        raise KeyError(f"no drawing for sheet {sheet}, version {version}")
