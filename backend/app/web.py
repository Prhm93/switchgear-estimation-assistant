"""Server-rendered screens (Jinja2 + HTMX): home, projects, project dashboard, upload, analysis, review, estimate.

All document text and every value reach the templates as plain data and are
escaped by Jinja's autoescaping; nothing from a document is marked safe.
Writes go through :mod:`backend.app.services`, which records each in the
audit log.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from backend.app import normalise as norm
from backend.app import services
from backend.app.highlight import segments
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow, Match, Project
from backend.app.report import estimate_docx
from backend.app.schemas import DocumentStatus, ReviewStatus
from backend.app.storage import UploadRejected

router = APIRouter()
BUSY = {DocumentStatus.UPLOADED.value, DocumentStatus.READING.value, DocumentStatus.EXTRACTING.value}
STATUS_WORDS = {"uploaded": "Queued", "reading": "Reading", "extracting": "Extracting", "done": "Read",
                "not_read": "Not read yet", "failed": "Could not be read"}
KIND_WORDS = {"specification": "Specification", "schematic": "Drawing", "requirements": "Customer letter"}
FIELD_ORDER = ["system.", "enclosure.", "incomer.", "busbar.", "metering.", "ways.count", "way."]
REQUIRED = ["system.voltage", "system.fault_level", "enclosure.form", "enclosure.ip_rating", "enclosure.cable_entry",
            "incomer.device", "incomer.rating", "incomer.poles", "busbar.rating", "metering.ct_ratio",
            "metering.meter", "ways.count"]
WAY_REQUIRED = ["device", "rating", "poles", "cable"]


def get_session(request: Request):
    sessions = request.app.state.sessions
    if sessions is None:
        raise HTTPException(503, "The database is not configured (DATABASE_URL).")
    with sessions() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def render(request: Request, template: str, /, status_code: int = 200, **context: Any) -> HTMLResponse:
    """Render a template; ``template`` is positional-only so any context key (``name`` too) is allowed.

    Adds the sidebar context: the environment, and for a project screen the
    project switcher list and the number of values still to review.
    """
    templates = request.app.state.templates
    base = {"app_name": request.app.state.settings.app_name, "status_words": STATUS_WORDS, "kind_words": KIND_WORDS,
            "environment": request.app.state.settings.environment}
    project = context.get("project")
    if isinstance(project, Project):
        base.update(sidebar_context(project))
    return templates.TemplateResponse(request, template, {**base, **context}, status_code=status_code)


def initials(name: str) -> str:
    """Two characters for the project tile: the first letters of the first two words."""
    words = [w for w in re.split(r"[\s_/-]+", name) if w]
    letters = "".join(w[0] for w in words[:2]) if len(words) > 1 else name[:2]
    return letters.upper() or "P"


def sidebar_context(project: Project) -> dict[str, Any]:
    """Project switcher entries (the 20 newest projects) and the number of values to review."""
    session = object_session(project)
    others = []
    if session is not None:
        others = list(session.execute(select(Project.id, Project.name).order_by(Project.id.desc()).limit(20)))
    return {"switch_projects": others, "project_initials": initials(project.name),
            "review_count": sum(1 for v in project.values if v.review_status == ReviewStatus.EXTRACTED.value)}


def project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "No such project.")
    return project


def field_sort_key(field: str) -> tuple:
    group = next((i for i, p in enumerate(FIELD_ORDER) if field.startswith(p)), len(FIELD_ORDER))
    m = re.match(r"^way\.Q(\d+)\.(.+)$", field)
    return (group, int(m.group(1)), m.group(2)) if m else (group, 0, field)


def field_label(field: str) -> str:
    m = re.match(r"^way\.(\w+)\.(.+)$", field)
    if m:
        return f"Way {m.group(1)} · {m.group(2).replace('_', ' ')}"
    return field.replace(".", " · ").replace("_", " ")


def display(value: Any, unit: str | None) -> str:
    if value is None:
        return "Not given"
    return f"{value} {unit}" if unit else str(value)


# --- dashboard and projects ---------------------------------------------------------------------

SHOWCASE_NAME = "showcase"


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """The public home page. Works without a database; with one, the hero cards show the showcase project."""
    showcase, summary = None, None
    sessions = request.app.state.sessions
    if sessions is not None:
        try:
            with sessions() as session:
                found = session.scalars(select(Project).where(func.lower(Project.name).contains(SHOWCASE_NAME))
                                        .order_by(Project.id.desc()).limit(1)).first()
                if found is not None:
                    summary = project_summary(found)
                    summary = {k: summary[k] for k in ("values", "approved", "review", "conflict", "missing")}
                    showcase = {"id": found.id, "name": found.name}
        except Exception:  # an unreachable database must not take the home page down
            showcase, summary = None, None
    return render(request, "home.html", showcase=showcase, summary=summary)


@router.get("/projects", response_class=HTMLResponse)
def projects(request: Request, session: SessionDep) -> HTMLResponse:
    projects = list(session.scalars(select(Project).order_by(Project.id.desc())))
    pending = dict(session.execute(select(ExtractedValueRow.project_id, func.count(ExtractedValueRow.id))
                                   .where(ExtractedValueRow.review_status == "extracted")
                                   .group_by(ExtractedValueRow.project_id)).all())
    approved = dict(session.execute(select(ExtractedValueRow.project_id, func.count(ExtractedValueRow.id))
                                    .where(ExtractedValueRow.review_status.in_(["approved", "edited"]))
                                    .group_by(ExtractedValueRow.project_id)).all())
    totals = dict(session.execute(select(ExtractedValueRow.project_id, func.count(ExtractedValueRow.id))
                                  .group_by(ExtractedValueRow.project_id)).all())
    errors = dict(session.execute(select(Document.project_id, func.count(Document.id))
                                  .where(Document.status == "failed").group_by(Document.project_id)).all())
    rows = [{"project": p, "documents": len(p.documents), "pending": pending.get(p.id, 0),
             "approved": approved.get(p.id, 0), "value_count": totals.get(p.id, 0), "errors": errors.get(p.id, 0),
             "estimate": services.latest_estimate(session, p.id)} for p in projects]
    return render(request, "projects.html", counts=services.project_counts(session), rows=rows)


@router.get("/projects/new", response_class=HTMLResponse)
def new_project_form(request: Request) -> HTMLResponse:
    return render(request, "project_new.html", error=None, name="", reference="")


@router.post("/projects")
def create_project(request: Request, session: SessionDep, name: Annotated[str, Form()] = "",
                   reference: Annotated[str, Form()] = "") -> Response:
    try:
        project = services.create_project(session, name, reference)
    except ValueError as error:
        return render(request, "project_new.html", status_code=422, error=str(error), name=name, reference=reference)
    return RedirectResponse(f"/projects/{project.id}/upload", status_code=303)


# --- upload ---------------------------------------------------------------------------------------

def _documents_context(project: Project) -> dict[str, Any]:
    return {"project": project, "documents": project.documents,
            "busy": any(d.status in BUSY for d in project.documents)}


@router.get("/projects/{project_id}/upload", response_class=HTMLResponse)
def upload_page(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    settings = request.app.state.settings
    return render(request, "upload.html", errors=[], max_mb=settings.max_upload_mb,
                  max_pages=settings.max_pdf_pages, **_documents_context(project))


@router.get("/projects/{project_id}/documents", response_class=HTMLResponse)
def document_cards(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    """The file cards; polled by HTMX every second while a file is being processed."""
    project = project_or_404(session, project_id)
    return render(request, "partials/documents.html", errors=[], **_documents_context(project))


@router.post("/projects/{project_id}/documents", response_class=HTMLResponse)
async def upload(request: Request, project_id: int, session: SessionDep, background: BackgroundTasks,
                 files: Annotated[list[UploadFile], File()]) -> Response:
    project = project_or_404(session, project_id)
    settings, storage = request.app.state.settings, request.app.state.storage
    errors: list[dict[str, str]] = []
    for upload_file in files:
        data = await upload_file.read(settings.max_upload_bytes + 1)  # never read more than the limit
        try:
            doc = services.add_document(session, storage, settings, project, upload_file.filename or "", data)
        except UploadRejected as error:
            errors.append({"name": (upload_file.filename or "unnamed").replace("\\", "/").split("/")[-1],
                           "reason": str(error)})
            continue
        background.add_task(services.process_document, request.app.state.sessions, storage, doc.id)
    session.refresh(project)
    if request.headers.get("HX-Request"):
        return render(request, "partials/documents.html", errors=errors, **_documents_context(project))
    if errors:
        return render(request, "upload.html", status_code=422, errors=errors, max_mb=settings.max_upload_mb,
                      max_pages=settings.max_pdf_pages, **_documents_context(project))
    return RedirectResponse(f"/projects/{project_id}/upload", status_code=303)


# --- analysis -------------------------------------------------------------------------------------

def _anchor(v: ExtractedValueRow) -> str | None:
    """Table cells are found inside their way's row."""
    if v.rule and v.rule.startswith("spec.table.") and (m := re.match(r"^way\.(\w+)\.", v.field)):
        return m.group(1)
    return None


