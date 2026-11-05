"""Invented names used in generated documents.

Every organisation name contains "Example" or "Sample" so it cannot be
mistaken for a real company. :data:`COMPANY_ALLOWLIST` is the complete list of
organisation names the generator may write; the tests check that every
company-like name in the generated files is on it.
"""

from __future__ import annotations

from typing import NamedTuple


class Customer(NamedTuple):
    name: str
    use: str  # what the building is, in plain words


PANEL_BUILDER = "Example Panels Ltd"
CONSULTANT = "Sample Building Services Consultants Ltd"

CUSTOMERS: list[Customer] = [
    Customer("Ashvale Example Estates Ltd", "office building"),
    Customer("Brindlemoor Sample Healthcare Trust", "outpatient clinic"),
    Customer("Corrin Example Logistics Ltd", "distribution warehouse"),
    Customer("Dunmere Sample Foods Ltd", "food processing plant"),
    Customer("Elstow Example Water Ltd", "pumping station"),
    Customer("Farrowdale Sample Schools Trust", "secondary school"),
    Customer("Glenhurst Example Data Ltd", "data hall"),
    Customer("Harlow Fen Sample Retail Ltd", "retail park"),
    Customer("Ingleby Example Housing Ltd", "apartment block"),
    Customer("Juniper Vale Sample Labs Ltd", "research laboratory"),
    Customer("Kestrel Example Leisure Ltd", "leisure centre"),
    Customer("Larchmont Sample Hotels Ltd", "hotel"),
]

COMPANY_ALLOWLIST: frozenset[str] = frozenset(
    [PANEL_BUILDER, CONSULTANT, *(c.name for c in CUSTOMERS)]
)

SITES = [
    "Unit 4, Example Business Park, Sampletown",
    "Plot 12, Sample Road, Exampleton",
    "North Site, Example Way, Samplebury",
    "Block C, Sample Quay, Exampleford",
    "Phase 2, Example Lane, Sampleham",
]

# Generic invented names for letter sign-offs and drawing initials.
PEOPLE = ["R. Marsh", "S. Okafor", "L. Novak", "T. Brennan", "M. Haddad", "C. Lindqvist", "A. Ferreira"]
INITIALS = ["JM", "AK", "RT", "SB", "NP", "DW", "EH"]

BUILDING_LOADS = [
    "Chiller 1", "Chiller 2", "AHU 1", "AHU 2", "Lift motor room", "Small power DB-L1",
    "Small power DB-L2", "Lighting DB-L1", "Lighting DB-L2", "Kitchen DB", "Fire pump",
    "Sprinkler pump", "EV chargers", "Server room UPS", "Mech services panel", "Boiler house",
    "External lighting", "Car park ventilation", "Workshop DB", "Spare",
]
