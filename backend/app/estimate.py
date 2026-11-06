"""Build a draft estimate from approved values only.

Steps:

1. **Resolve fields.** For each field, take the approved values (approved or
   edited by the engineer; extracted and rejected values are ignored). One
   distinct value: use it. None: the field is *missing*. Several different
   values: the field is a *conflict* and every line that needs it is blocked
   until the engineer rejects all but one.
2. **Requirements.** The rule book (``config/estimate.toml``) turns resolved
   fields into catalogue requirements: incomer, CTs, meter, one breaker per
   way, busbar per metre of board width, enclosure sections, form kits and
   cable glands. A line whose fields are missing or in conflict is not built;
   the reason is listed.
3. **Matching** (:mod:`backend.app.catalogue`): exact, substitute or unmatched.
   A substitute reaches the estimate only when the engineer has approved it.
4. **Prices** come only from the catalogue: quantity x unit price, plus
   quantity x labour hours x the labour rate, then the margin.
"""

from __future__ import annotations

import math
import re
import tomllib
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.app import normalise as norm
from backend.app.catalogue import CatalogueItem, match
from backend.app.schemas import MatchResult, MatchStatus, Requirement

CENT = Decimal("0.01")


class EstimateRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    labour_rate_per_hour: Decimal
    margin_percent: Decimal
    ct_per_incomer: int
    mcb_cascade: bool
    incomer_width_mm: int
    outgoing_width_mm: int
    units_per_outgoing_section: int
    units_above_400a: int
    forms_with_kit: list[str]
    glands_by_conductor_mm2: list[tuple[int, str]]
    parallel_gland: str


def load_rules(path: Path) -> EstimateRules:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    s, g = raw["sections"], raw["glands"]
    return EstimateRules(
        currency=raw["currency"], labour_rate_per_hour=Decimal(raw["labour_rate_per_hour"]),
        margin_percent=Decimal(raw["margin_percent"]), ct_per_incomer=raw["current_transformers"]["per_incomer"],
        mcb_cascade=raw["breakers"]["mcb_cascade"], incomer_width_mm=s["incomer_width_mm"],
        outgoing_width_mm=s["outgoing_width_mm"], units_per_outgoing_section=s["units_per_outgoing_section"],
        units_above_400a=s["units_above_400a"], forms_with_kit=s["forms_with_kit"],
        glands_by_conductor_mm2=[(int(a), str(b)) for a, b in g["by_conductor_mm2"]], parallel_gland=g["parallel"])


class ApprovedValue(BaseModel):
    """An engineer-approved value: what the estimate may use, and where it came from."""

    value_id: int
    field: str
    value: str | int | float | None
    unit: str | None = None
    source: str  # plain words, e.g. "specification p5"


class Problem(BaseModel):
    """Why a line could not be built: a missing field or approved values that disagree."""

    kind: str  # "missing" or "conflict"
    field: str
    message: str
    lines: list[str] = Field(default_factory=list)  # requirement keys it blocks


class Decision(BaseModel):
    """A requirement with its catalogue match and whether it may be priced."""

    requirement: Requirement
    match: MatchResult
    approved: bool  # exact matches are approved; substitutes only after the engineer approves them


class PricedLine(BaseModel):
    code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    labour_hours: Decimal  # total for the line
    materials: Decimal
    requirement_keys: list[str]
    basis: list[str]
    substitute_reasons: list[str] = Field(default_factory=list)


class Totals(BaseModel):
    materials: Decimal
    labour_hours: Decimal
    labour: Decimal
    subtotal: Decimal
    margin: Decimal
    total: Decimal


class Draft(BaseModel):
    lines: list[PricedLine]
    decisions: list[Decision]
    problems: list[Problem]
    totals: Totals

    @property
    def unmatched(self) -> list[Decision]:
        return [d for d in self.decisions if d.match.status == MatchStatus.UNMATCHED]

    @property
    def substitutes_to_review(self) -> list[Decision]:
        return [d for d in self.decisions if d.match.status == MatchStatus.SUBSTITUTE and not d.approved]


# --- 1. field resolution -------------------------------------------------------------------------

