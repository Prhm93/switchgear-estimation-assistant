"""What the screens do: projects, uploads, processing, review, estimate, export.

Every change goes through a function here, and every one writes an audit
event (:func:`audit`) in the same transaction, so the log cannot miss an
action that happened. The actor is "engineer" until login arrives (Stage 8).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app import normalise as norm
from backend.app.catalogue import CatalogueItem, load_catalogue
from backend.app.config import Settings
from backend.app.estimate import ApprovedValue, Draft, build, load_rules
from backend.app.models import (AuditEvent, CatalogueItemRow, Document, Estimate, EstimateLineRow,
                                ExtractedValueRow, Match, Page, Project, Review)
from backend.app.pipeline import analyse_file
from backend.app.schemas import DocumentStatus, MatchStatus, ReviewStatus
from backend.app.storage import FileType, Storage, check_upload

log = logging.getLogger(__name__)
DEFAULT_ACTOR = "engineer"


class ReviewError(ValueError):
    """A review action that is not allowed (the message is safe to show)."""


def audit(session: Session, action: str, entity: str, entity_id: Any = None, project_id: int | None = None,
          actor: str = DEFAULT_ACTOR, **detail: Any) -> None:
    session.add(AuditEvent(project_id=project_id, actor=actor, action=action, entity=entity,
                           entity_id=None if entity_id is None else str(entity_id), detail=detail))


# --- catalogue --------------------------------------------------------------------------------

def sync_catalogue(session: Session, settings: Settings) -> int:
    """Load the catalogue CSV into ``catalogue_items`` (insert new codes, update changed rows)."""
    items = load_catalogue(settings.catalogue_csv)
    existing = {r.code: r for r in session.scalars(select(CatalogueItemRow))}
    for item in items:
        row = existing.get(item.code)
        data = item.model_dump()
        if row is None:
            session.add(CatalogueItemRow(**data))
        else:
            for k, v in data.items():
                setattr(row, k, v)
    audit(session, "catalogue_sync", "catalogue_items", count=len(items), source=settings.catalogue_csv.name)
    session.commit()
    return len(items)


def catalogue_items(session: Session) -> list[CatalogueItem]:
    return [CatalogueItem.model_validate(r, from_attributes=True)
            for r in session.scalars(select(CatalogueItemRow).order_by(CatalogueItemRow.code))]


# --- projects and uploads -----------------------------------------------------------------------

def create_project(session: Session, name: str, reference: str | None = None) -> Project:
    name = " ".join(name.split())
    if not name:
        raise ValueError("A project needs a name.")
    project = Project(name=name[:200], reference=(reference or "").strip()[:100] or None)
    session.add(project)
    session.flush()
    audit(session, "create", "project", project.id, project.id, name=project.name)
    session.commit()
    return project


def add_document(session: Session, storage: Storage, settings: Settings, project: Project, filename: str,
                 data: bytes) -> Document:
    """Check and store one upload. Raises UploadRejected (audited) when a rule is broken."""
    from backend.app.storage import UploadRejected

    display = filename.replace("\\", "/").split("/")[-1][:255] or "unnamed"
    try:
        file_type = check_upload(filename, data, settings.max_upload_bytes, settings.max_pdf_pages)
    except UploadRejected as error:
        audit(session, "upload_rejected", "document", None, project.id, name=display, reason=str(error))
        session.commit()
        raise
    stored = storage.save(data, file_type)
    doc = Document(project_id=project.id, original_name=display, storage_key=stored.key, sha256=stored.sha256,
                   size_bytes=stored.size_bytes, file_type=file_type.value, status=DocumentStatus.UPLOADED.value)
    session.add(doc)
    session.flush()
    audit(session, "upload", "document", doc.id, project.id, name=display, sha256=stored.sha256,
          size_bytes=stored.size_bytes, file_type=file_type.value)
    session.commit()
    return doc


def process_document(sessions: sessionmaker[Session], storage: Storage, document_id: int) -> None:
    """Background task: read, classify and extract one document, updating its status as it goes."""
    with sessions() as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return
        doc.status = DocumentStatus.READING.value
        session.commit()
        try:
            data = storage.read(doc.storage_key)
            analysis = analyse_file(FileType(doc.file_type), data, doc.original_name)
            del data  # the original stays in storage; keep memory low
            doc.status = DocumentStatus.EXTRACTING.value
            doc.kind = analysis.kind.value
            doc.page_count = len(analysis.read.pages) or None
            doc.note = analysis.read.note
            for page in analysis.read.pages:
                session.add(Page(document_id=doc.id, number=page.number, text=page.text, tables=page.tables))
            for v in analysis.values:
                session.add(ExtractedValueRow(
                    project_id=doc.project_id, document_id=doc.id, field=v.field, value=v.value, unit=v.unit,
                    source_document=v.source.document.value, source_file=v.source.file, page=v.source.page,
                    source_text=v.source.source_text, regions=[r.model_dump() for r in v.source.regions],
                    method=v.method.value, confidence=v.confidence.value, review_status=v.review_status.value,
                    rule=v.rule, derivation=v.derivation))
            doc.status = analysis.read.status.value
            audit(session, "extract", "document", doc.id, doc.project_id, kind=doc.kind, status=doc.status,
                  values=len(analysis.values), method="rules")
            session.commit()
        except Exception as error:  # a broken file must not leave the card spinning
            session.rollback()
            doc = session.get(Document, document_id)
            doc.status = DocumentStatus.FAILED.value
            doc.note = f"Could not be read ({type(error).__name__})."
            audit(session, "extract_failed", "document", doc.id, doc.project_id, error=type(error).__name__)
            session.commit()
            log.exception("processing document %s failed", document_id)


# --- review -------------------------------------------------------------------------------------

def parse_input(text: str) -> str | int | float | None:
    """A typed value from the edit form: numbers as numbers, empty as None."""
    t = text.strip()
    if not t:
        return None
    n = norm.number(t)
    return n if n is not None else t


def review_value(session: Session, value_id: int, action: str, new_value: str | None = None,
                 new_unit: str | None = None, reason: str | None = None, actor: str = DEFAULT_ACTOR) -> ExtractedValueRow:
    """Approve, edit (approve with a typed value) or reject one extracted value."""
    row = session.get(ExtractedValueRow, value_id)
    if row is None:
        raise ReviewError("No such value.")
    reason = (reason or "").strip() or None
    old = {"value": row.approved_value if row.review_status in ("approved", "edited") else row.value,
           "unit": row.approved_unit if row.review_status in ("approved", "edited") else row.unit,
           "status": row.review_status}
    if action == "approve":
        if row.value is None:
            raise ReviewError("This value is missing in the document (for example TBC). Edit it to give a value.")
        row.review_status, row.approved_value, row.approved_unit = ReviewStatus.APPROVED.value, row.value, row.unit
    elif action == "edit":
        value = parse_input(new_value or "")
        if value is None:
            raise ReviewError("Type a value, or reject the item.")
        unit = norm.unit((new_unit or "").strip() or None)
        row.review_status, row.approved_value, row.approved_unit = ReviewStatus.EDITED.value, value, unit
    elif action == "reject":
        if not reason:
            raise ReviewError("Give a reason for rejecting.")
        row.review_status, row.approved_value, row.approved_unit = ReviewStatus.REJECTED.value, None, None
    else:
        raise ReviewError(f"Unknown action {action!r}.")
    new = {"value": row.approved_value, "unit": row.approved_unit, "status": row.review_status}
    session.add(Review(project_id=row.project_id, value_id=row.id, action=action, old_value=old, new_value=new,
                       reason=reason, actor=actor))
    audit(session, action, "extracted_value", row.id, row.project_id, actor=actor, field=row.field,
          old=old, new=new, reason=reason)
    session.commit()
    return row


def approved_values(session: Session, project_id: int) -> list[ApprovedValue]:
    """Only approved or edited values: the estimate's only input."""
    rows = session.scalars(select(ExtractedValueRow).where(
        ExtractedValueRow.project_id == project_id,
        ExtractedValueRow.review_status.in_([ReviewStatus.APPROVED.value, ReviewStatus.EDITED.value])))
    return [ApprovedValue(value_id=r.id, field=r.field, value=r.approved_value, unit=r.approved_unit,
                          source=source_label(r.source_document, r.page)) for r in rows]


