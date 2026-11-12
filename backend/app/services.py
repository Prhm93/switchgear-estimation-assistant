"""What the screens do: projects, uploads, processing, review, estimate, export.

Every change goes through a function here, and every one writes an audit
event (:func:`audit`) in the same transaction, so the log cannot miss an
action that happened. The actor is "engineer" until login arrives (Stage 8).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.app import enquiry, labels
from backend.app import normalise as norm
from backend.app.catalogue import CatalogueItem, load_catalogue
from backend.app.config import Settings
from backend.app.estimate import ApprovedValue, Draft, build, load_rules
from backend.app.llm.quote import QuoteCheckMode
from backend.app.models import (AuditEvent, CatalogueItemRow, Document, EnquiryNote, Estimate, EstimateLineRow,
                                ExtractedValueRow, Match, Page, Project, Review, utcnow)
from backend.app.drawing.symbols import make_detector
from backend.app.drawing.vision import VisionUnavailable, make_vision_client
from backend.app.pipeline import analyse_file
from backend.app.recordings import RecordingMismatch, find_recording
from backend.app.schemas import DocumentStatus, MatchStatus, ReviewStatus
from backend.app.storage import FileType, Storage, check_upload
from estimation_assistant.providers import ModelProvider, make_provider

log = logging.getLogger(__name__)
DEFAULT_ACTOR = "engineer"
DEFAULT_NAME = "New enquiry"  # until the engineer names it or its specification gives a title
SAMPLE_NAME = "Sample enquiry"
SAMPLE_FILES = ["specification.pdf", "requirements.docx", "drawing/schematic.dxf", "drawing/schematic.pdf"]


class ReviewError(ValueError):
    """A review action that is not allowed (the message is safe to show)."""


def audit(session: Session, action: str, entity: str, entity_id: Any = None, project_id: int | None = None,
          actor: str = DEFAULT_ACTOR, **detail: Any) -> None:
    session.add(AuditEvent(project_id=project_id, actor=actor, action=action, entity=entity,
                           entity_id=None if entity_id is None else str(entity_id), detail=detail))
    if project_id is not None:  # every logged action moves the enquiry's "last updated"
        session.execute(update(Project).where(Project.id == project_id).values(updated_at=utcnow()))


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

def create_project(session: Session, name: str = "", reference: str | None = None,
                   is_sample: bool = False) -> Project:
    """A new enquiry. The name is optional: an unnamed one is named from its specification once read."""
    name = " ".join((name or "").split()) or DEFAULT_NAME
    project = Project(name=name[:200], reference=(reference or "").strip()[:100] or None, is_sample=is_sample)
    session.add(project)
    session.flush()
    audit(session, "create", "project", project.id, project.id, name=project.name, sample=is_sample or None)
    session.commit()
    return project


def add_note(session: Session, project: Project, text: str, actor: str = DEFAULT_ACTOR) -> EnquiryNote | None:
    """Keep text the engineer typed about the enquiry (V4). White space alone is not a note."""
    text = (text or "").strip()
    if not text:
        return None
    note = EnquiryNote(project_id=project.id, text=text[:4000], actor=actor)
    session.add(note)
    session.flush()
    audit(session, "note", "enquiry_note", note.id, project.id, actor=actor, length=len(note.text))
    session.commit()
    return note


def rename_project(session: Session, project: Project, name: str, reference: str | None = None) -> Project:
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("Type a name for the enquiry.")
    old = project.name
    project.name = name[:200]
    if reference is not None:
        project.reference = reference.strip()[:100] or None
    audit(session, "rename", "project", project.id, project.id, name=project.name, old_name=old,
          reference=project.reference)
    session.commit()
    return project


def archive_project(session: Session, project: Project, archived: bool = True) -> Project:
    """Hide an enquiry from the list (or bring it back). Nothing is deleted."""
    project.archived_at = utcnow() if archived else None
    audit(session, "archive" if archived else "unarchive", "project", project.id, project.id)
    session.commit()
    return project


def _delete_values(session: Session, value_ids: list[int]) -> None:
    if value_ids:
        session.execute(delete(Review).where(Review.value_id.in_(value_ids)))
        session.execute(delete(ExtractedValueRow).where(ExtractedValueRow.id.in_(value_ids)))


def delete_project(session: Session, storage: Storage, project: Project) -> None:
    """Delete an enquiry with its files, values, quotes and decisions. The audit entry keeps what was removed.

    The rows are deleted explicitly (not left to the database's cascade) so that it works the same on
    PostgreSQL and SQLite. Past activity lines stay in the log, no longer tied to an enquiry.
    """
    pid, name, keys = project.id, project.name, [d.storage_key for d in project.documents]
    counts = {"documents": len(keys), "values": len(project.values)}
    session.execute(delete(Review).where(Review.project_id == pid))
    estimates = list(session.scalars(select(Estimate.id).where(Estimate.project_id == pid)))
    if estimates:
        session.execute(delete(EstimateLineRow).where(EstimateLineRow.estimate_id.in_(estimates)))
        session.execute(delete(Estimate).where(Estimate.id.in_(estimates)))
    session.execute(delete(Match).where(Match.project_id == pid))
    session.execute(update(AuditEvent).where(AuditEvent.project_id == pid).values(project_id=None))
    session.delete(project)
    audit(session, "delete", "project", pid, None, name=name, **counts)
    session.commit()
    for key in keys:  # after the commit: a failed delete leaves a stray file, never a row without its file
        try:
            storage.delete(key)
        except OSError:
            log.warning("stored file %s of deleted enquiry %s could not be removed", key, pid)


def delete_document(session: Session, storage: Storage, doc: Document) -> None:
    """Delete one file with its pages and values (and the decisions made on them)."""
    key, pid = doc.storage_key, doc.project_id
    ids = list(session.scalars(select(ExtractedValueRow.id).where(ExtractedValueRow.document_id == doc.id)))
    _delete_values(session, ids)
    audit(session, "document_delete", "document", doc.id, pid, name=doc.original_name, sha256=doc.sha256,
          values=len(ids))
    session.delete(doc)
    session.commit()
    try:
        storage.delete(key)
    except OSError:
        log.warning("stored file %s could not be removed", key)


def reset_document(session: Session, doc: Document) -> None:
    """Prepare "Read again": drop the file's pages and values so it can be read with today's settings."""
    ids = list(session.scalars(select(ExtractedValueRow.id).where(ExtractedValueRow.document_id == doc.id)))
    _delete_values(session, ids)
    session.execute(delete(Page).where(Page.document_id == doc.id))
    doc.status, doc.note, doc.model_run, doc.read_method = DocumentStatus.UPLOADED.value, None, None, None
    audit(session, "read_again", "document", doc.id, doc.project_id, name=doc.original_name, values_removed=len(ids))
    session.commit()
    session.expire_all()


def create_sample(session: Session, storage: Storage, settings: Settings) -> tuple[Project, list[int]]:
    """A fresh sample enquiry from the committed showcase files. Returns it and the ids of its files to read."""
    missing = [n for n in SAMPLE_FILES if not (settings.sample_dir / n).is_file()]
    if missing:
        raise FileNotFoundError(f"Sample files not found: {', '.join(missing)}")
    project = create_project(session, SAMPLE_NAME, is_sample=True)
    ids = [add_document(session, storage, settings, project, name, (settings.sample_dir / name).read_bytes()).id
           for name in SAMPLE_FILES]
    return project, ids


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


def model_provider(settings: Settings | None, data: bytes,
                   sample: bool = False) -> tuple[ModelProvider | None, str | None]:
    """The provider for this file in the configured mode, and a note when the mode cannot be used.

    Recorded mode uses only a recording whose SHA-256 equals the uploaded bytes;
    with none, the file is read by the rules alone and the note says why. A file of the sample
    enquiry is read in recorded mode whatever MODEL_MODE says (normal uploads follow MODEL_MODE).
    """
    mode = settings.model_mode if settings else "rules"
    if sample and settings is not None and mode == "rules":
        mode = "recorded"
    if mode == "rules":
        return None, None
    if mode == "recorded":
        try:
            recording = find_recording(settings.recorded_dir, data)
        except (RecordingMismatch, ValueError) as error:
            return None, f"Recorded model run refused: {error}"
        if recording is None:
            return None, "No recorded model run matches this file's SHA-256; read by the rules only."
        return make_provider("recorded", recording=recording), None
    return make_provider(mode, url=settings.ollama_url, model=settings.ollama_model), None


def process_document(sessions: sessionmaker[Session], storage: Storage, document_id: int,
                     settings: Settings | None = None) -> None:
    """Background task: read, classify and extract one document, updating its status as it goes."""
    with sessions() as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return
        doc.status = DocumentStatus.READING.value
        session.commit()
        try:
            data = storage.read(doc.storage_key)
            sample = bool(session.scalar(select(Project.is_sample).where(Project.id == doc.project_id)))
            provider, model_note = model_provider(settings, data, sample=sample)
            # The sample enquiry always shows the app's default, the relaxed quote check.
            quote_check = QuoteCheckMode(settings.quote_check if settings and not sample else QuoteCheckMode.RELAXED)
            drawing = {"drawing_reading": settings.drawing_reading, "ocr_dpi": settings.ocr_dpi,
                       "tesseract_cmd": settings.tesseract_cmd} if settings else {}
            vision_note = None
            if settings is not None:
                drawing["detector"] = make_detector(settings.symbol_detector)
                try:
                    drawing["vision"] = make_vision_client(settings)
                except VisionUnavailable as error:
                    vision_note = f"Vision model off: {error}."
            analysis = analyse_file(FileType(doc.file_type), data, doc.original_name, provider,
                                    quote_check=quote_check, **drawing)
            del data  # the original stays in storage; keep memory low
            doc.status = DocumentStatus.EXTRACTING.value
            doc.kind = analysis.kind.value
            doc.page_count = len(analysis.read.pages) or None
            notes = [analysis.read.note, model_note, vision_note if analysis.kind.value == "schematic" else None,
                     f"Model run failed, read by the rules only: {analysis.llm_error}" if analysis.llm_error else None]
            doc.note = " ".join(n for n in notes if n) or None
            doc.model_run = analysis.model_run
            if analysis.read.status == DocumentStatus.DONE:
                picture = "+".join(m for m, on in (("ocr", analysis.drawings), ("vision", analysis.vision_run)) if on)
                doc.read_method = picture or ("rules+model" if analysis.llm else "rules")
            if analysis.kind.value == "specification" and analysis.read.pages:
                _name_from_specification(session, doc.project_id, analysis.read.pages[0].text)
            for page in analysis.read.pages:
                session.add(Page(document_id=doc.id, number=page.number, text=page.text, tables=page.tables))
            for v in analysis.values:
                session.add(ExtractedValueRow(
                    project_id=doc.project_id, document_id=doc.id, field=v.field, value=v.value, unit=v.unit,
                    source_document=v.source.document.value, source_file=v.source.file, page=v.source.page,
                    source_text=v.source.source_text, regions=[r.model_dump() for r in v.source.regions],
                    method=v.method.value, confidence=v.confidence.value, review_status=v.review_status.value,
                    rule=v.rule, derivation=v.derivation, agreement=v.agreement.value if v.agreement else None,
                    quote_match=v.quote_match.value if v.quote_match else None,
                    flags=[f.value for f in v.flags]))
            doc.status = analysis.read.status.value
            audit(session, "extract", "document", doc.id, doc.project_id, kind=doc.kind, status=doc.status,
                  values=len(analysis.values),
                  method="ocr" if analysis.drawings else ("rules+llm" if analysis.llm else "rules"),
                  model_run=analysis.model_run)
            if analysis.llm and analysis.llm.rejected:
                # Every rejected model value is logged with its reason; none of them is stored as a value.
                audit(session, "llm_values_rejected", "document", doc.id, doc.project_id,
                      count=len(analysis.llm.rejected),
                      rejected=[r.model_dump(mode="json") for r in analysis.llm.rejected])
            if analysis.flags:
                audit(session, "instruction_text_flagged", "document", doc.id, doc.project_id,
                      flags=[f.model_dump() for f in analysis.flags])
            session.commit()
            if settings is not None:
                refresh_quote(session, doc.project_id, settings)
        except Exception as error:  # a broken file must not leave the card spinning
            session.rollback()
            doc = session.get(Document, document_id)
            doc.status = DocumentStatus.FAILED.value
            doc.note = f"Could not be read ({type(error).__name__})."
            audit(session, "extract_failed", "document", doc.id, doc.project_id, error=type(error).__name__)
            session.commit()
            log.exception("processing document %s failed", document_id)


def _name_from_specification(session: Session, project_id: int, first_page: str) -> None:
    """Name an enquiry the engineer left unnamed from its specification's title, and take its reference."""
    project = session.get(Project, project_id)
    if project is None or project.name not in (DEFAULT_NAME, SAMPLE_NAME):
        return
    name, reference = labels.title_from_specification(first_page)
    if name:
        project.name = f"{SAMPLE_NAME}: {name}"[:200] if project.is_sample else name
    if reference and not project.reference:
        project.reference = reference


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


def resolve_field(session: Session, project_id: int, field: str, keep_value_id: int | None = None,
                  typed_value: str | None = None, typed_unit: str | None = None, reason: str | None = None,
                  actor: str = DEFAULT_ACTOR) -> None:
    """Settle a conflict in one step: keep one source's value ("Use this") or a typed one.

    The kept value (and any other source giving the same value) is approved; every other value of
    the field is rejected with the reason. Each change is its own review and audit entry.
    """
    rows = [r for r in session.scalars(select(ExtractedValueRow).where(
        ExtractedValueRow.project_id == project_id, ExtractedValueRow.field == field).order_by(ExtractedValueRow.id))
        if r.review_status != ReviewStatus.REJECTED.value]
    if not rows:
        raise ReviewError("No such field.")
    reason = (reason or "").strip() or None
    if keep_value_id is not None:
        keep = next((r for r in rows if r.id == keep_value_id), None)
        if keep is None or keep.value is None:
            raise ReviewError("That value cannot be used.")
        kept_value, kept_unit = enquiry.shown(keep)
        chosen = (norm.value_key(kept_value), norm.unit(kept_unit))
        why = reason or f"Other source chosen: {labels.display(kept_value, kept_unit)}"
        for r in rows:
            value, unit = enquiry.shown(r)
            if r.value is not None and (norm.value_key(value), norm.unit(unit)) == chosen:
                if r.review_status == ReviewStatus.EXTRACTED.value:
                    review_value(session, r.id, "approve", reason=reason, actor=actor)
            else:
                review_value(session, r.id, "reject", reason=why, actor=actor)
        return
    if parse_input(typed_value or "") is None:
        raise ReviewError("Type a value, or choose one of the sources.")
    first = rows[0]
    review_value(session, first.id, "edit", typed_value, typed_unit, reason, actor)
    typed = labels.display(first.approved_value, first.approved_unit)
    for r in rows[1:]:
        review_value(session, r.id, "reject", reason=reason or f"Engineer typed another value: {typed}", actor=actor)


def accept_all(session: Session, project: Project, actor: str = DEFAULT_ACTOR) -> int:
    """Approve every value "Accept all" may take (see :func:`backend.app.enquiry.bulk_acceptable`).

    One review and one audit entry per value, each with the actor, plus one summary entry.
    """
    rows = enquiry.bulk_acceptable(enquiry.review_groups(project))
    for v in rows:
        review_value(session, v.id, "approve", reason="approved with all agreeing values", actor=actor)
    audit(session, "approve_agreed", "project", project.id, project.id, actor=actor, approved=len(rows))
    session.commit()
    return len(rows)


def approved_values(session: Session, project_id: int) -> list[ApprovedValue]:
    """Only approved or edited values: the estimate's only input."""
    rows = session.scalars(select(ExtractedValueRow).where(
        ExtractedValueRow.project_id == project_id,
        ExtractedValueRow.review_status.in_([ReviewStatus.APPROVED.value, ReviewStatus.EDITED.value])))
    return [ApprovedValue(value_id=r.id, field=r.field, value=r.approved_value, unit=r.approved_unit,
                          source=source_label(r.source_document, r.page)) for r in rows]


def open_values(session: Session, project_id: int) -> list[ApprovedValue]:
    """Values not yet reviewed. The estimate never prices them; it uses them only to see open conflicts."""
    rows = session.scalars(select(ExtractedValueRow).where(
        ExtractedValueRow.project_id == project_id,
        ExtractedValueRow.review_status == ReviewStatus.EXTRACTED.value))
    return [ApprovedValue(value_id=r.id, field=r.field, value=r.value, unit=r.unit,
                          source=source_label(r.source_document, r.page)) for r in rows if r.value is not None]


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
    pending_values = open_values(session, project_id)
    first = build(values, items, rules, open_values=pending_values)
    matches = _sync_matches(session, project_id, first)
    approved_subs = {(k, m.code) for k, m in matches.items()
                     if m.status == MatchStatus.SUBSTITUTE.value and m.review_status == "approved"}
    draft = build(values, items, rules, approved_substitutes=approved_subs, open_values=pending_values)
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


def refresh_quote(session: Session, project_id: int, settings: Settings, actor: str = DEFAULT_ACTOR) -> Estimate | None:
    """Rebuild the quote after anything it depends on changed. A failure is logged, never raised:
    the decision that triggered it is already saved, and the Quote screen says it is out of date."""
    try:
        return build_estimate(session, project_id, settings, actor)
    except Exception:
        session.rollback()
        log.exception("rebuilding the quote of enquiry %s failed", project_id)
        return None


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