class Fields:
    """Resolved approved values, recording what is missing or in conflict."""

    def __init__(self, approved: list[ApprovedValue], open_values: list[ApprovedValue] | None = None) -> None:
        self.by_field: dict[str, list[ApprovedValue]] = {}
        for v in approved:
            self.by_field.setdefault(v.field, []).append(v)
        # Values not yet reviewed: never priced, only used to tell a conflict from a gap.
        self.open_by_field: dict[str, list[ApprovedValue]] = {}
        for v in open_values or []:
            self.open_by_field.setdefault(v.field, []).append(v)
        self.problems: dict[str, Problem] = {}

    def disputed(self, field: str) -> list[ApprovedValue]:
        """Distinct approved and unreviewed values of ``field``: more than one means the documents disagree."""
        seen: dict[tuple, ApprovedValue] = {}
        for v in self.by_field.get(field, []) + self.open_by_field.get(field, []):
            if v.value is not None:
                seen.setdefault((norm.value_key(v.value), norm.unit(v.unit)), v)
        return list(seen.values())

    def distinct(self, field: str) -> list[ApprovedValue]:
        seen: dict[tuple, ApprovedValue] = {}
        for v in self.by_field.get(field, []):
            seen.setdefault((norm.value_key(v.value), norm.unit(v.unit)), v)
        return list(seen.values())

    def get(self, field: str, line: str) -> ApprovedValue | None:
        """The one approved value of ``field``, or None (recorded as a problem for ``line``)."""
        values = self.distinct(field)
        if len(values) == 1 and values[0].value is not None:
            return values[0]
        if len(values) > 1:
            listed = "; ".join(f"{v.value}{' ' + v.unit if v.unit else ''} ({v.source})" for v in values)
            problem = self.problems.setdefault(field, Problem(
                kind="conflict", field=field, message=f"Approved values disagree: {listed}"))
        elif len(open_ := self.disputed(field)) > 1:
            listed = "; ".join(f"{v.value}{' ' + v.unit if v.unit else ''} ({v.source})" for v in open_)
            problem = self.problems.setdefault(field, Problem(
                kind="conflict", field=field, message=f"Documents disagree, resolve on the review screen: {listed}"))
        else:
            problem = self.problems.setdefault(field, Problem(
                kind="missing", field=field, message="No approved value"))
        if line not in problem.lines:
            problem.lines.append(line)
        return None

    def number(self, field: str, line: str, unit: str | None = None) -> int | float | None:
        """A numeric value, in ``unit`` if given; a value without its unit is not assumed to have it."""
        v = self.get(field, line)
        if v is None:
            return None
        n = v.value if isinstance(v.value, (int, float)) else norm.number(str(v.value))
        if n is None or (unit is not None and norm.unit(v.unit) != unit):
            self.problems.setdefault(field, Problem(
                kind="missing", field=field,
                message=f"Approved value {v.value}{' ' + v.unit if v.unit else ''} has no usable unit "
                        f"(needs {unit}); not assumed")).lines.append(line)
            return None
        return n

    def text(self, field: str, line: str) -> str | None:
        v = self.get(field, line)
        return None if v is None else str(v.value)

    def ways(self) -> list[str]:
        """Every way with an approved or an unreviewed value; a way still under review is listed as missing."""
        ids = {m.group(1) for f in [*self.by_field, *self.open_by_field] if (m := re.match(r"^way\.([^.]+)\.", f))}
        return sorted(ids, key=lambda w: (len(w), w))


# --- 2. requirements ---------------------------------------------------------------------------

DEVICE_CATEGORY = {"acb": "acb", "mccb": "mccb", "mcb": "mcb", "switch_disconnector": "switch_disconnector"}
CONDUCTOR = re.compile(r"(?:(\d)x\s*)?\d+C\s+(\d+)\s*mm2", re.IGNORECASE)


def _layout_conflicts(fields: Fields, rules: EstimateRules) -> list[str]:
    """Conflicting fields that could change the number of section units: the number of ways, or a way
    rating whose alternatives fall on different sides of the 400 A two-unit limit."""
    out = ["ways.count"] if len(fields.disputed("ways.count")) > 1 else []
    for w in fields.ways():
        field = f"way.{w}.rating"
        ratings = [norm.number(str(v.value)) for v in fields.disputed(field)]
        units = {rules.units_above_400a if r is not None and r > 400 else 1 for r in ratings}
        if len(ratings) > 1 and len(units) > 1:
            out.append(field)
    return out


def gland_for(cable: str, rules: EstimateRules) -> tuple[str, int] | None:
    """Gland thread and count for one cable description, or None when the cable is not understood."""
    m = CONDUCTOR.search(cable)
    if not m:
        return None
    if m.group(1):  # parallel cables
        return rules.parallel_gland, int(m.group(1))
    size = int(m.group(2))
    for limit, thread in rules.glands_by_conductor_mm2:
        if size <= limit:
            return thread, 1
    return None


