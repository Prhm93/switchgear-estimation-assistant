"""The intended design of one switchboard, drawn at random from the catalogue.

A :class:`BoardDesign` is what the customer really wants. The documents are
written from it; planted problems then change what one document says (see
``planted.py``), never the design itself. The correct estimate is built from
the design.
"""

from __future__ import annotations

import math
import random
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from data_generator import catalogue as cat
from data_generator.names import CUSTOMERS, SITES, PEOPLE, BUILDING_LOADS

FAULT_LEVELS_KA = [25, 36, 50]
FORMS = ["2b", "3b", "4a", "4b"]
EARTHING = ["TN-S", "TN-C-S"]
CABLE_ENTRY = ["top", "bottom"]

# Cable sizes (mm2, 4-core armoured) and glands by device rating. Invented sizing table.
CABLE_BY_RATING: list[tuple[int, str, str]] = [
    (20, "4C 4 mm2 SWA", "M20"),
    (32, "4C 6 mm2 SWA", "M20"),
    (40, "4C 10 mm2 SWA", "M25"),
    (63, "4C 16 mm2 SWA", "M25"),
    (100, "4C 35 mm2 SWA", "M32"),
    (125, "4C 50 mm2 SWA", "M32"),
    (160, "4C 70 mm2 SWA", "M40"),
    (200, "4C 95 mm2 SWA", "M40"),
    (250, "4C 120 mm2 SWA", "M40"),
    (400, "4C 240 mm2 SWA", "M50"),
    (630, "2x 4C 185 mm2 SWA", "M63"),
    (800, "2x 4C 240 mm2 SWA", "M63"),
]
GLANDS_PER_WAY_ABOVE_400A = 2  # parallel cables


class Device(StrEnum):
    """Outgoing-way device types; the values match catalogue categories."""

    MCCB = "mccb"
    MCB = "mcb"
    SWITCH_DISCONNECTOR = "switch_disconnector"


DEVICE_LABEL = {Device.MCCB: "MCCB", Device.MCB: "MCB", Device.SWITCH_DISCONNECTOR: "SW-DISC"}
DEVICE_WORDS = {Device.MCCB: "MCCB", Device.MCB: "MCB", Device.SWITCH_DISCONNECTOR: "Switch-disconnector"}


class Way(BaseModel):
    """One outgoing way."""

    model_config = ConfigDict(extra="forbid")

    id: str  # "Q1", "Q2", ...
    description: str
    device: Device
    rating_a: int
    poles: int
    breaking_ka: int | None  # None for switch-disconnectors
    cable: str
    gland: str
    cable_length_m: int

    @property
    def units(self) -> int:
        """Mounting units the way takes in an outgoing section (4 units per section)."""
        return 2 if self.rating_a > 400 else 1

    @property
    def glands(self) -> int:
        return GLANDS_PER_WAY_ABOVE_400A if self.rating_a > 400 else 1


class BoardDesign(BaseModel):
    """The intended design of one low-voltage main switchboard."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    customer: str
    site: str
    building_use: str
    contact: str
    enquiry_ref: str
    issue_date: str  # ISO date, e.g. "2026-10-14"
    board_name: str
    voltage_v: int = 400
    frequency_hz: int = 50
    earthing: str
    fault_level_ka: int
    form: str
    ip_rating: str
    cable_entry: str
    incomer_rating_a: int
    incomer_poles: int
    busbar_rating_a: int
    meter: str  # "MFM" or "kWh"
    ways: list[Way] = Field(min_length=1)

    @property
    def ct_ratio(self) -> str:
        return f"{self.incomer_rating_a}/5"

    @property
    def outgoing_sections(self) -> int:
        return math.ceil(sum(w.units for w in self.ways) / 4)

    @property
    def sections(self) -> int:
        return 1 + self.outgoing_sections

    @property
    def width_mm(self) -> int:
        return cat.INCOMER_SECTION_WIDTH_MM + cat.OUTGOING_SECTION_WIDTH_MM * self.outgoing_sections

    def way(self, way_id: str) -> Way:
        for w in self.ways:
            if w.id == way_id:
                return w
        raise KeyError(way_id)


def cable_for(rating_a: int) -> tuple[str, str]:
    """Cable description and gland size for a device rating."""
    for limit, cable, gland in CABLE_BY_RATING:
        if rating_a <= limit:
            return cable, gland
    raise ValueError(f"no cable size for {rating_a} A")


def random_way(rng: random.Random, way_id: str, description: str, fault_level_ka: int,
               max_rating_a: int) -> Way:
    """One outgoing way whose device exists in the catalogue for this fault level."""
    choices: list[tuple[Device, int, int, int | None]] = []
    mccb_ratings = cat.MCCB_50KA_RATINGS if fault_level_ka > 36 else cat.MCCB_RATINGS
    for r in mccb_ratings:
        if r <= max_rating_a:
            for poles in ((4,) if fault_level_ka > 36 else (3, 4)):
                choices += [(Device.MCCB, r, poles, 50 if fault_level_ka > 36 else 36)] * 3
    if fault_level_ka <= 36:  # MCBs are used only where cascading is allowed
        choices += [(Device.MCB, r, 3, 10) for r in cat.MCB_RATINGS]
    choices += [(Device.SWITCH_DISCONNECTOR, r, 4, None) for r in cat.SD_RATINGS if r <= max_rating_a]
    device, rating, poles, ka = rng.choice(choices)
    cable, gland = cable_for(rating)
    return Way(id=way_id, description=description, device=device, rating_a=rating, poles=poles,
               breaking_ka=ka, cable=cable, gland=gland, cable_length_m=rng.randrange(8, 95))


def random_design(seed: int, project_id: str, n_ways: int | None = None) -> BoardDesign:
    """A random but valid board design. The same seed always gives the same design."""
    rng = random.Random(seed)
    fault = rng.choice(FAULT_LEVELS_KA)
    incomer = rng.choice(cat.ACB_RATINGS)
    poles = 4 if incomer not in (1250, 1600) or rng.random() < 0.7 else 3
    n = n_ways if n_ways is not None else rng.randint(4, 14)
    loads = rng.sample(BUILDING_LOADS, k=min(n, len(BUILDING_LOADS)))
    while len(loads) < n:
        loads.append(f"Spare {len(loads) + 1}")
    max_way = min(800, incomer // 2) if incomer >= 1250 else 400
    ways = [random_way(rng, f"Q{i + 1}", loads[i], fault, max_way) for i in range(n)]
    customer = rng.choice(CUSTOMERS)
    month, day = rng.randint(1, 10), rng.randint(1, 28)
    return BoardDesign(
        project_id=project_id,
        customer=customer.name,
        site=rng.choice(SITES),
        building_use=customer.use,
        contact=rng.choice(PEOPLE),
        enquiry_ref=f"ENQ-{rng.randint(1000, 9999)}",
        issue_date=f"2026-{month:02d}-{day:02d}",
        board_name=rng.choice(["MSB-1", "MSB-01", "LVMSB-A", "MSB-2", "LVP-1"]),
        earthing=rng.choice(EARTHING),
        fault_level_ka=fault,
        form=rng.choice(FORMS),
        ip_rating=rng.choice(cat.IP_RATINGS),
        cable_entry=rng.choice(CABLE_ENTRY),
        incomer_rating_a=incomer,
        incomer_poles=poles,
        busbar_rating_a=incomer,
        meter=rng.choice(cat.METER_TYPES),
        ways=ways,
    )
