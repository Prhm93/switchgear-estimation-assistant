"""Server-rendered screens (Jinja2 + HTMX).

The flow is: Enquiries (the list) -> an enquiry's three steps, Files, Check and
Quote -> the report. Proof viewer and Activity sit in the enquiry's Details
menu. Old ``/projects/...`` addresses redirect to ``/enquiries/...``.

All document text and every value reach the templates as plain data and are
escaped by Jinja's autoescaping; nothing from a document is marked safe.
Writes go through :mod:`backend.app.services`, which records each in the
audit log. What the screens show is worked out in :mod:`backend.app.enquiry`;
the words come from :mod:`backend.app.labels`.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import quote as url_quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app import enquiry, labels, services
from backend.app.design.breaker import breaker_svg
from backend.app.drawing.render import can_render, drawing_png, sheet_size
from backend.app.estimate import load_rules
from backend.app.highlight import segments
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow, Match, Project
from backend.app.report import estimate_docx
from backend.app.schemas import DocumentStatus, ReviewStatus
from backend.app.storage import FileType, UploadRejected

router = APIRouter()
BUSY = enquiry.BUSY
PENNY = Decimal("0.01")
PAGE_SIZE = 50  # rows per page in "Show all values" and Activity


def get_session(request: Request):
    sessions = request.app.state.sessions
    if sessions is None:
        raise HTTPException(503, "The database is not configured (DATABASE_URL).")
    with sessions() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def render(request: Request, template: str, /, status_code: int = 200, headers: dict[str, str] | None = None,
           **context: Any) -> HTMLResponse:
    """Render a template; ``template`` is positional-only so any context key (``name`` too) is allowed."""
    templates = request.app.state.templates
    base = {"app_name": request.app.state.settings.app_name, "kind_words": labels.KIND_WORDS,
            "field_label": labels.field_label, "display": labels.display, "source_words": labels.source_words,
            "method_words": labels.method_words, "money": services.money, "shown": enquiry.shown,
            "value_source": labels.value_source, "distinct_sources": enquiry.distinct_sources,
            "short_date": labels.short_date, "drawing_hint": drawing_hint(request.app.state.settings)}
    return templates.TemplateResponse(request, template, {**base, **context}, status_code=status_code,
                                      headers=headers)


def drawing_hint(settings: Any) -> str:
    """What happens to a drawing once uploaded, said before the upload."""
    if getattr(settings, "drawing_reading", "off") == "ocr":
        return ("A DXF drawing is read at once. Drawing PDFs and pictures are read by OCR, about 3 to 5 s "
                "per sheet, and every value read that way waits for your check.")
    return "A DXF drawing is read at once. Drawing PDFs and pictures are stored but not read: drawing reading is off."


def is_htmx(request: Request) -> bool:
    return bool(request.headers.get("HX-Request"))


def project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "No such enquiry.")
    return project


def document_or_404(session: Session, document_id: int) -> Document:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "No such file.")
    return doc


def enquiry_context(session: Session, project: Project, found: enquiry.Decisions | None = None) -> dict[str, Any]:
    """What every enquiry screen shows in its header: status, how it was read, and the count on the Check tab."""
    found = found or enquiry.decisions(project)
    estimate = services.latest_estimate(session, project.id)
    return {"project": project, "found": found, "estimate": estimate,
            "status": enquiry.status(session, project, estimate, found),
            "reading_line": enquiry.reading_line(project)}


# --- home, old addresses -------------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """The public home page. It needs no database: its numbers are the measured ones from the docs."""
    return render(request, "home.html", breaker=breaker_svg(), story_breaker=breaker_svg("story-"))


OLD_SCREENS = {"upload": "files", "analysis": "proof", "review": "check", "estimate": "quote", "audit": "activity"}


@router.api_route("/projects", methods=["GET", "POST"], include_in_schema=False)
@router.api_route("/projects/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def old_addresses(request: Request, rest: str = "") -> RedirectResponse:
    """``/projects/...`` moved to ``/enquiries/...``; old bookmarks and forms keep working (308 keeps the method)."""
    parts = rest.split("/") if rest else []
    if len(parts) == 2 and parts[1] in OLD_SCREENS:
        parts[1] = OLD_SCREENS[parts[1]]
    target = "/enquiries" + ("/" + "/".join(parts) if parts else "")
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(target, status_code=308)


# --- the list -------------------------------------------------------------------------------------------

@router.get("/enquiries", response_class=HTMLResponse)
def enquiries(request: Request, session: SessionDep, show: str = "open") -> HTMLResponse:
    archived = show == "archived"
    query = select(Project).where(Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None))
    projects = list(session.scalars(query.order_by(func.coalesce(Project.updated_at, Project.created_at).desc(),
                                                   Project.id.desc())))
    rows = []
    for p in projects:
        estimate = services.latest_estimate(session, p.id)
        rows.append({"project": p, "estimate": estimate, "status": enquiry.status(session, p, estimate)})
    archived_count = session.scalar(select(func.count(Project.id)).where(Project.archived_at.is_not(None))) or 0
    settings = request.app.state.settings
    return render(request, "enquiries.html", rows=rows, archived=archived, archived_count=archived_count,
                  max_mb=settings.max_upload_mb, nav="enquiries")


@router.get("/enquiries/new", response_class=HTMLResponse)
def new_enquiry_form(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return render(request, "enquiry_new.html", errors=[], name="", max_mb=settings.max_upload_mb,
                  max_pages=settings.max_pdf_pages, nav="new", watermark=breaker_svg("start-"))


async def _store_uploads(request: Request, session: Session, background: BackgroundTasks, project: Project,
                         files: list[UploadFile]) -> list[dict[str, str]]:
    """Check and store each file, queue its reading, and return the rejected ones with the reason."""
    settings, storage = request.app.state.settings, request.app.state.storage
    errors: list[dict[str, str]] = []
    for upload_file in files:
        if not upload_file.filename:  # an empty file input sends one nameless part
            continue
        data = await upload_file.read(settings.max_upload_bytes + 1)  # never read more than the limit
        try:
            doc = services.add_document(session, storage, settings, project, upload_file.filename, data)
        except UploadRejected as error:
            errors.append({"name": upload_file.filename.replace("\\", "/").split("/")[-1], "reason": str(error)})
            continue
        background.add_task(services.process_document, request.app.state.sessions, storage, doc.id, settings)
    return errors


@router.post("/enquiries")
async def create_enquiry(request: Request, session: SessionDep, background: BackgroundTasks,
                         name: Annotated[str, Form()] = "", reference: Annotated[str, Form()] = "",
                         note: Annotated[str, Form()] = "", next: Annotated[str, Form()] = "",  # noqa: A002
                         files: Annotated[list[UploadFile], File()] = []) -> Response:  # noqa: B006
    """One step: an optional name, the files and a typed note, in any mix. With files it goes on to read
    them and then to Check; a note alone opens Files, which asks for the files (V4)."""
    project = services.create_project(session, name, reference)
    services.add_note(session, project, note)
    errors = await _store_uploads(request, session, background, project, files)
    session.refresh(project)
    if errors:
        return render(request, "files.html", status_code=422, errors=errors, go=False,
                      **_files_context(request, session, project))
    if next == "review" and project.documents:  # the simple flow: Add files, then Review
        return RedirectResponse(f"/enquiries/{project.id}/review", status_code=303)
    return RedirectResponse(f"/enquiries/{project.id}/files" + ("?go=1" if project.documents else ""),
                            status_code=303)


@router.post("/enquiries/sample")
def create_sample(request: Request, session: SessionDep, background: BackgroundTasks) -> Response:
    """A fresh sample enquiry from the showcase files, read with recorded model runs where their hash matches."""
    settings, storage = request.app.state.settings, request.app.state.storage
    try:
        project, ids = services.create_sample(session, storage, settings)
    except FileNotFoundError as error:
        raise HTTPException(503, "The sample files are not installed with this copy of the app.") from error
    for doc_id in ids:
        background.add_task(services.process_document, request.app.state.sessions, storage, doc_id, settings)
    return RedirectResponse(f"/enquiries/{project.id}/files?go=1", status_code=303)


TILE_KEYS = ("quoted", "parts", "drawing", "agree", "cost", "missing")


def _summary_context(request: Request, session: Session, project: Project, tile: str | None) -> dict[str, Any]:
    """Everything the Summary shows: the six tiles, the open tile's detail and the buttons under them."""
    found = enquiry.decisions(project)
    context = enquiry_context(session, project, found)
    estimate = context["estimate"]
    items = _items(request, session, project)
    blockers = enquiry.quote_blockers(estimate) if estimate else []
    drawings = [d for d in project.documents if d.kind == "schematic"]
    return {**context, "tab": "summary", "items": items, "blockers": blockers, "drawings": drawings,
            "tiles": enquiry.summary_tiles(project, found, items, estimate, blockers),
            "open_tile": tile if tile in TILE_KEYS else "agree",
            "main_values": enquiry.main_values(found.groups),
            "proof_drawing": next((d for d in drawings if d.pages), None)}