def requirements(fields: Fields, rules: EstimateRules) -> list[Requirement]:
    out: list[Requirement] = []

    def add(**kw) -> None:
        out.append(Requirement(**kw))

    # Incomer, CTs and meter.
    dev, rating, poles = (fields.text("incomer.device", "incomer"), fields.number("incomer.rating", "incomer", "A"),
                          fields.number("incomer.poles", "incomer"))
    fault = fields.number("system.fault_level", "incomer", "kA")
    if dev and rating and poles and fault and dev in DEVICE_CATEGORY:
        add(key="incomer", category=DEVICE_CATEGORY[dev], quantity=1, rating_a=int(rating), poles=int(poles),
            min_breaking_ka=int(fault), description=f"Incomer {dev.upper()} {int(rating)} A {int(poles)}P",
            basis=["incomer.device", "incomer.rating", "incomer.poles", "system.fault_level"])
    ratio = fields.text("metering.ct_ratio", "cts")
    ct_rating = fields.number("incomer.rating", "cts", "A")
    if ratio and ct_rating:
        add(key="cts", category="current_transformer", quantity=rules.ct_per_incomer, rating_a=int(ct_rating),
            size=ratio, description=f"Current transformers {ratio} A", basis=["incomer.rating", "metering.ct_ratio"])
    if meter := fields.text("metering.meter", "meter"):
        add(key="meter", category="meter", quantity=1, size=meter, description=f"{meter} meter",
            basis=["metering.meter"])

    # One breaker per outgoing way.
    units = 0
    unit_problem = False
    for w in fields.ways():
        key, f = f"way.{w}", f"way.{w}"
        dev = fields.text(f"{f}.device", key)
        rating = fields.number(f"{f}.rating", key, "A")
        poles = fields.number(f"{f}.poles", key)
        if rating is None:
            unit_problem = True
        else:
            units += rules.units_above_400a if rating > 400 else 1
        if not (dev and rating and poles) or dev not in DEVICE_CATEGORY:
            continue
        basis = [f"{f}.device", f"{f}.rating", f"{f}.poles"]
        min_ka = None
        if dev in ("mccb", "mcb"):
            bc = fields.number(f"{f}.breaking_capacity", key, "kA")
            if dev == "mcb" and rules.mcb_cascade:
                min_ka = int(bc) if bc else None
                basis.append(f"{f}.breaking_capacity")
                if bc is None:
                    continue
            else:
                fl = fields.number("system.fault_level", key, "kA")
                if fl is None or len(fields.disputed(f"{f}.breaking_capacity")) > 1:
                    continue  # a disputed own kA could need a bigger breaker: never priced around it
                min_ka = int(max(fl, bc or 0))
                basis += [f"{f}.breaking_capacity", "system.fault_level"]
        add(key=key, category=DEVICE_CATEGORY[dev], quantity=1, rating_a=int(rating), poles=int(poles),
            min_breaking_ka=min_ka, description=f"Way {w} {dev.replace('_', '-').upper()} {int(rating)} A {int(poles)}P",
            basis=basis)

    # Sections: stated on the drawing, else counted from the ways (marked as calculated).
    # A stated layout follows the ways, so it waits while a conflict could change it.
    if layout_doubt := _layout_conflicts(fields, rules):
        for field in ("enclosure.sections", "enclosure.width"):
            if fields.by_field.get(field):
                fields.problems[field] = Problem(
                    kind="conflict", field=field, lines=["sections", "busbar", "form_kit"],
                    message=f"Depends on {', '.join(layout_doubt)}, which the documents give differently")
        sections = None
    else:
        sections = fields.number("enclosure.sections", "sections")
    sections_basis = ["enclosure.sections"]
    if sections is None and fields.ways() and not unit_problem and not layout_doubt:
        sections = 1 + math.ceil(units / rules.units_per_outgoing_section)
        sections_basis = [f"way.{w}.rating" for w in fields.ways()]
        fields.problems.pop("enclosure.sections", None)
    ip = fields.text("enclosure.ip_rating", "sections")
    if (sections or layout_doubt) and ip:  # one incomer section whatever the outgoing layout
        add(key="section.incomer", category="enclosure_section", quantity=1, ip_rating=ip,
            width_mm=rules.incomer_width_mm, description=f"Incomer section W{rules.incomer_width_mm} {ip}",
            basis=["enclosure.ip_rating"])
        if sections and sections > 1:
            add(key="section.outgoing", category="enclosure_section", quantity=int(sections) - 1, ip_rating=ip,
                width_mm=rules.outgoing_width_mm, description=f"Outgoing sections W{rules.outgoing_width_mm} {ip}",
                basis=["enclosure.ip_rating", *sections_basis])

    # Busbar per metre of board width: stated width, else from the sections.
    bus = fields.number("busbar.rating", "busbar", "A")
    width = None if layout_doubt else fields.number("enclosure.width", "busbar", "mm")
    width_basis = ["enclosure.width"]
    if width is None and sections:
        width = rules.incomer_width_mm + rules.outgoing_width_mm * (int(sections) - 1)
        width_basis = sections_basis
        fields.problems.pop("enclosure.width", None)
    if bus and width:
        add(key="busbar", category="busbar", quantity=round(width / 1000, 3), rating_a=int(bus),
            description=f"Busbar {int(bus)} A, {width / 1000:g} m", basis=["busbar.rating", *width_basis])

    # Form of separation kit, one per section.
    form = fields.text("enclosure.form", "form_kit")
    if form and sections and form.lower() in rules.forms_with_kit:
        add(key="form_kit", category="form_kit", quantity=int(sections), size=form.lower(),
            description=f"Form {form} kits", basis=["enclosure.form", *sections_basis])

    # Glands: one per outgoing cable (two for parallel cables), on the gland plate at the cable entry.
    for w in fields.ways():
        cable = fields.text(f"way.{w}.cable", f"gland.{w}")
        entry = fields.text("enclosure.cable_entry", f"gland.{w}")
        if not (cable and entry):
            continue
        gland = gland_for(cable, rules)
        if gland is None:
            fields.problems.setdefault(f"way.{w}.cable", Problem(
                kind="missing", field=f"way.{w}.cable", message=f"Cable {cable!r} not understood for gland sizing",
                lines=[f"gland.{w}"]))
            continue
        add(key=f"gland.{w}", category="cable_gland", quantity=gland[1], size=gland[0],
            description=f"Glands {gland[0]} for way {w}", basis=[f"way.{w}.cable", "enclosure.cable_entry"])
    return out


