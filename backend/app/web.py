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
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote as url_quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app import enquiry, labels, services
from backend.app.drawing.render import can_render, drawing_png
from backend.app.estimate import load_rules
from backend.app.highlight import segments
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow, Match, Project
from backend.app.report import estimate_docx
from backend.app.schemas import DocumentStatus, ReviewStatus
from backend.app.storage import FileType, UploadRejected

router = APIRouter()
BUSY = enquiry.BUSY
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
    return render(request, "home.html")


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
                  max_pages=settings.max_pdf_pages, nav="new")


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
                         files: Annotated[list[UploadFile], File()] = []) -> Response:  # noqa: B006
    """One step: an optional name and the files. With files it goes on to read them and then to Check."""
    project = services.create_project(session, name, reference)
    errors = await _store_uploads(request, session, background, project, files)
    session.refresh(project)
    if errors:
        return render(request, "files.html", status_code=422, errors=errors, go=False,
                      **_files_context(request, session, project))
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


@router.get("/enquiries/{project_id}")
def open_enquiry(project_id: int, session: SessionDep) -> Response:
    """Opening an enquiry goes to the step that needs the engineer: Files while empty, otherwise Check."""
    project = project_or_404(session, project_id)
    return RedirectResponse(f"/enquiries/{project_id}/{'check' if project.documents else 'files'}", status_code=303)


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


def _check_context(request: Request, session: Session, project: Project, open_reason: str | None = None,
                   error: str | None = None) -> dict[str, Any]:
    found = enquiry.decisions(project)
    items = _items(request, session, project)
    return {**enquiry_context(session, project, found), "items": items, "reasons": enquiry.REASONS,
            "open_reason": open_reason if open_reason in found.reasons else None, "error": error,
            "flags": enquiry.instruction_flags(project), "tab": "check"}


@router.get("/enquiries/{project_id}/check", response_class=HTMLResponse)
def check_page(request: Request, project_id: int, session: SessionDep, open: str | None = None,
               error: str | None = None) -> HTMLResponse:
    project = project_or_404(session, project_id)
    return render(request, "check.html", **_check_context(request, session, project, open, error))


def _after_decision(request: Request, session: Session, project_id: int, open_reason: str | None = None,
                    error: str | None = None, anchor: str | None = None) -> Response:
    """After a decision on Check: rebuild the quote, then the refreshed Check block (HTMX) or a redirect."""
    if error is None:
        services.refresh_quote(session, project_id, request.app.state.settings)
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
              value_id: Annotated[int, Form()]) -> Response:
    """ "Use this" on a conflict card: keep this source's value, reject the others."""
    project_or_404(session, project_id)
    error = None
    try:
        services.resolve_field(session, project_id, field, keep_value_id=value_id)
    except services.ReviewError as e:
        error = str(e)
    return _after_decision(request, session, project_id, error=error)


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
    """The report of the current quote. The quote is rebuilt first if anything changed since it was built."""
    project = project_or_404(session, project_id)
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
    return render(request, "proof.html", **enquiry_context(session, project), current=current, pages=pages,
                  page_no=page_no, segments=segs, values=values, flags=flags, tab="details")


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
