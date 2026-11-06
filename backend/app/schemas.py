"""Pydantic models for data that crosses a boundary: extractor output, matches, estimates, audit events.

Extracted values share their base with the answer key
(:class:`data_generator.schemas.SourcedValue`: value, unit, source document,
page, source text or region), so an extracted value can be scored against
``answers.json`` field by field. On top of that base they add how the value
was found (method), how sure the system is (confidence) and what the engineer
decided (review status).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from data_generator.schemas import DocumentKind, SourcedValue, SourceRef

__all__ = [
    "Agreement", "Confidence", "DocumentKind", "DocumentStatus", "ExtractedValue", "MatchStatus", "Method",
    "ReviewStatus", "SourceRef",
]


class Method(StrEnum):
    """How a value was found: ``rules`` (Stage 2) and ``llm`` (Stage 3) so far."""

    RULES = "rules"
    LLM = "llm"
    OCR = "ocr"
    VISION = "vision"
    DETECTOR = "detector"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CONFLICT = "conflict"


class Agreement(StrEnum):
    """Combined mode (Stage 3): how the rules and the LLM compare for a value. ``None`` in rules mode."""

    AGREE = "agree"  # both read the same value on the same page; one value kept
    DISAGREE = "disagree"  # different values on the same page; both kept for review
    RULES_ONLY = "rules_only"
    LLM_ONLY = "llm_only"


class ReviewStatus(StrEnum):
    """What the engineer decided. Only ``approved`` values reach an estimate."""

    EXTRACTED = "extracted"  # found, not reviewed yet
    APPROVED = "approved"
    EDITED = "edited"  # approved with a value the engineer typed
    REJECTED = "rejected"

    @property
    def is_approved(self) -> bool:
        return self in (ReviewStatus.APPROVED, ReviewStatus.EDITED)


class DocumentStatus(StrEnum):
    """Processing state of one uploaded file, shown on its file card."""

    UPLOADED = "uploaded"
    READING = "reading"
    EXTRACTING = "extracting"
    DONE = "done"
    NOT_READ = "not_read"  # stored, but this stage cannot read it (scanned or photo drawing, PDF without text)
    FAILED = "failed"


class ExtractedValue(SourcedValue):
    """A value found in a document by one method, with its confidence and review status.

    ``field`` uses the answer-key names, for example ``system.fault_level`` or
    ``way.Q3.rating``. ``derivation`` explains a value that is counted or
    combined rather than read from one place (for example the number of way
    labels on a drawing).
    """

    field: str
    method: Method = Method.RULES
    confidence: Confidence
    review_status: ReviewStatus = ReviewStatus.EXTRACTED
    rule: str | None = None  # name of the rule that produced it, for traceability
    derivation: str | None = None
    agreement: Agreement | None = None  # combined mode only


class MatchStatus(StrEnum):
    EXACT = "exact"  # every requested property equals the part's (breaking capacity: lowest that is enough)
    SUBSTITUTE = "substitute"  # nearest safe part; needs review before it reaches the estimate
    UNMATCHED = "unmatched"  # no safe part; never priced


class Requirement(BaseModel):
    """What one estimate line needs from the catalogue, built from approved values only."""

    model_config = ConfigDict(extra="forbid")

    key: str  # stable id within an estimate, e.g. "way.Q3" or "incomer"
    category: str  # catalogue category, e.g. "mccb"
    description: str  # plain words for the screen, e.g. "Way Q3 MCCB 100 A 4P"
    quantity: float = Field(ge=0)
    rating_a: int | None = None
    poles: int | None = None
    min_breaking_ka: int | None = None
    ip_rating: str | None = None
    width_mm: int | None = None
    size: str | None = None
    basis: list[str] = Field(default_factory=list)  # the fields this line depends on


class MatchResult(BaseModel):
    """The catalogue part chosen for a requirement, or why none was chosen."""

    model_config = ConfigDict(extra="forbid")

    status: MatchStatus
    code: str | None = None
    reason: str  # always filled: why this part, or why no part