# --- 3 and 4. matching and pricing ----------------------------------------------------------------

def _money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def build(approved: list[ApprovedValue], items: list[CatalogueItem], rules: EstimateRules,
          approved_substitutes: set[tuple[str, str]] = frozenset(),
          open_values: list[ApprovedValue] | None = None) -> Draft:
    """The draft estimate from approved values only.

    ``approved_substitutes`` holds (requirement key, code) pairs the engineer approved.
    ``open_values`` are extracted values not yet reviewed: they are never priced and only
    show where documents disagree, so a conflict is reported as one and its dependants wait.
    """
    fields = Fields(approved, open_values)
    reqs = requirements(fields, rules)
    by_code = {i.code: i for i in items}
    decisions = []
    for r in reqs:
        m = match(r, items)
        ok = m.status == MatchStatus.EXACT or (m.status == MatchStatus.SUBSTITUTE
                                                and (r.key, m.code) in approved_substitutes)
        decisions.append(Decision(requirement=r, match=m, approved=ok))
    grouped: OrderedDict[str, PricedLine] = OrderedDict()
    for d in decisions:
        if not d.approved or d.match.code is None:
            continue
        part = by_code[d.match.code]
        qty = Decimal(str(d.requirement.quantity))
        line = grouped.get(part.code)
        if line is None:
            line = grouped[part.code] = PricedLine(code=part.code, description=part.description, quantity=Decimal(0),
                                                   unit=part.unit, unit_price=part.unit_price_gbp,
                                                   labour_hours=Decimal(0), materials=Decimal(0),
                                                   requirement_keys=[], basis=[])
        line.quantity += qty
        line.labour_hours += qty * part.labour_hours
        line.materials = _money(line.quantity * part.unit_price_gbp)
        line.requirement_keys.append(d.requirement.key)
        line.basis += [b for b in d.requirement.basis if b not in line.basis]
        if d.match.status == MatchStatus.SUBSTITUTE:
            line.substitute_reasons.append(d.match.reason)
    lines = list(grouped.values())
    materials = sum((ln.materials for ln in lines), Decimal(0))
    hours = sum((ln.labour_hours for ln in lines), Decimal(0))
    labour = _money(hours * rules.labour_rate_per_hour)
    subtotal = materials + labour
    margin = _money(subtotal * rules.margin_percent / 100)
    totals = Totals(materials=_money(materials), labour_hours=hours, labour=labour, subtotal=_money(subtotal),
                    margin=margin, total=_money(subtotal + margin))
    return Draft(lines=lines, decisions=decisions, problems=list(fields.problems.values()), totals=totals)
