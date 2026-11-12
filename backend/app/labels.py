"""Plain words for the screens: field names, values, sources, reading methods and activity lines.

The database and the answer key use machine names (``system.fault_level``,
``way.Q2.rating``, ``spec.table.way``). Normal screens never show them; this
module turns each into the words an engineer would use. The machine names
stay available in the proof panel and in Activity.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

FIELD_LABELS = {
    "system.voltage": "System voltage",
    "system.frequency": "System frequency",
    "system.fault_level": "Fault level",
    "system.earthing": "Earthing system",
    "incomer.device": "Incomer device",
    "incomer.rating": "Incomer rating",
    "incomer.poles": "Incomer poles",
    "busbar.rating": "Busbar rating",
    "metering.ct_ratio": "CT ratio",
    "metering.meter": "Meter type",
    "enclosure.form": "Form of separation",
    "enclosure.ip_rating": "IP rating",
    "enclosure.cable_entry": "Cable entry",
    "enclosure.width": "Board width",
    "enclosure.sections": "Number of sections",
    "ways.count": "Number of outgoing ways",
}
WAY_PARTS = {
    "rating": "rating", "poles": "poles", "device": "device", "breaking_capacity": "breaking capacity",
    "cable": "cable", "cable_length": "cable length", "description": "description",
}
WAY_FIELD = re.compile(r"^way\.([^.]+)\.(.+)$")

DEVICE_WORDS = {"acb": "ACB", "mccb": "MCCB", "mcb": "MCB", "switch_disconnector": "Switch-disconnector"}
KIND_WORDS = {"specification": "Specification", "schematic": "Drawing", "requirements": "Customer letter"}
CONFIDENCE_WORDS = {
    "high": "High: read by a fixed rule from a clear statement.",
    "medium": "Medium: read from free text, a model or a picture, so check it against the source.",
    "low": "Low: the document leaves this open or the reading is weak.",
    "conflict": "Conflict: the documents give different values.",
}
LINE_WORDS = {"incomer": "Incomer", "cts": "Current transformers", "meter": "Meter", "sections": "Enclosure sections",
              "section.incomer": "Incomer section", "section.outgoing": "Outgoing sections", "busbar": "Busbar",
              "form_kit": "Form of separation kits"}


def field_label(field: str) -> str:
    """``system.voltage`` -> "System voltage"; ``way.Q2.rating`` -> "Way Q2 rating"."""
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    if m := WAY_FIELD.match(field):
        return f"Way {m.group(1)} {WAY_PARTS.get(m.group(2), m.group(2).replace('_', ' '))}"
    words = field.replace(".", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def line_label(key: str) -> str:
    """A quote line's key in words: ``way.Q2`` -> "Way Q2", ``gland.Q2`` -> "Cable gland for way Q2"."""
    if key in LINE_WORDS:
        return LINE_WORDS[key]
    if key.startswith("way."):
        return f"Way {key[4:]}"
    if key.startswith("gland."):
        return f"Cable gland for way {key[6:]}"
    return key.replace(".", " ").replace("_", " ").capitalize()


def display(value: Any, unit: str | None = None) -> str:
    """A value as an engineer writes it: "250 A", "MCCB", "Not given"."""
    if value is None:
        return "Not given"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and value in DEVICE_WORDS:
        return DEVICE_WORDS[value]
    return f"{value} {unit}" if unit else str(value)


def source_words(document: str, page: int | None, file_type: str | None = None) -> str:
    """ "Specification, page 5", "Drawing (CAD), sheet 1", "Drawing (picture), sheet 1", "Customer letter".

    With the file type, a drawing says whether it is the CAD file (DXF) or a picture of the drawing (a drawing
    PDF or an image, read by OCR), so the two never look like the same source.
    """
    kind = KIND_WORDS.get(document, document.capitalize())
    if document == "schematic" and file_type:
        kind = "Drawing (CAD)" if file_type == "dxf" else "Drawing (picture)"
    if page is None or document == "requirements":
        return kind
    return f"{kind}, {'sheet' if document == 'schematic' else 'page'} {page}"


def value_source(v: Any) -> str:
    """Where one stored value was read, in words (see :func:`source_words`)."""
    doc = getattr(v, "document", None)
    return source_words(v.source_document, v.page, getattr(doc, "file_type", None))


def method_words(method: str, agreement: str | None = None, quote_match: str | None = None) -> str:
    """How one value was read, in a short phrase."""
    if method == "ocr":
        return "Read from the drawing picture (OCR)"
    if method == "vision":
        return "Read from the drawing picture by a vision model"
    if method == "detector":
        return "Found on the drawing picture by the symbol detector"
    if method == "llm":
        text = "Read by the model"
        if quote_match == "words_on_page":
            text += "; its quote is pieced together from words on the page"
        return text
    if agreement == "agree":
        return "Read by the rules; the model read the same"
    if agreement == "disagree":
        return "Read by the rules; the model read something else"
    return "Read by the rules"


def short_date(day: date) -> str:
    """7 Nov 2026 (no leading zero, the same on every platform)."""
    return f"{day.day} {day:%b %Y}"


MODEL_RUN = re.compile(r"^(?P<model>[^,]+?), (?P<date>\d{4}-\d{2}-\d{2})(?P<rest> .*)?$")


