from __future__ import annotations

from pydantic import BaseModel, Field

from py_st.models import Cooldown, ShipCargo


class RefineItem(BaseModel):
    """A good that was produced or consumed in a refining process."""

    tradeSymbol: str = Field(..., description="Symbol of the good.")
    units: int = Field(..., description="Amount of units of the good.")


class RefineResult(BaseModel):
    """The result of a successful refining process."""

    cargo: ShipCargo
    cooldown: Cooldown
    produced: list[RefineItem]
    consumed: list[RefineItem]