@router.get("/enquiries/{project_id}", response_class=HTMLResponse)
def open_enquiry(request: Request, project_id: int, session: SessionDep, tile: str | None = None) -> Response:
    """The enquiry's Summary: six tiles, the open tile's detail below, and the Ask column (V4).

    ``?tile=<key>`` keeps the open tile in the address, so Back works. Without files it opens Files instead.
    """
    project = project_or_404(session, project_id)
    if not project.documents:
        return RedirectResponse(f"/enquiries/{project_id}/files", status_code=303)
    return render(request, "summary.html", **_summary_context(request, session, project, tile),
                  watermark=breaker_svg("summary-"))


@router.get("/enquiries/{project_id}/tiles/{key}", response_class=HTMLResponse)
def tile_detail(request: Request, project_id: int, key: str, session: SessionDep) -> Response:
    """One tile opened: the report block (tiles and detail) for HTMX, or the whole Summary without script."""
    if key not in TILE_KEYS:
        raise HTTPException(404, "There is no such tile.")
    project = project_or_404(session, project_id)
    if not is_htmx(request):
        return RedirectResponse(f"/enquiries/{project_id}?tile={key}", status_code=303)
    return render(request, "partials/summary_report.html", **_summary_context(request, session, project, key))


# --- rename, archive, delete (each asks first) ---------------------------------------------------------

def _confirm(request: Request, session: Session, project: Project, **context: Any) -> HTMLResponse:
    return render(request, "confirm.html", **enquiry_context(session, project), **context)


