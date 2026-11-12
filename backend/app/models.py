"""Database tables (SQLAlchemy 2), created by the Alembic migration 0002.

The column types are portable: PostgreSQL in Docker and CI, SQLite for the
fast local test suite. Money is ``Numeric(12, 2)``; scalar values that may be
text or numbers are stored as JSON.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Stage UX. ``updated_at`` moves with every upload, reading, review and quote; an archived enquiry is
    # hidden from the list but keeps all its data; the sample enquiry may use recorded model runs.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    documents: Mapped[list[Document]] = relationship(back_populates="project", order_by="Document.id",
                                                     cascade="all, delete-orphan")
    values: Mapped[list[ExtractedValueRow]] = relationship(back_populates="project",
                                                           order_by="ExtractedValueRow.id",
                                                           cascade="all, delete-orphan")
    notes: Mapped[list[EnquiryNote]] = relationship(back_populates="project", order_by="EnquiryNote.id",
                                                    cascade="all, delete-orphan")


class EnquiryNote(Base):
    """Text the engineer typed about an enquiry (V4): it may start an enquiry before any file arrives.

    A note is the engineer's own words, kept as data. It is never read for values and never priced.
    """

    __tablename__ = "enquiry_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="notes")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))  # as uploaded; data only, never a path
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    file_type: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str | None] = mapped_column(String(20))  # specification, schematic, requirements
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    model_run: Mapped[str | None] = mapped_column(String(200))  # e.g. "gemma4:e2b, 2026-11-07"; None in rules mode
    # How the file was actually read: "rules", "ocr" or "rules+model"; None while unread (Stage UX).
    read_method: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")
    pages: Mapped[list[Page]] = relationship(back_populates="document", order_by="Page.number",
                                             cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    tables: Mapped[list[Any]] = mapped_column(JSON, default=list)

    document: Mapped[Document] = relationship(back_populates="pages")


class ExtractedValueRow(Base):
    """One extracted value: answer-key fields plus method, confidence and review status."""

    __tablename__ = "extracted_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)  # as extracted (None for "TBC"); never changed
    unit: Mapped[str | None] = mapped_column(String(20))
    source_document: Mapped[str] = mapped_column(String(20))
    source_file: Mapped[str] = mapped_column(String(255))
    page: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    regions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(20))
    review_status: Mapped[str] = mapped_column(String(20), default="extracted")
    rule: Mapped[str | None] = mapped_column(String(60))
    derivation: Mapped[str | None] = mapped_column(Text)
    agreement: Mapped[str | None] = mapped_column(String(20))  # combined mode: agree, disagree, rules_only, llm_only
    quote_match: Mapped[str | None] = mapped_column(String(20))  # model values: exact or words_on_page
    flags: Mapped[list[Any] | None] = mapped_column(JSON, default=list)  # e.g. poles_from_cable_cores
    # Set only by an engineer's approve or edit; the estimate reads these, never ``value``.
    approved_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    approved_unit: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="values")
    document: Mapped[Document] = relationship()


class CatalogueItemRow(Base):
    __tablename__ = "catalogue_items"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(String(200))
    rating_a: Mapped[int | None] = mapped_column(Integer)
    poles: Mapped[int | None] = mapped_column(Integer)
    breaking_ka: Mapped[int | None] = mapped_column(Integer)
    ip_rating: Mapped[str | None] = mapped_column(String(8))
    width_mm: Mapped[int | None] = mapped_column(Integer)
    size: Mapped[str | None] = mapped_column(String(20))
    unit: Mapped[str] = mapped_column(String(8))
    unit_price_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    labour_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))


class Match(Base):
    """The catalogue decision for one requirement of a project; substitutes carry the engineer's review."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_key: Mapped[str] = mapped_column(String(60))
    requirement: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # exact, substitute, unmatched
    code: Mapped[str | None] = mapped_column(ForeignKey("catalogue_items.code"))
    reason: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20))  # approved (exact), pending, approved, rejected
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    currency: Mapped[str] = mapped_column(String(3))
    labour_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    margin_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    materials: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    labour_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    labour: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    margin: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    problems: Mapped[list[Any]] = mapped_column(JSON, default=list)  # missing and conflicting fields
    unmatched: Mapped[list[Any]] = mapped_column(JSON, default=list)  # requirements with no safe part
    pending: Mapped[list[Any]] = mapped_column(JSON, default=list)  # substitutes waiting for review

    lines: Mapped[list[EstimateLineRow]] = relationship(back_populates="estimate", order_by="EstimateLineRow.id",
                                                        cascade="all, delete-orphan")


class EstimateLineRow(Base):
    __tablename__ = "estimate_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(ForeignKey("catalogue_items.code"))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(8))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    labour_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    materials: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    basis: Mapped[list[str]] = mapped_column(JSON, default=list)  # fields the line depends on
    value_ids: Mapped[list[int]] = mapped_column(JSON, default=list)  # approved values it was built from
    substitute_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)

    estimate: Mapped[Estimate] = relationship(back_populates="lines")


class Review(Base):
    """An engineer's decision on a value or a substitute match."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    value_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_values.id", ondelete="CASCADE"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))  # approve, edit, reject
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(40))  # upload, extract, approve, edit, reject, estimate, export, ...
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