@router.get("/projects/{project_id}/analysis", response_class=HTMLResponse)
def analysis(request: Request, project_id: int, session: SessionDep, doc: int | None = None,
             page: int | None = None) -> HTMLResponse:
    project = project_or_404(session, project_id)
    readable = [d for d in project.documents if d.pages]
    current = next((d for d in project.documents if d.id == doc), None) or (readable[0] if readable else None)
    pages, page_no, segs, values = [], None, [], []
    if current is not None and current.pages:
        pages = current.pages
        page_no = page if page in {p.number for p in pages} else pages[0].number
        text = next(p.text for p in pages if p.number == page_no)
        values = sorted((v for v in project.values if v.document_id == current.id and v.page == page_no),
                        key=lambda v: field_sort_key(v.field))
        segs = segments(text, [(v.id, v.source_text or "", _anchor(v)) for v in values])
    return render(request, "analysis.html", project=project, current=current, pages=pages, page_no=page_no,
                  segments=segs, values=values, field_label=field_label, display=display)


# --- review ---------------------------------------------------------------------------------------

WAY_FIELD = re.compile(r"^way\.(\w+)\.")


def partial_ways(rows: list[Any]) -> dict[str, list[str]]:
    """Ways missing from a document that lists ways, mapped to the documents they are missing from.

    The specification and the drawing both list the outgoing ways; a way in only
    one of them is a quantity question for the engineer, so it is never approved
    in bulk. Rejected values do not count as stating a way.
    """
    seen: dict[str, set[str]] = {}
    for r in rows:
        if r.review_status != ReviewStatus.REJECTED.value and (m := WAY_FIELD.match(r.field)):
            seen.setdefault(m.group(1), set()).add(r.source_document)
    listing = set().union(*seen.values()) if seen else set()
    if len(listing) < 2:
        return {}
    return {w: sorted(listing - kinds) for w, kinds in seen.items() if kinds != listing}


