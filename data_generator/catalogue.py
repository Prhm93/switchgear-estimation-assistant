"""The invented parts catalogue: build it, write it, read it, and match parts.

Every part, code and price here is invented. The catalogue is built from fixed
rules plus a seeded price jitter, so ``build_catalogue()`` always returns the
same rows. The committed file ``data/catalogue/catalogue.csv`` is checked
against it by the tests.

The generator only designs boards from parts that exist in this catalogue, so
every correct estimate line has a real catalogue code.
"""

from __future__ import annotations

import csv
import io
import random
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CATALOGUE_SEED = 7310
CSV_COLUMNS = [
    "code",
    "category",
    "description",
    "rating_a",
    "poles",
    "breaking_ka",
    "ip_rating",
    "width_mm",
    "size",
    "unit",
    "unit_price_gbp",
    "labour_hours",
]


class Category(StrEnum):
    ACB = "acb"
    MCCB = "mccb"
    MCB = "mcb"
    SWITCH_DISCONNECTOR = "switch_disconnector"
    CT = "current_transformer"
    METER = "meter"
    BUSBAR = "busbar"
    SECTION = "enclosure_section"
    FORM_KIT = "form_kit"
    GLAND = "cable_gland"


class Part(BaseModel):
    """One catalogue row. Empty CSV cells are ``None``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^PRT-\d{4}$")
    category: Category
    description: str
    rating_a: int | None = None
    poles: int | None = None
    breaking_ka: int | None = None
    ip_rating: str | None = None
    width_mm: int | None = None
    size: str | None = None  # CT ratio, gland thread, meter type or form of separation
    unit: str  # "each" or "m"
    unit_price_gbp: float = Field(gt=0)
    labour_hours: float = Field(ge=0)


# Ratings offered per device family. The generator picks only from these.
ACB_RATINGS = [800, 1000, 1250, 1600, 2000, 2500]
MCCB_RATINGS = [100, 125, 160, 200, 250, 400, 630]
MCCB_50KA_RATINGS = [250, 400, 630]  # 4-pole only
MCB_RATINGS = [16, 20, 32, 40, 63]
SD_RATINGS = [125, 250, 400, 630, 800]
IP_RATINGS = ["IP31", "IP42", "IP54"]
FORMS_WITH_KIT = ["3b", "4a", "4b"]  # Form 2b needs no separation kit
GLAND_SIZES = ["M20", "M25", "M32", "M40", "M50", "M63"]
METER_TYPES = ["MFM", "kWh"]

INCOMER_SECTION_WIDTH_MM = 800
OUTGOING_SECTION_WIDTH_MM = 600


def build_catalogue() -> list[Part]:
    """Return the full catalogue in code order. Deterministic."""
    rng = random.Random(CATALOGUE_SEED)

    def price(base: float) -> float:
        # Invented prices: a base figure with up to +/-6 % jitter, to the penny.
        return round(base * rng.uniform(0.94, 1.06), 2)

    parts: list[Part] = []

    def add(block: int, **fields: object) -> None:
        index = sum(1 for p in parts if int(p.code[4:]) // 100 == block)
        parts.append(Part(code=f"PRT-{block * 100 + index + 1:04d}", **fields))  # type: ignore[arg-type]

    # 01xx air circuit breakers (incomers), 4-pole, 50 kA, withdrawable.
    for r in ACB_RATINGS:
        add(1, category=Category.ACB, description=f"Air circuit breaker {r} A 4P 50 kA withdrawable",
            rating_a=r, poles=4, breaking_ka=50, unit="each",
            unit_price_gbp=price(2400 + 2.6 * r), labour_hours=round(3.0 + r / 1000, 1))
    for r in [1250, 1600]:
        add(1, category=Category.ACB, description=f"Air circuit breaker {r} A 3P 50 kA withdrawable",
            rating_a=r, poles=3, breaking_ka=50, unit="each",
            unit_price_gbp=price(2100 + 2.3 * r), labour_hours=round(3.0 + r / 1000, 1))

    # 02xx moulded-case circuit breakers.
    for poles in (3, 4):
        for r in MCCB_RATINGS:
            add(2, category=Category.MCCB, description=f"Moulded-case circuit breaker {r} A {poles}P 36 kA",
                rating_a=r, poles=poles, breaking_ka=36, unit="each",
                unit_price_gbp=price((180 + 1.9 * r) * (1.25 if poles == 4 else 1.0)),
                labour_hours=round(0.8 + r / 500, 1))
    for r in MCCB_50KA_RATINGS:
        add(2, category=Category.MCCB, description=f"Moulded-case circuit breaker {r} A 4P 50 kA",
            rating_a=r, poles=4, breaking_ka=50, unit="each",
            unit_price_gbp=price((260 + 2.4 * r) * 1.25), labour_hours=round(0.9 + r / 500, 1))

    # 03xx miniature circuit breakers, 3-pole, 10 kA.
    for r in MCB_RATINGS:
        add(3, category=Category.MCB, description=f"Miniature circuit breaker {r} A 3P 10 kA type C",
            rating_a=r, poles=3, breaking_ka=10, unit="each",
            unit_price_gbp=price(38 + 0.9 * r), labour_hours=0.4)

    # 04xx switch-disconnectors, 4-pole.
    for r in SD_RATINGS:
        add(4, category=Category.SWITCH_DISCONNECTOR, description=f"Switch-disconnector {r} A 4P",
            rating_a=r, poles=4, unit="each", unit_price_gbp=price(140 + 1.1 * r),
            labour_hours=round(0.7 + r / 800, 1))

    # 05xx current transformers for incomer metering, x/5 A.
    for r in ACB_RATINGS:
        add(5, category=Category.CT, description=f"Current transformer {r}/5 A class 1",
            rating_a=r, size=f"{r}/5", unit="each", unit_price_gbp=price(62 + 0.03 * r), labour_hours=0.3)

    # 06xx meters.
    add(6, category=Category.METER, description="Multifunction power meter, panel mounted",
        size="MFM", unit="each", unit_price_gbp=price(310), labour_hours=1.0)
    add(6, category=Category.METER, description="kWh energy meter, panel mounted",
        size="kWh", unit="each", unit_price_gbp=price(145), labour_hours=0.8)

    # 07xx copper busbar systems, priced per metre of board.
    for r in ACB_RATINGS:
        add(7, category=Category.BUSBAR, description=f"Busbar system {r} A TP&N, per metre",
            rating_a=r, poles=4, unit="m", unit_price_gbp=price(180 + 0.42 * r),
            labour_hours=round(1.5 + r / 1000, 1))

    # 08xx enclosure sections, per IP rating.
    for ip in IP_RATINGS:
        uplift = {"IP31": 1.0, "IP42": 1.08, "IP54": 1.22}[ip]
        add(8, category=Category.SECTION, description=f"Incomer section W{INCOMER_SECTION_WIDTH_MM} H2200 {ip}",
            ip_rating=ip, width_mm=INCOMER_SECTION_WIDTH_MM, unit="each",
            unit_price_gbp=price(1650 * uplift), labour_hours=6.0)
        add(8, category=Category.SECTION, description=f"Outgoing section W{OUTGOING_SECTION_WIDTH_MM} H2200 {ip}",
            ip_rating=ip, width_mm=OUTGOING_SECTION_WIDTH_MM, unit="each",
            unit_price_gbp=price(1180 * uplift), labour_hours=4.5)

    # 09xx form of separation kits, one per section.
    for form, base in zip(FORMS_WITH_KIT, (260, 390, 470)):
        add(9, category=Category.FORM_KIT, description=f"Form {form} separation kit, per section",
            size=form, unit="each", unit_price_gbp=price(base), labour_hours=2.0)

    # 10xx cable glands, brass, for armoured cable.
    for g, base in zip(GLAND_SIZES, (4.2, 5.8, 8.9, 13.5, 21.0, 32.0)):
        add(10, category=Category.GLAND, description=f"Cable gland {g} brass, armoured cable",
            size=g, unit="each", unit_price_gbp=price(base), labour_hours=0.2)

    return parts


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def catalogue_csv_text(parts: list[Part]) -> str:
    """The CSV text, with LF line endings, so it is byte-identical everywhere."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for p in parts:
        row = p.model_dump()
        writer.writerow([_cell(row[c]) if c != "category" else p.category.value for c in CSV_COLUMNS])
    return out.getvalue()


