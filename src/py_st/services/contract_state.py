"""Shared contract observation admission for procurement workflows."""

from __future__ import annotations

from typing import Any, cast

from py_st.services.automation import SafetyStop


def select_contract(contracts: Any, contract_id: str) -> dict[str, Any]:
    """Reject ambiguous identity and flags before using obligation evidence."""
    if not isinstance(contracts, list) or any(
        not isinstance(c, dict)
        or not isinstance(c.get("id"), str)
        or not c["id"]
        or any(type(c.get(k)) is not bool for k in ("accepted", "fulfilled"))
        for c in contracts
    ):
        raise SafetyStop(
            "Invalid contract identity or acceptance/fulfillment flags"
        )
    ids = [c["id"] for c in contracts]
    if len(set(ids)) != len(ids):
        raise SafetyStop("Fresh contracts must be uniquely present")
    matches = [c for c in contracts if c["id"] == contract_id]
    if not matches:
        raise SafetyStop("Contract not found")
    return cast(dict[str, Any], matches[0])