def source_label(document: str, page: int | None) -> str:
    """Plain words for a source: "specification p5", "schematic sheet 1"."""
    if page is None:
        return document
    return f"{document} sheet {page}" if document == "schematic" else f"{document} p{page}"


# --- estimate -----------------------------------------------------------------------------------

def _sync_matches(session: Session, project_id: int, draft: Draft) -> dict[str, Match]:
    """Keep one match row per requirement; a changed requirement or part resets an approval."""
    existing = {m.requirement_key: m for m in session.scalars(select(Match).where(Match.project_id == project_id))}
    keep: dict[str, Match] = {}
    for d in draft.decisions:
        req = d.requirement.model_dump()
        m = existing.pop(d.requirement.key, None)
        same = m is not None and m.code == d.match.code and m.requirement == req and m.status == d.match.status.value
        if m is None:
            m = Match(project_id=project_id, requirement_key=d.requirement.key)
            session.add(m)
        if not same:
            m.requirement, m.status, m.code, m.reason = req, d.match.status.value, d.match.code, d.match.reason
            m.review_status = {"exact": "approved", "substitute": "pending", "unmatched": "unmatched"}[m.status]
        keep[d.requirement.key] = m
    for stale in existing.values():
        session.delete(stale)
    session.flush()
    return keep