def open_in_a_document(rows: list[Any]) -> bool:
    """True when a document leaves the field open (for example "TBC") while another gives a value."""
    return any(r.value is None and r.review_status != ReviewStatus.REJECTED.value for r in rows)


def review_groups(project: Project) -> OrderedDict[str, dict[str, Any]]:
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for v in sorted(project.values, key=lambda v: (field_sort_key(v.field), v.id)):
        g = groups.setdefault(v.field, {"field": v.field, "label": field_label(v.field), "values": []})
        g["values"].append(v)
    partial = partial_ways(project.values)
    for g in groups.values():
        m = WAY_FIELD.match(g["field"])
        g["missing_from"] = partial.get(m.group(1), []) if m else []
        live = [v for v in g["values"] if v.review_status != ReviewStatus.REJECTED.value and v.value is not None]
        current = {(norm.value_key(v.approved_value if v.review_status in ("approved", "edited") else v.value),
                    norm.unit(v.approved_unit if v.review_status in ("approved", "edited") else v.unit))
                   for v in live}
        g["conflict"] = len(current) > 1
        g["pending"] = any(v.review_status == ReviewStatus.EXTRACTED.value for v in g["values"])
        g["left_open"] = open_in_a_document(g["values"])
    return groups


def missing_information(project: Project, groups: OrderedDict[str, dict[str, Any]]) -> list[dict[str, str]]:
    stated = {f for f, g in groups.items() if any(v.value is not None for v in g["values"])}
    ways = sorted({m.group(1) for f in groups if (m := re.match(r"^way\.(\w+)\.", f))},
                  key=lambda w: (len(w), w))
    needed = REQUIRED + [f"way.{w}.{p}" for w in ways for p in WAY_REQUIRED]
    out = []
    for f in needed:
        if f not in stated:
            tbc = f in groups
            out.append({"field": f, "label": field_label(f),
                        "why": "Stated as TBC; no value given" if tbc else "Not found in any document read"})
    return out


def segment_counts(project: Project, groups: OrderedDict[str, dict[str, Any]],
                   missing: list[dict[str, str]]) -> dict[str, int]:
    """Counts for the segment bar and the ring gauge. Rejected values count in none of them."""
    in_conflict = {v.id for g in groups.values() if g["conflict"] for v in g["values"]}
    pending = [v for v in project.values if v.review_status == ReviewStatus.EXTRACTED.value]
    return {"values": sum(1 for v in project.values if v.review_status != ReviewStatus.REJECTED.value),
            "approved": sum(1 for v in project.values if v.review_status in ("approved", "edited")),
            "conflict": sum(1 for v in pending if v.id in in_conflict),
            "review": sum(1 for v in pending if v.id not in in_conflict),
            "missing": len(missing)}


