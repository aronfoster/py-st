from __future__ import annotations

from pydantic import BaseModel, Field

from py_st._generated.models import (
    Agent,
    Contract,
    Cooldown,
    Faction,
    Ship,
    ShipCargo,
)


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


class RegisterAgentResponseData(BaseModel):
    """Holds the nested 'data' from a successful agent registration."""

    agent: Agent
    contract: Contract
    faction: Faction
    ships: list[Ship]
    token: str


class RegisterAgentResponse(BaseModel):
    """Models the top-level response from POST /register."""

    data: RegisterAgentResponseData
