"""The draft estimate as a DOCX report (python-docx).

The report lists every priced line with its catalogue code and price, the
approved values each line was built from (with document and page), the
substitutes the engineer approved and why, the unmatched items, and the
missing or conflicting information. Prices come only from the catalogue.
"""

from __future__ import annotations

import io
from datetime import datetime

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from backend.app.models import Estimate, ExtractedValueRow, Project


def _money(x) -> str:
    return f"{x:,.2f}"


def _qty(x) -> str:
    return f"{x.normalize():f}" if x == x.to_integral() else f"{x:.3f}".rstrip("0")


def _table(document, header: list[str], rows: list[list[str]], numeric: set[int] = frozenset()):
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Light List Accent 1" if "Light List Accent 1" in [s.name for s in document.styles] else None
    for i, h in enumerate(header):
        table.rows[0].cells[i].text = h
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = value
            if i in numeric:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return table


def source_words(v: ExtractedValueRow) -> str:
    where = f"sheet {v.page}" if v.source_document == "schematic" else f"page {v.page}"
    text = f', "{v.source_text}"' if v.source_text else ""
    return f"{v.source_file}, {where}{text}"


def estimate_docx(project: Project, estimate: Estimate, values: dict[int, ExtractedValueRow],
                  generated_at: datetime, reading_line: str = "Read with rules") -> bytes:
    d = docx.Document()
    d.styles["Normal"].font.size = Pt(10)
    d.core_properties.title = f"Draft estimate {project.reference or project.name}"
    d.core_properties.author = "Switchgear Estimation Assistant"

    d.add_heading("Draft estimate", level=0)
    d.add_paragraph(f"Project: {project.name}")
    if project.reference:
        d.add_paragraph(f"Reference: {project.reference}")
    d.add_paragraph(f"Estimate {estimate.id}, built {estimate.created_at:%Y-%m-%d %H:%M} UTC; "
                    f"report generated {generated_at:%Y-%m-%d %H:%M} UTC. {reading_line}.")
    d.add_paragraph("Built from engineer-approved values only. Every price comes from the parts catalogue; "
                    "items with no safe catalogue match are listed as unmatched and are not priced. "
                    "Synthetic demonstration data.")

    d.add_heading("Totals", level=1)
    cur = estimate.currency
    _table(d, ["Item", f"Amount ({cur})"], [
        ["Materials", _money(estimate.materials)],
        [f"Labour ({_qty(estimate.labour_hours)} h at {_money(estimate.labour_rate)} per hour)",
         _money(estimate.labour)],
        [f"Margin ({_qty(estimate.margin_percent)} %)", _money(estimate.margin)],
        ["Total", _money(estimate.total)],
    ], numeric={1})

    d.add_heading("Lines", level=1)
    _table(d, ["Code", "Description", "Qty", "Unit", f"Unit price ({cur})", f"Materials ({cur})"],
           [[ln.code, ln.description + ("  [substitute, approved]" if ln.substitute_reasons else ""),
             _qty(ln.quantity), ln.unit, _money(ln.unit_price), _money(ln.materials)] for ln in estimate.lines],
           numeric={2, 4, 5})

    d.add_heading("Sources of each line", level=1)
    for ln in estimate.lines:
        p = d.add_paragraph(style="List Bullet")
        p.add_run(f"{ln.code}: ").bold = True
        used = [values[i] for i in ln.value_ids if i in values]
        p.add_run("; ".join(f"{v.field} = {v.approved_value}{' ' + v.approved_unit if v.approved_unit else ''} "
                            f"({source_words(v)}{', edited' if v.review_status == 'edited' else ''})"
                            for v in used) or "no values")
        for reason in ln.substitute_reasons:
            d.add_paragraph(f"Substitute approved by the engineer: {reason}", style="List Bullet 2")

    d.add_heading("Not priced", level=1)
    if estimate.pending:
        d.add_paragraph("Substitutes waiting for review:")
        for s in estimate.pending:
            d.add_paragraph(f"{s['description']}: {s['code']} ({s['reason']})", style="List Bullet")
    if estimate.unmatched:
        d.add_paragraph("Unmatched items (no safe catalogue part):")
        for u in estimate.unmatched:
            d.add_paragraph(f"{u['description']}: {u['reason']}", style="List Bullet")
    if estimate.problems:
        d.add_paragraph("Missing or conflicting information:")
        for pr in estimate.problems:
            d.add_paragraph(f"{pr['field']}: {pr['message']}", style="List Bullet")
    if not (estimate.pending or estimate.unmatched or estimate.problems):
        d.add_paragraph("Nothing: every required item is priced.")

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