@router.get("/enquiries/{project_id}/rename", response_class=HTMLResponse)
def rename_form(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    return render(request, "rename.html", error=None, **enquiry_context(session, project))


@router.post("/enquiries/{project_id}/rename")
def rename(request: Request, project_id: int, session: SessionDep, name: Annotated[str, Form()] = "",
           reference: Annotated[str, Form()] = "") -> Response:
    project = project_or_404(session, project_id)
    try:
        services.rename_project(session, project, name, reference)
    except ValueError as error:
        return render(request, "rename.html", status_code=422, error=str(error),
                      **enquiry_context(session, project))
    return RedirectResponse("/enquiries", status_code=303)


@router.get("/enquiries/{project_id}/archive", response_class=HTMLResponse)
def archive_confirm(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    return _confirm(request, session, project, title="Archive this enquiry?", action=f"/enquiries/{project_id}/archive",
                    button="Archive", danger=False,
                    message="It leaves the list but nothing is deleted. You can bring it back from the archive.")


@router.post("/enquiries/{project_id}/archive")
def archive(request: Request, project_id: int, session: SessionDep, confirm: Annotated[str, Form()] = "") -> Response:
    project = project_or_404(session, project_id)
    if confirm != "yes":
        return archive_confirm(request, project_id, session)
    services.archive_project(session, project, True)
    return RedirectResponse("/enquiries", status_code=303)


@router.post("/enquiries/{project_id}/unarchive")
def unarchive(project_id: int, session: SessionDep) -> Response:
    services.archive_project(session, project_or_404(session, project_id), False)
    return RedirectResponse("/enquiries", status_code=303)


@router.get("/enquiries/{project_id}/delete", response_class=HTMLResponse)
def delete_confirm(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    files, values = len(project.documents), len(project.values)
    return _confirm(request, session, project, title="Delete this enquiry?", action=f"/enquiries/{project_id}/delete",
                    button="Delete for good", danger=True,
                    message=f"This removes its {files} file{'s' if files != 1 else ''}, {values} values, every "
                            "decision and its quotes. It cannot be undone. To hide it instead, archive it.")


@router.post("/enquiries/{project_id}/delete")
def delete(request: Request, project_id: int, session: SessionDep, confirm: Annotated[str, Form()] = "") -> Response:
    project = project_or_404(session, project_id)
    if confirm != "yes":  # nothing is deleted without the confirmation step
        return delete_confirm(request, project_id, session)
    services.delete_project(session, request.app.state.storage, project)
    return RedirectResponse("/enquiries", status_code=303)


# --- step 1: files --------------------------------------------------------------------------------------

PICTURES = ("png", "jpg")


def file_line(doc: Document) -> dict[str, Any]:
    """One plain progress line for a file: what it is, its size, and where its reading stands."""
    picture = doc.file_type in PICTURES
    if doc.kind == "schematic":
        what = "Drawing picture" if picture else "Drawing (CAD file)" if doc.file_type == "dxf" else "Drawing PDF"
    elif doc.kind:
        what = labels.KIND_WORDS.get(doc.kind, doc.kind)
    else:
        what = "Drawing picture" if picture else {"dxf": "Drawing (CAD file)", "docx": "Letter"}.get(doc.file_type, "PDF")
    size = None
    if doc.page_count:
        unit = "sheet" if doc.kind == "schematic" else "page"
        size = f"{doc.page_count} {unit}{'s' if doc.page_count != 1 else ''}"
    method = enquiry.document_method(doc)
    if doc.status == DocumentStatus.UPLOADED.value:
        state, tone = "waiting to be read", "busy"
    elif doc.status in BUSY:
        state = "reading text from the picture, about 5 s per sheet" if picture else "reading"
        tone = "busy"
    elif doc.status == DocumentStatus.DONE.value:
        state = {"ocr": "read from the picture (OCR)",
                 "rules+model": f"read with rules and {labels.model_run_words(doc.model_run or 'the model')}"
                 }.get(method or "", "read")
        tone = "ok"
    elif doc.status == DocumentStatus.NOT_READ.value:
        state, tone = "not read", "warn"
    else:
        state, tone = "could not be read", "error"
    return {"doc": doc, "what": what, "size": size, "state": state, "tone": tone,
            "note": doc.note if tone in ("warn", "error") else None}


def _files_context(request: Request, session: Session, project: Project) -> dict[str, Any]:
    settings = request.app.state.settings
    return {**enquiry_context(session, project), "lines": [file_line(d) for d in project.documents],
            "busy": any(d.status in BUSY for d in project.documents), "max_mb": settings.max_upload_mb,
            "max_pages": settings.max_pdf_pages, "tab": "files"}


def _read_any(project: Project) -> bool:
    return any(d.status == DocumentStatus.DONE.value for d in project.documents)


@router.get("/enquiries/{project_id}/files", response_class=HTMLResponse)
def files_page(request: Request, project_id: int, session: SessionDep, go: int = 0) -> Response:
    project = project_or_404(session, project_id)
    context = _files_context(request, session, project)
    if go and not context["busy"] and _read_any(project):  # reading already finished: straight on to Check
        return RedirectResponse(f"/enquiries/{project_id}/check", status_code=303)
    return render(request, "files.html", errors=[], go=bool(go), **context)


@router.get("/enquiries/{project_id}/documents", response_class=HTMLResponse)
def file_lines(request: Request, project_id: int, session: SessionDep, go: int = 0) -> Response:
    """The file lines; polled by HTMX every second while a file is read. With ``go`` it moves on to Check."""
    project = project_or_404(session, project_id)
    context = _files_context(request, session, project)
    if go and not context["busy"] and _read_any(project) and is_htmx(request):
        return Response(status_code=204, headers={"HX-Redirect": f"/enquiries/{project_id}/check"})
    return render(request, "partials/file_lines.html", errors=[], go=bool(go), **context)


@router.post("/enquiries/{project_id}/documents", response_class=HTMLResponse)
async def upload(request: Request, project_id: int, session: SessionDep, background: BackgroundTasks,
                 files: Annotated[list[UploadFile], File()]) -> Response:
    project = project_or_404(session, project_id)
    errors = await _store_uploads(request, session, background, project, files)
    session.refresh(project)
    context = _files_context(request, session, project)
    if is_htmx(request):
        return render(request, "partials/file_lines.html", errors=errors, go=not errors, **context)
    if errors:
        return render(request, "files.html", status_code=422, errors=errors, go=False, **context)
    return RedirectResponse(f"/enquiries/{project_id}/files?go=1", status_code=303)


@router.get("/documents/{document_id}/delete", response_class=HTMLResponse)
def delete_document_confirm(request: Request, document_id: int, session: SessionDep) -> HTMLResponse:
    doc = document_or_404(session, document_id)
    values = session.scalar(select(func.count(ExtractedValueRow.id)).where(
        ExtractedValueRow.document_id == doc.id)) or 0
    return _confirm(request, session, doc.project, title=f"Delete {doc.original_name}?",
                    action=f"/documents/{doc.id}/delete", button="Delete the file", danger=True,
                    message=f"This removes the file, the {values} values read from it and the decisions made on "
                            "them. The quote is rebuilt without them. It cannot be undone.")


@router.post("/documents/{document_id}/delete")
def delete_document(request: Request, document_id: int, session: SessionDep,
                    confirm: Annotated[str, Form()] = "") -> Response:
    doc = document_or_404(session, document_id)
    if confirm != "yes":
        return delete_document_confirm(request, document_id, session)
    project_id = doc.project_id
    services.delete_document(session, request.app.state.storage, doc)
    services.refresh_quote(session, project_id, request.app.state.settings)
    return RedirectResponse(f"/enquiries/{project_id}/files", status_code=303)


@router.get("/documents/{document_id}/read-again", response_class=HTMLResponse)
def read_again_confirm(request: Request, document_id: int, session: SessionDep) -> HTMLResponse:
    doc = document_or_404(session, document_id)
    decided = session.scalar(select(func.count(ExtractedValueRow.id)).where(
        ExtractedValueRow.document_id == doc.id, ExtractedValueRow.review_status != "extracted")) or 0
    return _confirm(request, session, doc.project, title=f"Read {doc.original_name} again?",
                    action=f"/documents/{doc.id}/read-again", button="Read again", danger=False,
                    message="The file is read again with today's settings and its values are replaced."
                            + (f" Your {decided} decision{'s' if decided != 1 else ''} on its values will be removed; "
                               "they stay listed in Activity." if decided else ""))


@router.post("/documents/{document_id}/read-again")
def read_again(request: Request, document_id: int, session: SessionDep, background: BackgroundTasks,
               confirm: Annotated[str, Form()] = "") -> Response:
    doc = document_or_404(session, document_id)
    if confirm != "yes":
        return read_again_confirm(request, document_id, session)
    project_id = doc.project_id
    services.reset_document(session, doc)
    background.add_task(services.process_document, request.app.state.sessions, request.app.state.storage,
                        document_id, request.app.state.settings)
    return RedirectResponse(f"/enquiries/{project_id}/files", status_code=303)


# --- step 2: check --------------------------------------------------------------------------------------

def _items(request: Request, session: Session, project: Project) -> list[enquiry.Item]:
    settings = request.app.state.settings
    return enquiry.preview_items(project, services.catalogue_items(session), load_rules(settings.estimate_rules),
                                 enquiry.approved_substitutes(session, project.id))


# The buttons under the tabs on Check: (key, label, count from the Check context or None).
# Each view is the template partials/views/<key>.html; adding a view (Stock, Ask) is one line here.
VIEWS: list[tuple[str, str, Callable[[dict[str, Any]], int | None]]] = [
    ("decisions", "To check", lambda c: c["found"].needs),  # plain names (V4): keys stay for old links
    ("items", "Parts list", lambda c: len(c["items"])),
    ("report", "Report", lambda c: None),
]
DEFAULT_VIEW = VIEWS[0][0]


def _check_context(request: Request, session: Session, project: Project, open_reason: str | None = None,
                   error: str | None = None, view: str | None = None) -> dict[str, Any]:
    found = enquiry.decisions(project)
    items = _items(request, session, project)
    context = {**enquiry_context(session, project, found), "items": items, "reasons": enquiry.REASONS,
               "open_reason": open_reason if open_reason in found.reasons else None, "error": error,
               "flags": enquiry.instruction_flags(project), "tab": "check",
               "view": view if view in {k for k, _, _ in VIEWS} else DEFAULT_VIEW}
    context["views"] = [{"key": k, "label": label, "count": count(context)} for k, label, count in VIEWS]
    if context["view"] == "report":
        estimate = context["estimate"]
        context["can_export"] = found.approved > 0
        context["out_of_date"] = enquiry.quote_out_of_date(session, project.id, estimate)
    return context


@router.get("/enquiries/{project_id}/check", response_class=HTMLResponse)
def check_page(request: Request, project_id: int, session: SessionDep, open: str | None = None,
               error: str | None = None, view: str | None = None) -> HTMLResponse:
    """Check, with one view open (``?view=decisions|items|report``). A bar button swaps only the Check block."""
    project = project_or_404(session, project_id)
    context = _check_context(request, session, project, open, error, view)
    if is_htmx(request) and request.headers.get("HX-Target") == "check-body":
        return render(request, "partials/check_body.html", **context)
    return render(request, "check.html", **context)


def _after_decision(request: Request, session: Session, project_id: int, open_reason: str | None = None,
                    error: str | None = None, anchor: str | None = None, back: str = "") -> Response:
    """After a decision on Check: rebuild the quote, then the refreshed Check block (HTMX) or a redirect.

    A decision taken on the Summary (``back="summary"``) returns there with the agreement tile open;
    an error is still shown on Check, where the whole conflict can be read.
    """
    if error is None:
        services.refresh_quote(session, project_id, request.app.state.settings)
        if back == "summary" and not is_htmx(request):
            return RedirectResponse(f"/enquiries/{project_id}?tile=agree", status_code=303)
    if is_htmx(request):
        session.expire_all()
        project = project_or_404(session, project_id)
        return render(request, "partials/check_body.html", oob=True,
                      **_check_context(request, session, project, open_reason, error))
    target = f"/enquiries/{project_id}/check"
    params = "&".join(p for p in (f"open={open_reason}" if open_reason else "",
                                  f"error={url_quote(error)}" if error else "") if p)
    return RedirectResponse(target + (f"?{params}" if params else "") + (f"#{anchor}" if anchor and not error else ""),
                            status_code=303)


@router.get("/enquiries/{project_id}/check/group/{reason}", response_class=HTMLResponse)
def check_group(request: Request, project_id: int, reason: str, session: SessionDep) -> HTMLResponse:
    """The values of one "needs your decision" group, loaded when the engineer opens it."""
    project = project_or_404(session, project_id)
    found = enquiry.decisions(project)
    if reason not in found.reasons:
        raise HTTPException(404, "Nothing left to review in this group.")
    return render(request, "partials/value_rows.html", project=project, rows=found.reasons[reason],
                  open_reason=reason, actions=True)


VALUE_FILTERS = {"all": "All", "open": "Not decided", "approved": "Approved", "rejected": "Rejected"}


@router.get("/enquiries/{project_id}/check/values", response_class=HTMLResponse)
def check_values(request: Request, project_id: int, session: SessionDep, show: str = "all", doc: int | None = None,
                 page: int = 1) -> HTMLResponse:
    """ "Show all values": one filtered page of plain rows. No edit form is rendered here."""
    project = project_or_404(session, project_id)
    show = show if show in VALUE_FILTERS else "all"
    wanted = {"open": ("extracted",), "approved": enquiry.DONE, "rejected": ("rejected",)}.get(show)
    rows = [v for v in sorted(project.values, key=lambda v: (enquiry.field_sort_key(v.field), v.id))
            if (wanted is None or v.review_status in wanted) and (doc is None or v.document_id == doc)]
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(max(1, page), pages)
    extra = {} if is_htmx(request) else {**enquiry_context(session, project), "tab": "check"}
    return render(request, "partials/all_values.html" if is_htmx(request) else "values.html", total=len(rows),
                  rows=rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE], show=show, doc=doc, page=page, pages=pages,
                  filters=VALUE_FILTERS, **{"project": project, **extra})


@router.get("/enquiries/{project_id}/check/accept-all", response_class=HTMLResponse)
def accept_all_confirm(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    """The confirmation step of "Accept all": it shows how many values would be approved, and which kinds never are."""
    project = project_or_404(session, project_id)
    found = enquiry.decisions(project)
    template = "partials/accept_confirm.html" if is_htmx(request) else "accept_confirm.html"
    return render(request, template, **enquiry_context(session, project, found), tab="check")


@router.post("/enquiries/{project_id}/check/accept-all")
def accept_all(request: Request, project_id: int, session: SessionDep, confirm: Annotated[str, Form()] = "") -> Response:
    project = project_or_404(session, project_id)
    if confirm != "yes":
        return accept_all_confirm(request, project_id, session)
    services.accept_all(session, project)
    return _after_decision(request, session, project_id)


@router.post("/enquiries/{project_id}/fields/use")
def use_value(request: Request, project_id: int, session: SessionDep, field: Annotated[str, Form()],
              value_id: Annotated[int, Form()], back: Annotated[str, Form()] = "") -> Response:
    """ "Use this" on a conflict card: keep this source's value, reject the others."""
    project_or_404(session, project_id)
    error = None
    try:
        services.resolve_field(session, project_id, field, keep_value_id=value_id)
    except services.ReviewError as e:
        error = str(e)
    return _after_decision(request, session, project_id, error=error, back=back)


@router.post("/enquiries/{project_id}/fields/type")
def type_value(request: Request, project_id: int, session: SessionDep, field: Annotated[str, Form()],
               value: Annotated[str, Form()] = "", unit: Annotated[str, Form()] = "",
               reason: Annotated[str, Form()] = "") -> Response:
    """ "Type another value" on a conflict card: the typed value is approved, the sources' values rejected."""
    project_or_404(session, project_id)
    error = None
    try:
        services.resolve_field(session, project_id, field, typed_value=value, typed_unit=unit, reason=reason)
    except services.ReviewError as e:
        error = str(e)
    return _after_decision(request, session, project_id, error=error)


# --- the proof panel -------------------------------------------------------------------------------------

def _anchor(v: ExtractedValueRow) -> str | None:
    """Table cells are found inside their way's row."""
    if v.rule and v.rule.startswith("spec.table.") and (m := re.match(r"^way\.(\w+)\.", v.field)):
        return m.group(1)
    return None


def proof_of(v: ExtractedValueRow, context_lines: int = 3) -> dict[str, Any]:
    """Where a value was read: a picture of the drawing with its box, or its sentence with a few lines around it."""
    doc = v.document
    out: dict[str, Any] = {"image": None, "before": "", "mark": None, "after": ""}
    if v.regions and can_render(FileType(doc.file_type)):
        out["image"] = f"/values/{v.id}/drawing.png"
    page = next((p for p in doc.pages if p.number == v.page), None)
    if page is None or not v.source_text:
        return out
    segs = segments(page.text, [(v.id, v.source_text, _anchor(v))])
    index = next((i for i, s in enumerate(segs) if s.marked), None)
    if index is None:
        return out
    before = "".join(s.text for s in segs[:index]).split("\n")
    after = "".join(s.text for s in segs[index + 1:]).split("\n")
    out.update(before="\n".join(before[-(context_lines + 1):]), mark=segs[index].text,
               after="\n".join(after[:context_lines + 1]))
    return out


def _panel(request: Request, session: Session, v: ExtractedValueRow, error: str | None = None,
           open_reason: str | None = None, status_code: int = 200) -> HTMLResponse:
    others = [o for o in session.scalars(select(ExtractedValueRow).where(
        ExtractedValueRow.project_id == v.project_id, ExtractedValueRow.field == v.field)) if o.id != v.id]
    headers = {"HX-Retarget": "#panel", "HX-Reswap": "innerHTML"} if error else None
    return render(request, "partials/value_panel.html", status_code=status_code, headers=headers, v=v, others=others,
                  proof=proof_of(v), error=error, open_reason=open_reason,
                  confidence_words=labels.CONFIDENCE_WORDS)


@router.get("/values/{value_id}/panel", response_class=HTMLResponse)
def value_panel(request: Request, value_id: int, session: SessionDep, open: str | None = None) -> HTMLResponse:
    """The proof and the decision form of one value, loaded when the engineer clicks it."""
    v = session.get(ExtractedValueRow, value_id)
    if v is None:
        raise HTTPException(404, "No such value.")
    if not is_htmx(request):  # opened as a page (no script): the same panel on its own screen
        return render(request, "value.html", v=v, panel_error=None, open_reason=open, proof=proof_of(v),
                      others=[o for o in v.project.values if o.field == v.field and o.id != v.id],
                      confidence_words=labels.CONFIDENCE_WORDS, error=None, tab="check",
                      **enquiry_context(session, v.project))
    return _panel(request, session, v, open_reason=open)


@router.get("/values/{value_id}/drawing.png")
def value_drawing(request: Request, value_id: int, session: SessionDep, full: int = 0) -> Response:
    """The drawing sheet a value was read from, with its box outlined (cropped around it unless ``full``)."""
    v = session.get(ExtractedValueRow, value_id)
    if v is None or not v.regions:
        raise HTTPException(404, "This value has no box on a drawing.")
    doc = v.document
    file_type = FileType(doc.file_type)
    if not can_render(file_type):
        raise HTTPException(404, "This file has no picture to show.")
    region = v.regions[0]
    sheet = v.page if file_type == FileType.PDF else 1
    try:
        png = drawing_png(file_type, request.app.state.storage.read(doc.storage_key), sheet or 1,
                          [region["bbox"]], crop=not full)
    except (OSError, ValueError) as error:
        raise HTTPException(404, "The drawing could not be shown.") from error
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/enquiries/{project_id}/items/{key}/panel", response_class=HTMLResponse)
def item_panel(request: Request, project_id: int, key: str, session: SessionDep) -> HTMLResponse:
    """What an item rests on: the values of each field it needs, each opening its own proof."""
    project = project_or_404(session, project_id)
    item = next((i for i in _items(request, session, project) if i.key == key), None)
    if item is None:
        raise HTTPException(404, "No such item.")
    groups = enquiry.review_groups(project)
    basis = [{"field": f, "label": labels.field_label(f), "values": groups[f]["values"] if f in groups else [],
              "conflict": groups[f]["conflict"] if f in groups else False} for f in dict.fromkeys(item.basis)]
    template = "partials/item_panel.html" if is_htmx(request) else "item.html"
    extra = {} if is_htmx(request) else {**enquiry_context(session, project), "tab": "check"}
    return render(request, template, item=item, basis=basis, **{"project": project, **extra})


@router.post("/values/{value_id}/{action}")
def review_value(request: Request, value_id: int, action: str, session: SessionDep,
                 value: Annotated[str, Form()] = "", unit: Annotated[str, Form()] = "",
                 reason: Annotated[str, Form()] = "", open: Annotated[str, Form()] = "") -> Response:
    row = session.get(ExtractedValueRow, value_id)
    if row is None or action not in ("approve", "edit", "reject"):
        raise HTTPException(404)
    project_id, field = row.project_id, row.field
    try:
        services.review_value(session, value_id, action, value, unit, reason)
    except services.ReviewError as e:
        if is_htmx(request):
            return _panel(request, session, row, error=str(e), open_reason=open or None)
        return _after_decision(request, session, project_id, open or None, error=str(e))
    return _after_decision(request, session, project_id, open or None, anchor=f"f-{field}")


# --- step 3: quote --------------------------------------------------------------------------------------

@router.post("/enquiries/{project_id}/quote")
def rebuild_quote(request: Request, project_id: int, session: SessionDep) -> Response:
    project_or_404(session, project_id)
    services.build_estimate(session, project_id, request.app.state.settings)
    return RedirectResponse(f"/enquiries/{project_id}/quote", status_code=303)


@router.get("/enquiries/{project_id}/quote", response_class=HTMLResponse)
def quote_page(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    project = project_or_404(session, project_id)
    context = enquiry_context(session, project)
    est = context["estimate"]
    return render(request, "quote.html", **context, tab="quote",
                  blockers=enquiry.quote_blockers(est) if est else [],
                  out_of_date=enquiry.quote_out_of_date(session, project_id, est),
                  line_label=labels.line_label)


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
    return RedirectResponse(f"/enquiries/{m.project_id}/quote", status_code=303)


def _export_docx(request: Request, session: Session, project: Project, est: Estimate) -> Response:
    ids = {i for ln in est.lines for i in ln.value_ids}
    values = {v.id: v for v in session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.id.in_(ids)))}
    data = estimate_docx(project, est, values, datetime.now(UTC), enquiry.reading_line(project))
    services.audit(session, "export", "estimate", est.id, project.id, format="docx", bytes=len(data),
                   sha256=hashlib.sha256(data).hexdigest())
    session.commit()
    name = f"quote-{project.id}-{est.id}.docx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/enquiries/{project_id}/quote/report.docx")
def export_latest_docx(request: Request, project_id: int, session: SessionDep) -> Response:
    """The report of the current quote. The quote is rebuilt first if anything changed since it was built.

    Refused (409) while nothing is approved: a report of an empty quote helps no one.
    """
    project = project_or_404(session, project_id)
    if not enquiry.decisions(project).approved:
        raise HTTPException(409, "Approve at least one value to export the report.")
    est = services.latest_estimate(session, project_id)
    if est is None or enquiry.quote_out_of_date(session, project_id, est):
        est = services.build_estimate(session, project_id, request.app.state.settings)
    return _export_docx(request, session, project, est)


@router.get("/enquiries/{project_id}/estimates/{estimate_id}/report.docx")
def export_docx(request: Request, project_id: int, estimate_id: int, session: SessionDep) -> Response:
    project = project_or_404(session, project_id)
    est = session.get(Estimate, estimate_id)
    if est is None or est.project_id != project_id:
        raise HTTPException(404)
    return _export_docx(request, session, project, est)


# --- the simple flow: Review, one card at a time, then the draft quote -----------------------------------

def _crop(request: Request, v: ExtractedValueRow, sizes: dict[tuple[int, int], Any] | None = None
          ) -> dict[str, Any] | None:
    """The drawing around a value's box, as an SVG view of the sheet picture: the box stays a see-through outline.

    ``sizes`` keeps each sheet's size for one request, so a card with many boxes reads each file once.
    """
    doc = v.document
    if not v.regions or not can_render(FileType(doc.file_type)):
        return None
    sheet = (v.page or 1) if doc.file_type == "pdf" else 1
    sizes = {} if sizes is None else sizes
    if (doc.id, sheet) not in sizes:
        try:
            sizes[(doc.id, sheet)] = sheet_size(FileType(doc.file_type),
                                                request.app.state.storage.read(doc.storage_key), sheet)
        except (OSError, ValueError):
            sizes[(doc.id, sheet)] = None
    if sizes[(doc.id, sheet)] is None:
        return None
    width, height = sizes[(doc.id, sheet)]
    x0, y0, x1, y1 = v.regions[0]["bbox"]
    margin = max(x1 - x0, y1 - y0, 60) * 1.5
    vx, vy = max(0.0, x0 - margin), max(0.0, y0 - margin)
    vw, vh = min(width, x1 + margin) - vx, min(height, y1 + margin) - vy
    return {"src": f"/documents/{doc.id}/sheets/{sheet}.png", "width": width, "height": height,
            "view": f"{vx:g} {vy:g} {vw:g} {vh:g}", "kind": box_kind(v), "label": symbol_label(v), "font": vw / 22,
            "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "full": f"/enquiries/{v.project_id}/proof?doc={doc.id}"
            + (f"&page={v.page}" if v.page else "")}


def _value_item(request: Request, v: ExtractedValueRow, sizes: dict) -> dict[str, Any]:
    """One value on a group card: its label, value, where it was read, and its box or its marked text."""
    value, unit = enquiry.shown(v)
    return {"v": v, "label": labels.field_label(v.field), "value": labels.display(value, unit),
            "source": labels.value_source(v), "crop": _crop(request, v, sizes), "proof": proof_of(v, context_lines=1),
            "kind": box_kind(v)}


def _review_context(request: Request, session: Session, project: Project, error: str | None = None,
                    one: bool = False) -> dict[str, Any]:
    """The Review page: groups checked out of all groups, and the first group still waiting, as one card.

    Order: the agreeing values (one button for all of them), each real conflict, then one card per file and
    page with every value ticked (:func:`backend.app.enquiry.review_plan`).
    """
    found = enquiry.decisions(project)
    plan = enquiry.review_plan(project)
    later = enquiry.left_for_later(session, project)
    waiting = [g for g in plan if not g.done(later)]
    context = {**enquiry_context(session, project, found), "busy": any(d.status in BUSY for d in project.documents),
               "total": len(plan), "done": len(plan) - len(waiting), "card": None, "error": error,
               "later": len(later), "box_kinds": BOX_KINDS, "one": one, "agree_counts": None}
    agreeing = next((g for g in plan if g.kind == "agreeing"), None)
    if agreeing is not None:  # "N approved, N changed, N still to check": every agreeing value is in one of them
        listed = [v for v in agreeing.values if v.review_status != ReviewStatus.REJECTED.value]
        context["agree_counts"] = {
            "approved": sum(v.review_status == ReviewStatus.APPROVED.value for v in listed),
            "changed": sum(v.review_status == ReviewStatus.EDITED.value for v in listed),
            "still": sum(v.review_status == ReviewStatus.EXTRACTED.value for v in listed)}
    if not waiting:
        return context
    group = waiting[0]
    sizes: dict = {}
    if group.kind == "agreeing" and one:  # "Check one by one": the first waiting value on its own card
        v = group.pending(later)[0]
        context["card"] = {"kind": "one", "item": _value_item(request, v, sizes)}
    elif group.kind == "agreeing":
        waiting_ids = {v.id for v in group.pending(later)}
        items = [_value_item(request, v, sizes) | {"crop": None, "pending": v.id in waiting_ids}
                 for v in group.values if v.review_status != ReviewStatus.REJECTED.value]
        context["card"] = {"kind": "agreeing", "key": group.key, "items": items, "ticked": len(waiting_ids)}
    elif group.kind == "conflict":
        g = found.groups[group.field]
        sides = g["sides"]
        first = sides[0][0] if sides else group.pending(later)[0]
        proof_value = next((v for v in (sides[0] if sides else [first]) if v.regions), first)
        between = found.between_files.get(group.field)
        others = [labels.display(*enquiry.shown(side[0])) for side in sides[1:]]
        context["card"] = {"kind": "conflict", "group": g, "first": first, "can_approve": first.value is not None,
                           "proof": proof_of(proof_value), "proof_value": proof_value,
                           "crop": _crop(request, proof_value, sizes), "kind_box": box_kind(proof_value),
                           "disagree": (between.message + "." if between else
                                        f"Another reading of the same file says {', '.join(others)}." if others
                                        else None)}
    else:
        doc = group.document
        where = f"{'sheet' if doc.kind == 'schematic' else 'page'} {group.page or 1}"
        context["card"] = {"kind": "page", "key": group.key, "document": doc, "page": group.page or 1, "where": where,
                           "items": [_value_item(request, v, sizes) for v in group.pending(later)]}
    return context


def _review_response(request: Request, session: Session, project_id: int, error: str | None = None,
                     one: bool = False) -> Response:
    if is_htmx(request):
        session.expire_all()
        return render(request, "partials/review_body.html",
                      **_review_context(request, session, project_or_404(session, project_id), error, one))
    params = "&".join(p for p in ("one=1" if one else "", f"error={url_quote(error)}" if error else "") if p)
    target = f"/enquiries/{project_id}/review" + (f"?{params}" if params else "")
    return RedirectResponse(target, status_code=303)


@router.get("/enquiries/{project_id}/review", response_class=HTMLResponse)
def review_page(request: Request, project_id: int, session: SessionDep, error: str | None = None,
                one: int = 0) -> HTMLResponse:
    """One card per group that needs checking, with its proof; reading first while files are read.

    ``?one=1`` ("Check one by one") shows the agreeing values one at a time instead of as one list.
    """
    project = project_or_404(session, project_id)
    context = _review_context(request, session, project, error, bool(one))
    if is_htmx(request) and request.headers.get("HX-Target") == "review-body":
        return render(request, "partials/review_body.html", **context)
    return render(request, "review.html", **context)


@router.post("/enquiries/{project_id}/review/approve")
def review_approve(request: Request, project_id: int, session: SessionDep, field: Annotated[str, Form()],
                   value_id: Annotated[int, Form()]) -> Response:
    """Approve on a card: this value, and every source giving the same value; a different reading is set aside."""
    project_or_404(session, project_id)
    error = None
    try:
        services.resolve_field(session, project_id, field, keep_value_id=value_id)
        services.refresh_quote(session, project_id, request.app.state.settings)
    except services.ReviewError as e:
        error = str(e)
    return _review_response(request, session, project_id, error)


@router.post("/enquiries/{project_id}/review/change")
def review_change(request: Request, project_id: int, session: SessionDep, field: Annotated[str, Form()],
                  value: Annotated[str, Form()] = "", unit: Annotated[str, Form()] = "") -> Response:
    """Change on a card: the typed value is approved for this item; the values read from the files are set aside."""
    project_or_404(session, project_id)
    error = None
    try:
        services.resolve_field(session, project_id, field, typed_value=value, typed_unit=unit)
        services.refresh_quote(session, project_id, request.app.state.settings)
    except services.ReviewError as e:
        error = str(e)
    return _review_response(request, session, project_id, error)


def _group(session: Session, project_id: int, key: str) -> tuple[Project, enquiry.ReviewGroup | None, set[int]]:
    project = project_or_404(session, project_id)
    group = next((g for g in enquiry.review_plan(project) if g.key == key), None)
    return project, group, enquiry.left_for_later(session, project)


@router.post("/enquiries/{project_id}/review/agreeing")
def review_agreeing(request: Request, project_id: int, session: SessionDep,
                    value_id: Annotated[list[int], Form()] = [],  # noqa: B006
                    in_group: Annotated[list[int], Form()] = []) -> Response:  # noqa: B006
    """ "Yes, these are right (N ticked)": exactly the ticked agreeing values that still wait, one approval and one
    audit entry each. An id that is not an agreeing value waiting for a decision is never approved. A value the
    card listed but left un-ticked stays to check (one audit entry), unapproved and never priced."""
    project, group, later = _group(session, project_id, "agreeing")
    allowed = {v.id for v in group.pending(later)} if group else set()
    ticked = set(value_id) & allowed
    for i in sorted(ticked):
        services.review_value(session, i, "approve", reason="approved with the agreeing values")
    for i in sorted((set(in_group) & allowed) - ticked):
        services.audit(session, "review_later", "extracted_value", i, project.id,
                       reason="left un-ticked on the agreeing values card")
    session.commit()
    services.refresh_quote(session, project_id, request.app.state.settings)
    return _review_response(request, session, project_id)


def _waiting_value(session: Session, project_id: int, value_id: int) -> ExtractedValueRow | None:
    v = session.get(ExtractedValueRow, value_id)
    ok = v is not None and v.project_id == project_id and v.review_status == ReviewStatus.EXTRACTED.value
    return v if ok else None


@router.post("/enquiries/{project_id}/review/one/approve")
def review_one_approve(request: Request, project_id: int, session: SessionDep, value_id: Annotated[int, Form()],
                       one: Annotated[int, Form()] = 0) -> Response:
    """Approve one value ("Check one by one"): its own approval and audit entry."""
    project_or_404(session, project_id)
    error = None
    if _waiting_value(session, project_id, value_id) is None:
        error = "That value was already decided; here is the next one."
    else:
        try:
            services.review_value(session, value_id, "approve", reason="approved on its own Review card")
            services.refresh_quote(session, project_id, request.app.state.settings)
        except services.ReviewError as e:
            error = str(e)
    return _review_response(request, session, project_id, error, bool(one))


@router.post("/enquiries/{project_id}/review/one/change")
def review_one_change(request: Request, project_id: int, session: SessionDep, value_id: Annotated[int, Form()],
                      value: Annotated[str, Form()] = "", unit: Annotated[str, Form()] = "",
                      one: Annotated[int, Form()] = 0) -> Response:
    """Change one value: the engineer's value is stored as approved ("changed by engineer"); the value read from
    the file is kept on the record; its own review row and audit entry."""
    project_or_404(session, project_id)
    error = None
    if _waiting_value(session, project_id, value_id) is None:
        error = "That value was already decided."
    else:
        try:
            services.review_value(session, value_id, "edit", value, unit, reason="changed by engineer on Review")
            services.refresh_quote(session, project_id, request.app.state.settings)
        except services.ReviewError as e:
            error = str(e)
    return _review_response(request, session, project_id, error, bool(one))


@router.post("/enquiries/{project_id}/review/group")
def review_page_group(request: Request, project_id: int, session: SessionDep, key: Annotated[str, Form()],
                      in_group: Annotated[list[int], Form()] = [],  # noqa: B006
                      value_id: Annotated[list[int], Form()] = []) -> Response:  # noqa: B006
    """ "Approve N ticked" on a file-and-page card: each ticked value is approved on its own; each value the card
    showed but left un-ticked is left for later (one audit entry), stays unapproved and is never priced."""
    project, group, later = _group(session, project_id, key)
    if group is None or group.kind != "page":
        return _review_response(request, session, project_id, "This card has changed; here is the next one.")
    waiting = {v.id for v in group.pending(later)}
    ticked = set(value_id) & waiting
    for i in sorted(ticked):
        services.review_value(session, i, "approve", reason="approved on its Review card")
    for i in sorted((set(in_group) & waiting) - ticked):
        services.audit(session, "review_later", "extracted_value", i, project.id,
                       reason="left for later on its Review card")
    session.commit()
    services.refresh_quote(session, project_id, request.app.state.settings)
    return _review_response(request, session, project_id)


@router.post("/enquiries/{project_id}/review/quote")
def review_make_quote(request: Request, project_id: int, session: SessionDep) -> Response:
    """Make quote: build it from approved values only (the cost rules are unchanged), then show it."""
    project_or_404(session, project_id)
    services.build_estimate(session, project_id, request.app.state.settings)
    return RedirectResponse(f"/enquiries/{project_id}/draft-quote", status_code=303)


@router.get("/enquiries/{project_id}/draft-quote", response_class=HTMLResponse)
def draft_quote(request: Request, project_id: int, session: SessionDep) -> HTMLResponse:
    """The short quote: part, description, quantity and line total, and the draft total. The rest is in the workings."""
    project = project_or_404(session, project_id)
    context = enquiry_context(session, project)
    est = context["estimate"]
    lines = []
    if est is not None:
        for ln in est.lines:
            total = (ln.materials + ln.labour_hours * est.labour_rate).quantize(PENNY)  # before the margin
            lines.append({"code": ln.code, "description": ln.description, "qty": ln.quantity.normalize(),
                          "unit": ln.unit, "total": total})
    left_out = (len(est.unmatched) + len(est.pending)) if est is not None else 0
    return render(request, "draft_quote.html", **context, lines=lines, left_out=left_out)


# --- details: proof viewer and activity ----------------------------------------------------------------

@router.get("/enquiries/{project_id}/proof", response_class=HTMLResponse)
def proof_viewer(request: Request, project_id: int, session: SessionDep, doc: int | None = None,
                 page: int | None = None) -> HTMLResponse:
    """A file's text page by page, with the source of every value highlighted (the old Analysis screen)."""
    project = project_or_404(session, project_id)
    readable = [d for d in project.documents if d.pages]
    current = next((d for d in readable if d.id == doc), None) or (readable[0] if readable else None)
    pages, page_no, segs, values = [], None, [], []
    if current is not None:
        pages = current.pages
        page_no = page if page in {p.number for p in pages} else pages[0].number
        text = next(p.text for p in pages if p.number == page_no)
        values = sorted((v for v in project.values if v.document_id == current.id and v.page == page_no),
                        key=lambda v: enquiry.field_sort_key(v.field))
        flagged = [f["text"] for f in enquiry.instruction_flags(project, current.id) if f["page"] == page_no]
        segs = segments(text, [(v.id, v.source_text or "", _anchor(v)) for v in values]
                        + [(-1 - i, t, None) for i, t in enumerate(flagged)])
    flags = enquiry.instruction_flags(project, current.id) if current is not None else []
    sheet = _sheet_boxes(request, current, page_no, values) if current is not None else None
    return render(request, "proof.html", **enquiry_context(session, project), current=current, pages=pages,
                  page_no=page_no, segments=segs, values=values, flags=flags, tab="details", sheet=sheet)


# How a box is coloured: by how its value was read (the one-line legend under every drawing).
BOX_KINDS = {"rules": "Read by rules", "picture": "Read from a picture, needs review", "symbol": "Symbol found"}
SYMBOL_WORDS = {"acb": "ACB", "mccb": "MCCB", "mcb": "MCB", "switch_disconnector": "Switch-disconnector"}


def box_kind(v: ExtractedValueRow) -> str:
    """rules (text read from a file), picture (OCR or a vision model: always reviewed) or symbol (the detector)."""
    if v.method == "detector":
        return "symbol"
    return "picture" if v.method in ("ocr", "vision") else "rules"


def symbol_label(v: ExtractedValueRow) -> str | None:
    """The short label on a symbol box, for example "MCCB 0.82": the device and the detector's score."""
    if v.method != "detector":
        return None
    score = re.search(r"score (\d+\.\d+)", v.derivation or "")
    name = SYMBOL_WORDS.get(str(v.value), str(v.value))
    return f"{name} {score.group(1)}" if score else name


def _sheet_boxes(request: Request, doc: Document, sheet: int | None, values: list[ExtractedValueRow]
                 ) -> dict[str, Any] | None:
    """A drawing sheet's picture and one box per value read on it with a region (Stage 4 Part D).

    Boxes are in the answer key's coordinates, so the SVG over the picture uses the sheet's size as its
    viewBox. Only drawing pictures (PDF, PNG, JPG) have one; a DXF or a text document has none.
    """
    if doc.kind != "schematic" or sheet is None or not can_render(FileType(doc.file_type)):
        return None
    try:
        width, height = sheet_size(FileType(doc.file_type), request.app.state.storage.read(doc.storage_key), sheet)
    except (OSError, ValueError):
        return None
    boxes = []
    for v in values:
        region = next((r for r in v.regions or [] if r.get("sheet") in (None, sheet)), None)
        if region is None:
            continue
        x0, y0, x1, y1 = region["bbox"]
        value, unit = enquiry.shown(v)
        title = f"{labels.field_label(v.field)}: {labels.display(value, unit)}"
        if v.source_text:
            title += f" (read: {v.source_text})"
        boxes.append({"id": v.id, "tone": box_kind(v), "label": symbol_label(v), "x": x0, "y": y0, "w": x1 - x0,
                      "h": y1 - y0, "title": title})
    return {"src": f"/documents/{doc.id}/sheets/{sheet}.png", "width": width, "height": height, "boxes": boxes,
            "font": width / 70,  # symbol labels, in sheet units
            "ids": {b["id"] for b in boxes}}


@router.get("/documents/{document_id}/sheets/{sheet}.png")
def sheet_png(request: Request, document_id: int, sheet: int, session: SessionDep) -> Response:
    """One drawing sheet as a picture, for the proof viewer (the boxes are drawn over it in SVG)."""
    doc = session.get(Document, document_id)
    if doc is None or doc.kind != "schematic" or not can_render(FileType(doc.file_type)):
        raise HTTPException(404, "This file has no drawing picture.")
    if doc.file_type != "pdf" and sheet != 1:
        raise HTTPException(404, "A drawing picture has one sheet.")
    try:
        png = drawing_png(FileType(doc.file_type), request.app.state.storage.read(doc.storage_key), sheet, [])
    except (OSError, ValueError) as error:
        raise HTTPException(404, "The drawing sheet could not be shown.") from error
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/enquiries/{project_id}/activity", response_class=HTMLResponse)
def activity(request: Request, project_id: int, session: SessionDep, show: str = "all", page: int = 1) -> HTMLResponse:
    """Everything done on the enquiry, newest first, in plain words; filtered by kind and paged."""
    project = project_or_404(session, project_id)
    show = show if show in labels.ACTIVITY_GROUPS else "all"
    query = select(AuditEvent).where(AuditEvent.project_id == project_id)
    count = select(func.count(AuditEvent.id)).where(AuditEvent.project_id == project_id)
    if show != "all":
        actions = labels.ACTIVITY_GROUPS[show][1]
        query, count = query.where(AuditEvent.action.in_(actions)), count.where(AuditEvent.action.in_(actions))
    total = session.scalar(count) or 0
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    events = list(session.scalars(query.order_by(AuditEvent.id.desc()).offset((page - 1) * PAGE_SIZE)
                                  .limit(PAGE_SIZE)))
    names = {str(d.id): d.original_name for d in project.documents}
    rows = [{"event": e, "text": labels.activity_text(
        e.action, e.detail, names.get(e.entity_id or "") if e.entity == "document" else None)} for e in events]
    return render(request, "activity.html", **enquiry_context(session, project), rows=rows, show=show, page=page,
                  pages=pages, total=total, tab="details",
                  filters={"all": "All", **{k: v[0] for k, v in labels.ACTIVITY_GROUPS.items()}})