def build_estimate(session: Session, project_id: int, settings: Settings, actor: str = DEFAULT_ACTOR) -> Estimate:
    rules = load_rules(settings.estimate_rules)
    items = catalogue_items(session)
    values = approved_values(session, project_id)
    first = build(values, items, rules)
    matches = _sync_matches(session, project_id, first)
    approved_subs = {(k, m.code) for k, m in matches.items()
                     if m.status == MatchStatus.SUBSTITUTE.value and m.review_status == "approved"}
    draft = build(values, items, rules, approved_substitutes=approved_subs)
    ids_by_field: dict[str, list[int]] = {}
    for v in values:
        ids_by_field.setdefault(v.field, []).append(v.value_id)
    est = Estimate(project_id=project_id, currency=rules.currency, labour_rate=rules.labour_rate_per_hour,
                   margin_percent=rules.margin_percent, materials=draft.totals.materials,
                   labour_hours=draft.totals.labour_hours, labour=draft.totals.labour, margin=draft.totals.margin,
                   total=draft.totals.total, problems=[p.model_dump() for p in draft.problems],
                   unmatched=[{"key": d.requirement.key, "description": d.requirement.description,
                               "reason": d.match.reason} for d in draft.unmatched],
                   pending=[{"key": d.requirement.key, "description": d.requirement.description,
                             "code": d.match.code, "reason": d.match.reason, "match_id": matches[d.requirement.key].id}
                            for d in draft.substitutes_to_review])
    for ln in draft.lines:
        est.lines.append(EstimateLineRow(
            code=ln.code, description=ln.description, quantity=ln.quantity, unit=ln.unit, unit_price=ln.unit_price,
            labour_hours=ln.labour_hours, materials=ln.materials, basis=ln.basis,
            value_ids=sorted({i for f in ln.basis for i in ids_by_field.get(f, [])}),
            substitute_reasons=ln.substitute_reasons))
    session.add(est)
    session.flush()
    audit(session, "estimate", "estimate", est.id, project_id, actor=actor, lines=len(draft.lines),
          total=str(draft.totals.total), problems=len(draft.problems), unmatched=len(draft.unmatched),
          pending_substitutes=len(draft.substitutes_to_review), approved_values=len(values))
    session.commit()
    return est


def review_match(session: Session, match_id: int, action: str, reason: str | None = None,
                 actor: str = DEFAULT_ACTOR) -> Match:
    """Approve or reject a substitute part. Exact and unmatched rows cannot be reviewed."""
    m = session.get(Match, match_id)
    if m is None or m.status != MatchStatus.SUBSTITUTE.value:
        raise ReviewError("Only a substitute part can be approved or rejected.")
    if action not in ("approve", "reject"):
        raise ReviewError(f"Unknown action {action!r}.")
    reason = (reason or "").strip() or None
    if action == "reject" and not reason:
        raise ReviewError("Give a reason for rejecting.")
    old = m.review_status
    m.review_status = "approved" if action == "approve" else "rejected"
    session.add(Review(project_id=m.project_id, match_id=m.id, action=action, old_value={"status": old},
                       new_value={"status": m.review_status, "code": m.code}, reason=reason, actor=actor))
    audit(session, f"substitute_{action}", "match", m.id, m.project_id, actor=actor, code=m.code,
          requirement=m.requirement_key, reason=reason, match_reason=m.reason)
    session.commit()
    return m


def latest_estimate(session: Session, project_id: int) -> Estimate | None:
    return session.scalars(select(Estimate).where(Estimate.project_id == project_id)
                           .order_by(Estimate.id.desc()).limit(1)).first()


# --- dashboard ----------------------------------------------------------------------------------

def project_counts(session: Session) -> dict[str, int]:
    def count(q) -> int:
        return session.scalar(q) or 0

    return {
        "projects": count(select(func.count(Project.id))),
        "documents": count(select(func.count(Document.id))),
        "pending_reviews": count(select(func.count(ExtractedValueRow.id))
                                 .where(ExtractedValueRow.review_status == ReviewStatus.EXTRACTED.value)),
        "errors": count(select(func.count(Document.id)).where(Document.status == DocumentStatus.FAILED.value)),
    }


def money(x: Decimal) -> str:
    return f"{x:,.2f}"