def _review_context(project: Project) -> dict[str, Any]:
    groups = review_groups(project)
    missing = missing_information(project, groups)
    # Conflicts first, then values still to review, then reviewed ones; field order within each.
    shown = OrderedDict(sorted(groups.items(), key=lambda kv: (not kv[1]["conflict"], not kv[1]["pending"])))
    return {"project": project, "groups": shown, "missing": missing, "seg": segment_counts(project, groups, missing),
            "field_label": field_label, "display": display, "source_label": services.source_label,
            "conflicts": sum(1 for g in groups.values() if g["conflict"]),
            "pending": sum(1 for v in project.values if v.review_status == "extracted"),
            "not_read": [d for d in project.documents if d.status == DocumentStatus.NOT_READ.value]}


def project_summary(project: Project) -> dict[str, Any]:
    """The segment counts plus the review groups, the missing list and the fields in conflict."""
    groups = review_groups(project)
    missing = missing_information(project, groups)
    return {**segment_counts(project, groups, missing), "groups": groups, "missing_list": missing,
            "conflicts": [g for g in groups.values() if g["conflict"]]}


def way_of(field: str) -> str:
    """The way column of the dashboard table: Q2, IN for the incomer, a dash otherwise."""
    if m := WAY_FIELD.match(field):
        return m.group(1)
    return "IN" if field.startswith("incomer.") else "-"


DASHBOARD_ROWS = 12
FILTERS = {"all": "All", "review": "Needs review", "approved": "Approved"}


def dashboard_rows(groups: OrderedDict[str, dict[str, Any]], show: str) -> list[dict[str, Any]]:
    """One row per value that is not rejected; conflicts first, then values to review, then approved ones."""
    rows = []
    for g in groups.values():
        for v in g["values"]:
            if v.review_status == ReviewStatus.REJECTED.value:
                continue
            done = v.review_status in ("approved", "edited")
            if (show == "review" and done) or (show == "approved" and not done):
                continue
            others = [o for o in g["values"] if o.id != v.id and o.review_status != ReviewStatus.REJECTED.value]
            rows.append({"v": v, "way": way_of(g["field"]), "label": g["label"], "conflict": g["conflict"],
                         "done": done, "others": others, "rank": (not g["conflict"], done)})
    rows.sort(key=lambda r: r["rank"])  # stable: field order within each rank
    return rows


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_dashboard(request: Request, project_id: int, session: SessionDep, show: str = "all") -> HTMLResponse:
    """Overview of one project. It changes nothing itself: its buttons post to the review routes."""
    project = project_or_404(session, project_id)
    show = show if show in FILTERS else "all"
    summary = project_summary(project)
    rows = dashboard_rows(summary["groups"], show)
    counts = {"all": summary["values"], "review": summary["review"] + summary["conflict"],
              "approved": summary["approved"]}
    events = list(session.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id)
                                  .order_by(AuditEvent.id.desc()).limit(5)))
    estimate = services.latest_estimate(session, project_id)
    blocked = len({line for p in estimate.problems for line in p["lines"]}) if estimate else 0
    return render(request, "project_dashboard.html", project=project, summary=summary,
                  rows=rows[:DASHBOARD_ROWS], row_total=len(rows), show=show, filters=FILTERS,
                  filter_counts=counts, events=events, estimate=estimate, blocked=blocked,
                  money=services.money, display=display, source_label=services.source_label,
                  audit_detail=audit_detail)


@router.get("/projects/{project_id}/review", response_class=HTMLResponse)
def review_page(request: Request, project_id: int, session: SessionDep, error: str | None = None) -> HTMLResponse:
    project = project_or_404(session, project_id)
    return render(request, "review.html", error=error, **_review_context(project))


@router.post("/values/{value_id}/{action}")
def review_value(request: Request, value_id: int, action: str, session: SessionDep,
                 value: Annotated[str, Form()] = "", unit: Annotated[str, Form()] = "",
                 reason: Annotated[str, Form()] = "") -> Response:
    row = session.get(ExtractedValueRow, value_id)
    if row is None or action not in ("approve", "edit", "reject"):
        raise HTTPException(404)
    project_id = row.project_id
    error = None
    try:
        services.review_value(session, value_id, action, value, unit, reason)
    except services.ReviewError as e:
        error = str(e)
    if request.headers.get("HX-Request"):
        project = project_or_404(session, project_id)
        session.refresh(project)
        return render(request, "partials/review_body.html", error=error, **_review_context(project))
    target = f"/projects/{project_id}/review#f-{row.field}"
    return RedirectResponse(target if error is None else f"/projects/{project_id}/review?error={error}",
                            status_code=303)