def write_catalogue(path: Path) -> None:
    """Write the catalogue CSV to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(catalogue_csv_text(build_catalogue()).encode("utf-8"))


def load_catalogue(path: Path) -> list[Part]:
    """Read and validate a catalogue CSV."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [Part(**{k: (v if v != "" else None) for k, v in row.items()}) for row in rows]


class NoMatchingPart(LookupError):
    """No catalogue part fits the request."""


def match_part(
    parts: list[Part],
    category: Category,
    *,
    rating_a: int | None = None,
    poles: int | None = None,
    min_breaking_ka: int | None = None,
    ip_rating: str | None = None,
    width_mm: int | None = None,
    size: str | None = None,
) -> Part:
    """The one part that fits. Breaking capacity is a minimum; the lowest one that fits wins.

    Raises :class:`NoMatchingPart` when nothing fits. Never guesses.
    """
    found = [
        p
        for p in parts
        if p.category == category
        and (rating_a is None or p.rating_a == rating_a)
        and (poles is None or p.poles == poles)
        and (min_breaking_ka is None or (p.breaking_ka is not None and p.breaking_ka >= min_breaking_ka))
        and (ip_rating is None or p.ip_rating == ip_rating)
        and (width_mm is None or p.width_mm == width_mm)
        and (size is None or p.size == size)
    ]
    if not found:
        raise NoMatchingPart(
            f"no {category.value} with rating={rating_a} poles={poles} "
            f"min_kA={min_breaking_ka} ip={ip_rating} width={width_mm} size={size}"
        )
    found.sort(key=lambda p: (p.breaking_ka or 0, p.code))
    return found[0]
