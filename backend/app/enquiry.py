"""What an enquiry's screens show, worked out from its stored values (no web code, no writes).

- :func:`review_groups`: the values of each field side by side, with conflicts marked.
- :func:`decisions`: what needs the engineer: conflicts, values to review one by one (grouped by the
  reason), and the values that agree and may be accepted together.
- :func:`preview_items`: "Items the customer wants", from the same matching logic as the quote. Unlike the
  quote it may use values that are not approved yet; every such item is marked.
- :func:`status`: the pill on the enquiries list ("Needs you (N)", "Ready to quote", "Quoted").

The quote itself is still built only from approved values (:mod:`backend.app.estimate`).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app import labels
from backend.app import normalise as norm
from backend.app.catalogue import CatalogueItem
from backend.app.estimate import ApprovedValue, Draft, EstimateRules, build
from backend.app.injection import find_instructions
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow, Match, Project
from backend.app.schemas import DocumentStatus, MatchStatus, ReviewStatus

BUSY = {DocumentStatus.UPLOADED.value, DocumentStatus.READING.value, DocumentStatus.EXTRACTING.value}
DONE = ("approved", "edited")
FIELD_ORDER = ["system.", "enclosure.", "incomer.", "busbar.", "metering.", "ways.count", "way."]
REQUIRED = ["system.voltage", "system.fault_level", "enclosure.form", "enclosure.ip_rating", "enclosure.cable_entry",
            "incomer.device", "incomer.rating", "incomer.poles", "busbar.rating", "metering.ct_ratio",
            "metering.meter", "ways.count"]
WAY_REQUIRED = ["device", "rating", "poles", "cable"]
WAY_FIELD = re.compile(r"^way\.(\w+)\.")

# Why a value is left for the engineer instead of being accepted with the agreeing ones.
REASONS: OrderedDict[str, tuple[str, str]] = OrderedDict([
    ("open", ("Left open in a document", "The document names the item but gives no value (for example TBC). "
                                         "Type the value once it is confirmed.")),
    ("ocr", ("Read from a drawing picture", "Text read from a picture can be misread. Check each one against "
                                            "the drawing.")),
    ("pieced", ("Quote pieced together", "Every word of the model's quote is on the page, but not as one "
                                         "sentence. Check each one against the page.")),
    ("way_missing", ("Way not in every document", "The specification and the drawing do not list the same "
                                                  "ways. Check the number of ways first.")),
    ("open_elsewhere", ("Open in another document", "Another document leaves this open (for example TBC). "
                                                    "Approve only if it is confirmed.")),
    ("low", ("Low confidence", "The reading is weak. Check each one against its source.")),
    ("medium", ("Medium confidence", "Read from free text or by a model. Check each one against its source.")),
])


def field_sort_key(name: str) -> tuple:
    group = next((i for i, p in enumerate(FIELD_ORDER) if name.startswith(p)), len(FIELD_ORDER))
    m = re.match(r"^way\.Q(\d+)\.(.+)$", name)
    return (group, int(m.group(1)), m.group(2)) if m else (group, 0, name)


def shown(v: ExtractedValueRow) -> tuple[Any, str | None]:
    """The value as it stands now: the engineer's once approved or edited, else as extracted."""
    return (v.approved_value, v.approved_unit) if v.review_status in DONE else (v.value, v.unit)


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
    """One group per field, in reading order, with its values and whether they conflict."""
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for v in sorted(project.values, key=lambda v: (field_sort_key(v.field), v.id)):
        g = groups.setdefault(v.field, {"field": v.field, "label": labels.field_label(v.field), "values": []})
        g["values"].append(v)
    partial = partial_ways(project.values)
    for g in groups.values():
        m = WAY_FIELD.match(g["field"])
        g["missing_from"] = partial.get(m.group(1), []) if m else []
        live = [v for v in g["values"] if v.review_status != ReviewStatus.REJECTED.value and v.value is not None]
        sides: OrderedDict[tuple, list[ExtractedValueRow]] = OrderedDict()
        for v in live:
            value, unit = shown(v)
            sides.setdefault((norm.value_key(value), norm.unit(unit)), []).append(v)
        g["sides"] = list(sides.values())
        g["conflict"] = len(sides) > 1
        g["pending"] = any(v.review_status == ReviewStatus.EXTRACTED.value for v in g["values"])
        g["left_open"] = open_in_a_document(g["values"])
    return groups


