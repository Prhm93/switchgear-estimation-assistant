"""Parts catalogue: loading the CSV and matching requirements to parts.

Matching order:

1. **Exact**: same category, and every property the requirement states
   (rating, poles, IP rating, width, size) equals the part's. A breaking
   capacity is a minimum: the lowest one that is enough wins.
2. **Substitute**: when no rating matches exactly, the next *higher* rating
   with every other property exact. It is marked "substitute, needs review"
   with the reason, for example "250 A chosen, 200 A requested", and reaches
   the estimate only after the engineer approves it. A lower rating is never
   offered: it would be unsafe.
3. **Unmatched**: no safe part. The line is listed as unmatched and gets no
   price. Prices come only from the catalogue; nothing is guessed.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from backend.app.schemas import MatchResult, MatchStatus, Requirement


class CatalogueItem(BaseModel):
    """One row of ``data/catalogue/catalogue.csv`` (see its data dictionary)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    category: str
    description: str
    rating_a: int | None = None
    poles: int | None = None
    breaking_ka: int | None = None
    ip_rating: str | None = None
    width_mm: int | None = None
    size: str | None = None
    unit: str
    unit_price_gbp: Decimal
    labour_hours: Decimal


def _int(text: str) -> int | None:
    return int(text) if text.strip() else None


def _text(text: str) -> str | None:
    return text.strip() or None


def parse_catalogue(text: str) -> list[CatalogueItem]:
    rows = csv.DictReader(io.StringIO(text))
    return [CatalogueItem(code=r["code"], category=r["category"], description=r["description"],
                          rating_a=_int(r["rating_a"]), poles=_int(r["poles"]), breaking_ka=_int(r["breaking_ka"]),
                          ip_rating=_text(r["ip_rating"]), width_mm=_int(r["width_mm"]), size=_text(r["size"]),
                          unit=r["unit"], unit_price_gbp=Decimal(r["unit_price_gbp"]),
                          labour_hours=Decimal(r["labour_hours"]))
            for r in rows]


def load_catalogue(path: Path) -> list[CatalogueItem]:
    return parse_catalogue(path.read_text(encoding="utf-8"))


def _norm_size(s: str | None) -> str | None:
    return None if s is None else s.strip().upper().replace(" ", "")


def _fits_except_rating(item: CatalogueItem, req: Requirement) -> bool:
    return ((req.poles is None or item.poles == req.poles)
            and (req.min_breaking_ka is None or (item.breaking_ka is not None
                                                 and item.breaking_ka >= req.min_breaking_ka))
            and (req.ip_rating is None or (item.ip_rating or "").upper() == req.ip_rating.upper())
            and (req.width_mm is None or item.width_mm == req.width_mm)
            and (req.size is None or _norm_size(item.size) == _norm_size(req.size)))


def _wanted(req: Requirement) -> str:
    parts = [f"{req.rating_a} A" if req.rating_a is not None else None,
             f"{req.poles}P" if req.poles is not None else None,
             f"at least {req.min_breaking_ka} kA" if req.min_breaking_ka is not None else None,
             req.ip_rating, f"W{req.width_mm}" if req.width_mm is not None else None, req.size]
    return " ".join(p for p in parts if p) or "any"


def _pick(found: list[CatalogueItem]) -> CatalogueItem:
    return sorted(found, key=lambda i: (i.rating_a or 0, i.breaking_ka or 0, i.code))[0]


def match(req: Requirement, items: list[CatalogueItem]) -> MatchResult:
    """The part for one requirement: exact, substitute (needs review) or unmatched. Never a guess."""
    pool = [i for i in items if i.category == req.category]
    if not pool:
        return MatchResult(status=MatchStatus.UNMATCHED, reason=f"no {req.category} parts in the catalogue")
    fitting = [i for i in pool if _fits_except_rating(i, req)]
    exact = [i for i in fitting if req.rating_a is None or i.rating_a == req.rating_a]
    if exact:
        part = _pick(exact)
        note = ""
        if req.min_breaking_ka is not None and part.breaking_ka != req.min_breaking_ka:
            note = f"; {part.breaking_ka} kA is the lowest breaking capacity of at least {req.min_breaking_ka} kA"
        return MatchResult(status=MatchStatus.EXACT, code=part.code, reason=f"matches {_wanted(req)}{note}")
    if req.rating_a is not None:
        higher = [i for i in fitting if i.rating_a is not None and i.rating_a > req.rating_a]
        if higher:
            part = _pick(higher)
            return MatchResult(status=MatchStatus.SUBSTITUTE, code=part.code,
                               reason=f"{part.rating_a} A chosen, {req.rating_a} A requested: "
                                      f"no {req.rating_a} A part with the other properties")
    return MatchResult(status=MatchStatus.UNMATCHED, reason=f"no catalogue part for {req.category} {_wanted(req)}")
