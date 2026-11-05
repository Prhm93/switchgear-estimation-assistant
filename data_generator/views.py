"""What one document says, as opposed to what the customer really wants.

Each document is written from a :class:`DocView`: a copy of the design plus
the planted changes for that document (left out, "TBC", no unit, a hidden
line). Keeping these apart from the design is what makes the answer key exact.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from data_generator.design import BoardDesign


class DocView(BaseModel):
    """The design as one document states it."""

    model_config = ConfigDict(extra="forbid")

    design: BoardDesign
    omit: set[str] = Field(default_factory=set)  # fields the document does not state
    tbc: set[str] = Field(default_factory=set)  # fields stated as "TBC"
    no_unit: set[str] = Field(default_factory=set)  # fields stated without a unit
    injection: str | None = None  # a hidden instruction line (prompt-injection test)

    def states(self, field: str) -> bool:
        """True when the document states ``field`` at all."""
        return field not in self.omit