def distinct_sources(values: list[Any]) -> list[Any]:
    """The values of one conflict side with true duplicates merged: one per file and page.

    A side holds values that agree, so the same file and page twice (the rules and the model reading the
    same line) is one source. Two different files stay apart even when their words look alike, for
    example the CAD drawing and a picture of the drawing.
    """
    seen: set[tuple[Any, Any]] = set()
    out = []
    for v in values:
        key = (v.document_id, v.page)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def missing_information(groups: OrderedDict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Required fields no document gives a value for."""
    stated = {f for f, g in groups.items() if any(v.value is not None for v in g["values"])}
    ways = sorted({m.group(1) for f in groups if (m := WAY_FIELD.match(f))}, key=lambda w: (len(w), w))
    needed = REQUIRED + [f"way.{w}.{p}" for w in ways for p in WAY_REQUIRED]
    out = []
    for f in needed:
        if f not in stated:
            out.append({"field": f, "label": labels.field_label(f),
                        "why": "Stated as TBC; no value given" if f in groups else "Not found in any file read"})
    return out


def bulk_acceptable(groups: OrderedDict[str, dict[str, Any]]) -> list[ExtractedValueRow]:
    """The values "Accept all" may approve: high confidence, no conflict, exact quote, not read by OCR.

    Also left out: a way missing from one of the documents that list ways, and a field that one
    document leaves open while another gives a value.
    """
    out = []
    for g in groups.values():
        if g["conflict"] or g["missing_from"] or g["left_open"]:
            continue
        for v in g["values"]:
            if v.quote_match == "words_on_page" or v.method == "ocr":
                continue
            if v.review_status == ReviewStatus.EXTRACTED.value and v.confidence == "high" and v.value is not None:
                out.append(v)
    return out


def _reason(v: ExtractedValueRow, g: dict[str, Any]) -> str:
    if v.value is None:
        return "open"
    if v.method == "ocr":
        return "ocr"
    if v.quote_match == "words_on_page":
        return "pieced"
    if g["missing_from"]:
        return "way_missing"
    if g["left_open"]:
        return "open_elsewhere"
    return "low" if v.confidence == "low" else "medium"


def instruction_flags(project: Project, document_id: int | None = None) -> list[dict[str, Any]]:
    """Instruction-like sentences in the stored page text of the enquiry's files (or one file)."""
    out = []
    for d in project.documents:
        if document_id is not None and d.id != document_id:
            continue
        for page in d.pages:
            for f in find_instructions(page.number, page.text):
                out.append({"doc_id": d.id, "document": d.original_name, "page": f.page, "text": f.text,
                            "reasons": f.reasons})
    return out


@dataclass
class Decisions:
    """Everything the Check screen needs to say what is left for the engineer."""

    groups: OrderedDict[str, dict[str, Any]]
    conflicts: list[dict[str, Any]]  # field groups whose values differ
    reasons: OrderedDict[str, list[ExtractedValueRow]]  # values to review one by one, by reason key
    acceptable: list[ExtractedValueRow]  # what "Accept all" would approve
    missing: list[dict[str, str]]
    not_read: list[Document]
    busy: bool
    total: int  # values that are not rejected
    approved: int

    @property
    def to_review(self) -> int:
        return sum(len(v) for v in self.reasons.values())

    @property
    def disagree(self) -> int:
        """Fields whose documents give different values: the one count the Summary and Check both show."""
        return len(self.conflicts)

    @property
    def needs(self) -> int:
        """Decisions waiting: each conflict is one, each value to review is one. The agreeing values that
        "Accept all" would approve are not decisions and are not counted (owner, 12 Nov 2026)."""
        return self.disagree + self.to_review


def decisions(project: Project) -> Decisions:
    groups = review_groups(project)
    acceptable = bulk_acceptable(groups)
    taken = {v.id for v in acceptable}
    reasons: OrderedDict[str, list[ExtractedValueRow]] = OrderedDict()
    found: dict[str, list[ExtractedValueRow]] = {}
    for g in groups.values():
        if g["conflict"]:
            continue
        for v in g["values"]:
            if v.review_status == ReviewStatus.EXTRACTED.value and v.id not in taken:
                found.setdefault(_reason(v, g), []).append(v)
    for key in REASONS:
        if key in found:
            reasons[key] = found[key]
    return Decisions(
        groups=groups, conflicts=[g for g in groups.values() if g["conflict"]], reasons=reasons,
        acceptable=acceptable, missing=missing_information(groups),
        not_read=[d for d in project.documents if d.status in (DocumentStatus.NOT_READ.value,
                                                               DocumentStatus.FAILED.value)],
        busy=any(d.status in BUSY for d in project.documents),
        total=sum(1 for v in project.values if v.review_status != ReviewStatus.REJECTED.value),
        approved=sum(1 for v in project.values if v.review_status in DONE))


# --- how the enquiry was read -------------------------------------------------------------------------

def document_method(doc: Document) -> str | None:
    """How a file was read; worked out for files stored before the column existed."""
    if doc.read_method:
        return doc.read_method
    if doc.status != DocumentStatus.DONE.value:
        return None
    if doc.model_run:
        return "rules+model"
    return "ocr" if (doc.note or "").startswith("Read by OCR") else "rules"


def reading_line(project: Project) -> str:
    methods = {m for d in project.documents if (m := document_method(d))}
    runs = sorted({d.model_run for d in project.documents if d.model_run})
    return labels.reading_line(methods, runs)


# --- items the customer wants ---------------------------------------------------------------------------

@dataclass
class Item:
    key: str
    description: str
    quantity: float | None = None
    unit: str | None = None
    state: str = "approved"  # approved, unapproved, waiting, substitute, unmatched
    code: str | None = None
    part: str | None = None
    note: str | None = None
    basis: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # documents that state it, in words
    waiting_on: list[dict[str, str]] = field(default_factory=list)  # fields to decide or still missing

    @property
    def state_words(self) -> str:
        return {"approved": "Approved", "unapproved": "Not yet approved", "waiting": "Waiting for you",
                "substitute": "Substitute, needs approval", "unmatched": "No catalogue part"}[self.state]


def _approved(rows: list[ExtractedValueRow]) -> list[ApprovedValue]:
    return [ApprovedValue(value_id=r.id, field=r.field, value=r.approved_value, unit=r.approved_unit,
                          source=labels.value_source(r)) for r in rows
            if r.review_status in DONE]


def _open(rows: list[ExtractedValueRow]) -> list[ApprovedValue]:
    return [ApprovedValue(value_id=r.id, field=r.field, value=r.value, unit=r.unit,
                          source=labels.value_source(r)) for r in rows
            if r.review_status == ReviewStatus.EXTRACTED.value and r.value is not None]


def preview_draft(project: Project, items: list[CatalogueItem], rules: EstimateRules,
                  approved_substitutes: set[tuple[str, str]] = frozenset()) -> tuple[Draft, set[str]]:
    """The quote logic run on approved values plus, for fields with none, the values not yet reviewed.

    Returns the draft and the fields that rest on unreviewed values. Nothing here is stored or priced
    into the quote: it only tells the engineer what the customer appears to want.
    """
    approved, pending = _approved(project.values), _open(project.values)
    decided = {v.field for v in approved}
    assumed = [v for v in pending if v.field not in decided]
    draft = build(approved + assumed, items, rules, approved_substitutes=approved_substitutes,
                  open_values=[v for v in pending if v.field in decided])
    return draft, {v.field for v in assumed}


def preview_items(project: Project, items: list[CatalogueItem], rules: EstimateRules,
                  approved_substitutes: set[tuple[str, str]] = frozenset()) -> list[Item]:
    draft, assumed = preview_draft(project, items, rules, approved_substitutes)
    by_code = {i.code: i for i in items}
    stated: dict[str, set[str]] = {}
    for v in project.values:
        if v.review_status != ReviewStatus.REJECTED.value and v.value is not None:
            stated.setdefault(v.field, set()).add(labels.KIND_WORDS.get(v.source_document, v.source_document))
    out: list[Item] = []
    built = set()
    for d in draft.decisions:
        r, m = d.requirement, d.match
        built.add(r.key)
        part = by_code.get(m.code) if m.code else None
        if m.status == MatchStatus.UNMATCHED:
            state = "unmatched"
        elif m.status == MatchStatus.SUBSTITUTE and not d.approved:
            state = "substitute"
        else:
            state = "unapproved" if any(b in assumed for b in r.basis) else "approved"
        out.append(Item(key=r.key, description=r.description, quantity=r.quantity, unit=part.unit if part else None,
                        state=state, code=m.code, part=part.description if part else None,
                        note=m.reason if m.status != MatchStatus.EXACT else None, basis=list(r.basis),
                        sources=sorted(set().union(*(stated.get(b, set()) for b in r.basis)) if r.basis else [])))
    waiting: OrderedDict[str, Item] = OrderedDict()
    for p in draft.problems:
        for key in p.lines:
            if key in built:
                continue
            item = waiting.setdefault(key, Item(key=key, description=labels.line_label(key), state="waiting"))
            item.basis.append(p.field)
            item.waiting_on.append({"field": p.field, "label": labels.field_label(p.field), "kind": p.kind})
            item.sources = sorted(set(item.sources) | stated.get(p.field, set()))
    return out + list(waiting.values())


def approved_substitutes(session: Session, project_id: int) -> set[tuple[str, str]]:
    return {(m.requirement_key, m.code) for m in session.scalars(select(Match).where(Match.project_id == project_id))
            if m.status == MatchStatus.SUBSTITUTE.value and m.review_status == "approved" and m.code}


# --- the quote ------------------------------------------------------------------------------------------

def quote_blockers(estimate: Estimate) -> list[dict[str, Any]]:
    """One entry per line the quote could not build, saying what it waits for."""
    lines: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for p in estimate.problems or []:
        for key in p.get("lines", []):
            entry = lines.setdefault(key, {"key": key, "line": labels.line_label(key), "waits": []})
            entry["waits"].append({"field": p["field"], "label": labels.field_label(p["field"]),
                                   "kind": p["kind"], "message": p["message"]})
    return list(lines.values())


QUOTE_INPUTS = ("approve", "edit", "reject", "extract", "document_delete", "read_again", "substitute_approve",
                "substitute_reject")


def quote_out_of_date(session: Session, project_id: int, estimate: Estimate | None) -> bool:
    """True when something the quote depends on changed after the quote was built."""
    last_input = session.scalar(select(func.max(AuditEvent.id)).where(AuditEvent.project_id == project_id,
                                                                      AuditEvent.action.in_(QUOTE_INPUTS)))
    if last_input is None:
        return False
    if estimate is None:
        return True
    built = session.scalar(select(func.max(AuditEvent.id)).where(
        AuditEvent.project_id == project_id, AuditEvent.action == "estimate",
        AuditEvent.entity_id == str(estimate.id)))
    return built is None or built < last_input


# --- the Summary page: six tiles ------------------------------------------------------------------------

@dataclass
class Tile:
    """One tile on an enquiry's Summary page: a plain label, the answer, and the step that shows more."""

    key: str
    label: str
    value: str
    href: str
    note: str | None = None
    extra: str | None = None  # a second, separate fact (the missing tile's "Marked TBC")
    tone: str = "neutral"  # neutral, conflict or review


REQUIRED_NOTE = "From the app's list of required fields, not from the specification."
NOT_FOUND = "Not found in any file read"


def summary_tiles(project: Any, found: Any, items: list[Any], estimate: Any, blockers: list[Any]) -> list[Tile]:
    """The six tiles, from what the enquiry holds now. The cost uses approved values only (owner, 12 Nov
    2026): "Waiting for approvals" until something is approved, then the draft total and how many of the
    quote's lines it covers. Missing counts required fields no file gives; TBC values are kept apart."""
    base = f"/enquiries/{getattr(project, 'id', '')}"
    ways = sorted({m.group(1) for f in found.groups if (m := WAY_FIELD.match(f))})
    drawings = [d for d in project.documents if d.kind == "schematic"]
    kinds = sorted({d.file_type.upper() for d in drawings}, key=lambda k: (k != "DXF", k))
    conflicts = found.disagree
    if conflicts:
        agree = Tile("agree", "Do they agree?", f"Not yet: {conflicts} disagree", f"{base}/check", tone="conflict")
    else:
        agree = Tile("agree", "Do they agree?", "Yes", f"{base}/check",
                     note=f"{found.needs} decisions wait for you" if found.needs else None)
    if found.approved and estimate is not None and estimate.lines:
        lines = len(estimate.lines)
        cost = Tile("cost", "Estimated cost", f"{estimate.currency} {estimate.total:,.2f}", f"{base}/quote",
                    note=f"Draft, from {lines} of {lines + len(blockers)} lines")
    else:
        cost = Tile("cost", "Estimated cost", "Waiting for approvals", f"{base}/quote")
    required = [m for m in found.missing if m["why"] == NOT_FOUND]
    tbc = [m for m in found.missing if m["why"] != NOT_FOUND]
    missing = Tile("missing", "Required, not found", str(len(required)) if required else "None",
                   f"{base}/check#missing", note=REQUIRED_NOTE,
                   extra=f"Marked TBC: {len(tbc)}" if tbc else None, tone="review" if required else "neutral")
    return [
        Tile("quoted", "What is quoted", project.name, f"{base}/check?view=items",
             note=f"{len(ways)} outgoing ways found" if ways else None),
        Tile("parts", "Parts found", str(len(items)), f"{base}/check?view=items"),
        Tile("drawing", "Drawing attached", f"Yes: {', '.join(kinds)}" if drawings else "No", f"{base}/files"),
        agree, cost, missing,
    ]


# --- status pill ------------------------------------------------------------------------------------------

@dataclass
class Status:
    key: str  # empty, reading, needs, ready, quoted, archived
    label: str
    tone: str  # chip tone: neutral, review, conflict, approved


def status(session: Session, project: Project, estimate: Estimate | None, found: Decisions | None = None) -> Status:
    if project.archived_at is not None:
        return Status("archived", "Archived", "neutral")
    if not project.documents:
        return Status("empty", "No files yet", "neutral")
    d = found or decisions(project)
    if d.busy:
        return Status("reading", "Reading", "review")
    if (d.needs or d.acceptable or d.missing or not estimate or not estimate.lines or estimate.problems
            or estimate.pending):
        waiting = d.needs + len(estimate.pending if estimate else [])
        return Status("needs", f"Needs you ({waiting})" if waiting else "Needs you", "conflict")
    exported = session.scalar(select(func.max(AuditEvent.id)).where(
        AuditEvent.project_id == project.id, AuditEvent.action == "export",
        AuditEvent.entity_id == str(estimate.id)))
    return Status("quoted", "Quoted", "approved") if exported else Status("ready", "Ready to quote", "review")