def model_run_words(label: str) -> str:
    """``gemma4:e2b, 2026-11-07`` -> "gemma4:e2b (recorded 7 Nov 2026)"; a live run says "live"."""
    m = MODEL_RUN.match(label)
    if not m:
        return label
    model, rest = m.group("model"), (m.group("rest") or "").strip()
    day = short_date(date.fromisoformat(m.group("date")))
    live = "(live" in model
    model = re.sub(r"\s*\(live[^)]*\)", "", model)
    words = f"{model} ({'live' if live else 'recorded'} {day})"
    return f"{words} {rest}" if rest else words


def reading_line(methods: set[str], model_runs: list[str]) -> str:
    """The honest header line, e.g. "Read with rules + OCR + gemma4:e2b (recorded 7 Nov 2026)"."""
    parts = []
    tokens = {t for m in methods for t in m.split("+")}  # "ocr+vision" is a drawing read both ways
    if "rules" in tokens:
        parts.append("rules")
    if "ocr" in tokens:
        parts.append("OCR")
    if "vision" in tokens:
        parts.append("a vision model")
    parts += [model_run_words(run) for run in model_runs]
    return "Read with " + " + ".join(parts) if parts else "Nothing read yet"


# --- activity ------------------------------------------------------------------------------------

def _state(state: Any) -> str:
    if not isinstance(state, dict):
        return "" if state is None else str(state)
    return display(state.get("value"), state.get("unit")) if state.get("value") is not None else ""


def activity_text(action: str, detail: dict[str, Any], file_name: str | None = None) -> str:
    """One activity line in plain words, e.g. "Approved Way Q8 rating 125 A"."""
    d = detail or {}
    label = field_label(d["field"]) if d.get("field") else "a value"
    old, new = _state(d.get("old")), _state(d.get("new"))
    reason = f": {d['reason']}" if d.get("reason") else ""
    name = file_name or d.get("name") or "a file"
    if action == "approve":
        return f"Approved {label} {new}".rstrip() + (reason if reason and "agreeing" not in reason else "")
    if action == "edit":
        return f"Changed {label} to {new}" + (f" (was {old})" if old else "") + reason
    if action == "reject":
        return f"Rejected {label} {old}".rstrip() + reason
    if action == "approve_agreed":
        return f"Accepted {d.get('approved', 0)} agreeing values in one step"
    if action == "create":
        return f"Created the enquiry {d.get('name', '')}".rstrip()
    if action == "rename":
        return f"Renamed the enquiry to {d.get('name', '')}".rstrip()
    if action == "archive":
        return "Archived the enquiry"
    if action == "unarchive":
        return "Brought the enquiry back from the archive"
    if action == "upload":
        return f"Uploaded {name}"
    if action == "upload_rejected":
        return f"Did not accept {name}{reason}"
    if action == "extract":
        how = {"ocr": "OCR", "rules+llm": "rules and the model", "rules": "rules"}.get(d.get("method"), "rules")
        if d.get("status") == "not_read":
            return f"Stored {name}; it was not read"
        return f"Read {name} with {how}: {d.get('values', 0)} values"
    if action == "extract_failed":
        return f"Could not read {name}"
    if action == "read_again":
        return f"Read {name} again"
    if action == "document_delete":
        return f"Deleted {name}"
    if action == "llm_values_rejected":
        return f"Left out {d.get('count', 0)} model values from {name} that failed the quote check"
    if action == "instruction_text_flagged":
        return f"Flagged instruction-like text in {name}; it was not followed"
    if action == "estimate":
        return f"Rebuilt the quote: {d.get('lines', 0)} lines, total {d.get('total', '0.00')}"
    if action == "export":
        return f"Exported the report ({str(d.get('format', 'file')).upper()})"
    if action == "substitute_approve":
        return f"Approved substitute part {d.get('code', '')}".rstrip()
    if action == "substitute_reject":
        return f"Rejected substitute part {d.get('code', '')}".rstrip() + reason
    if action == "ask":
        return f"Asked: {d.get('question', '')}".rstrip()
    return action.replace("_", " ").capitalize()


ACTIVITY_GROUPS = {
    "decisions": ("Decisions", ["approve", "edit", "reject", "approve_agreed", "substitute_approve",
                                "substitute_reject"]),
    "files": ("Files", ["upload", "upload_rejected", "extract", "extract_failed", "read_again", "document_delete",
                        "llm_values_rejected", "instruction_text_flagged"]),
    "quote": ("Quote and report", ["estimate", "export"]),
    "questions": ("Questions", ["ask"]),
    "enquiry": ("Enquiry", ["create", "rename", "archive", "unarchive"]),
}


def title_from_specification(text: str) -> tuple[str | None, str | None]:
    """A name and a reference for an unnamed enquiry, from the first page of its specification.

    The title is the lines before the first "Label: value" line; "Technical specification for" is
    dropped. Both are None when the page does not start that way: nothing is invented.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head: list[str] = []
    for ln in lines[:4]:
        if ":" in ln:
            break
        head.append(ln)
    title = " ".join(head)
    title = re.sub(r"^(technical\s+)?specification\s+(for|of)\s+", "", title, flags=re.IGNORECASE).strip(" .")
    name = (title[:1].upper() + title[1:])[:120] if 3 <= len(title) and head and len(head) < 4 else None
    ref = re.search(r"(?:Enquiry|Our)\s+reference:\s*([A-Za-z0-9][\w/-]{1,40})", text)
    return name, (ref.group(1) if ref else None)