@router.post("/projects/{project_id}/review/approve-agreed")
def approve_agreed(request: Request, project_id: int, session: SessionDep) -> Response:
    """Approve every unreviewed high-confidence value whose field has no conflict; each is audited.

    Left for the engineer: a way missing from one of the documents that list ways, and a field
    that one document leaves open (for example "TBC") while another gives a value.
    """
    project = project_or_404(session, project_id)
    approved = 0
    for g in review_groups(project).values():
        if g["conflict"] or g["missing_from"] or g["left_open"]:
            continue
        for v in g["values"]:
            if v.review_status == "extracted" and v.confidence == "high" and v.value is not None:
                services.review_value(session, v.id, "approve", reason="approved with all agreeing values")
                approved += 1
    services.audit(session, "approve_agreed", "project", project_id, project_id, approved=approved)
    session.commit()
    return RedirectResponse(f"/projects/{project_id}/review", status_code=303)


# --- estimate -------------------------------------------------------------------------------------

@router.post("/projects/{project_id}/estimate")
def build_estimate(request: Request, project_id: int, session: SessionDep) -> Response:
    project_or_404(session, project_id)
    services.build_estimate(session, project_id, request.app.state.settings)
    return RedirectResponse(f"/projects/{project_id}/estimate", status_code=303)


@router.get("/projects/{project_id}/estimate", response_class=HTMLResponse)
def estimate_page(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    est = services.latest_estimate(session, project_id)
    approved = len(services.approved_values(session, project_id))
    return render(request, "estimate.html", project=project, estimate=est, approved=approved,
                  money=services.money, field_label=field_label)


@router.post("/matches/{match_id}/{action}")
def review_match(request: Request, match_id: int, action: str, session: SessionDep,
                 reason: Annotated[str, Form()] = "") -> Response:
    m = session.get(Match, match_id)
    if m is None or action not in ("approve", "reject"):
        raise HTTPException(404)
    try:
        services.review_match(session, match_id, action, reason)
    except services.ReviewError as error:
        raise HTTPException(422, str(error)) from error
    services.build_estimate(session, m.project_id, request.app.state.settings)
    return RedirectResponse(f"/projects/{m.project_id}/estimate", status_code=303)


@router.get("/projects/{project_id}/estimates/{estimate_id}/report.docx")
def export_docx(request: Request, project_id: int, estimate_id: int, session: SessionDep) -> Response:
    project = project_or_404(session, project_id)
    est = session.get(Estimate, estimate_id)
    if est is None or est.project_id != project_id:
        raise HTTPException(404)
    ids = {i for ln in est.lines for i in ln.value_ids}
    values = {v.id: v for v in session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.id.in_(ids)))}
    data = estimate_docx(project, est, values, datetime.now(UTC))
    services.audit(session, "export", "estimate", est.id, project_id, format="docx", bytes=len(data),
                   sha256=__import__("hashlib").sha256(data).hexdigest())
    session.commit()
    name = f"estimate-{project_id}-{estimate_id}.docx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _state_words(state: Any) -> str:
    """{"value": 200, "unit": "A", "status": "extracted"} as "200 A, extracted"."""
    if not isinstance(state, dict):
        return str(state)
    value = display(state["value"], state.get("unit")) if state.get("value") is not None else None
    return ", ".join(str(x) for x in (value, state.get("code"), state.get("status")) if x)


def audit_detail(detail: dict[str, Any]) -> list[tuple[str, str]]:
    """An audit event's detail as (label, plain text) pairs; old and new states become one change."""
    out: list[tuple[str, str]] = []
    if "old" in detail or "new" in detail:
        out.append(("change", f"{_state_words(detail.get('old'))} → {_state_words(detail.get('new'))}"))
    for key, value in detail.items():
        if key not in ("old", "new") and value is not None:
            out.append((key.replace("_", " "), _state_words(value)))
    return out


@router.get("/projects/{project_id}/audit", response_class=HTMLResponse)
def audit_log(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    events = list(session.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id)
                                  .order_by(AuditEvent.id.desc())))
    return render(request, "audit.html", project=project, events=events, audit_detail=audit_detail)
