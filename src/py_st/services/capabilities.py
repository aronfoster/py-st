"""Fresh GET-only planning evidence; never merge or write runtime caches."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from py_st.client.client import SpaceTradersClient
from py_st.client.transport import APIError

# Explicit field projection excludes descriptions, transactions, account IDs,
# response errors and any future API fields from publishable evidence.
COMPONENT = {"symbol": None, "capacity": None}
SHIP = {
    "symbol": None,
    "registration": {"role": None},
    "nav": {
        "systemSymbol": None,
        "waypointSymbol": None,
        "status": None,
        "flightMode": None,
    },
    "frame": COMPONENT,
    "modules": COMPONENT,
    "mounts": COMPONENT,
    "cargo": {"capacity": None, "units": None},
    "fuel": {"capacity": None, "current": None},
}
WAYPOINT = {
    "symbol": None,
    "type": None,
    "x": None,
    "y": None,
    "traits": {"symbol": None},
    "isUnderConstruction": None,
}
MARKET = {
    "symbol": None,
    "imports": COMPONENT,
    "exports": COMPONENT,
    "exchange": COMPONENT,
    "tradeGoods": {
        "symbol": None,
        "type": None,
        "tradeVolume": None,
        "supply": None,
        "activity": None,
        "purchasePrice": None,
        "sellPrice": None,
    },
}
SHIPYARD = {
    "symbol": None,
    "shipTypes": {"type": None},
    "ships": {
        "type": None,
        "purchasePrice": None,
        "frame": COMPONENT,
        "modules": COMPONENT,
        "mounts": COMPONENT,
    },
}
CONTRACT = {
    "type": None,
    "accepted": None,
    "fulfilled": None,
    "terms": {
        "deadline": None,
        "payment": {"onAccepted": None, "onFulfilled": None},
        "deliver": {
            "tradeSymbol": None,
            "destinationSymbol": None,
            "unitsRequired": None,
            "unitsFulfilled": None,
        },
    },
}


def project(value: Any, schema: Any) -> Any:
    """Keep only declared fields and simple identifier/date scalar values."""
    if schema is None:
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, str) and re.fullmatch(
            r"[A-Za-z0-9_:.+\-]{1,100}", value
        ):
            return value
        return None
    if isinstance(value, list):
        return [project(item, schema) for item in value]
    if not isinstance(value, dict):
        return None
    return {key: project(value.get(key), sub) for key, sub in schema.items()}


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def capability_snapshot(client: SpaceTradersClient) -> dict[str, Any]:
    """Inspect headquarters system, with at most 80 market/shipyard GETs.

    Authentication/reset failures abort immediately. Other unavailable reads
    become explicit unknowns; exception text/payloads never enter the report.
    """

    def observe(path: str, schema: Any, *, pages: bool = False) -> Any:
        try:
            data = client.request("GET", path, paginate=pages)
            if not isinstance(data, list if pages else dict):
                raise ValueError("Unexpected response shape")
            return {
                "state": "observed",
                "observed_at": timestamp(),
                "data": project(data, schema),
            }
        except APIError as exc:
            if exc.authentication_failed:
                raise
        except (httpx.HTTPError, ValueError):
            pass
        return {"state": "unknown", "reason": "read_unavailable", "data": None}

    started = timestamp()
    reset: Any = None
    try:
        reset = project(client.status().get("resetDate"), None)
    except APIError as exc:
        if exc.authentication_failed:
            raise
    except (httpx.HTTPError, ValueError):
        pass
    agent = observe(
        "/my/agent", {"symbol": None, "headquarters": None, "credits": None}
    )
    ships = observe("/my/ships", SHIP, pages=True)
    contracts = observe("/my/contracts", CONTRACT, pages=True)
    hq = (agent["data"] or {}).get("headquarters")
    system = hq.rsplit("-", 1)[0] if isinstance(hq, str) else None
    waypoints = (
        observe(f"/systems/{system}/waypoints", WAYPOINT, pages=True)
        if system
        else {
            "state": "unknown",
            "reason": "headquarters_unknown",
            "data": None,
        }
    )
    markets: list[dict[str, Any]] = []
    shipyards: list[dict[str, Any]] = []
    details = 0
    for waypoint in waypoints["data"] or []:
        symbol = waypoint["symbol"]
        if not isinstance(symbol, str):
            continue
        traits = {t["symbol"] for t in waypoint["traits"] or []}
        for trait, endpoint, schema, target, detail_field in (
            ("MARKETPLACE", "market", MARKET, markets, "tradeGoods"),
            ("SHIPYARD", "shipyard", SHIPYARD, shipyards, "ships"),
        ):
            if trait not in traits:
                continue
            observation: dict[str, Any]
            if details >= 80:
                observation = {
                    "state": "unknown",
                    "reason": "detail_budget",
                    "data": None,
                }
            else:
                details += 1
                observation = observe(
                    f"/systems/{system}/waypoints/{symbol}/{endpoint}", schema
                )
            data = observation["data"] or {}
            known = data.get(detail_field) is not None
            target.append(
                {
                    "waypoint": symbol,
                    **observation,
                    "details_state": "observed" if known else "unknown",
                    "details_unknown_reason": (
                        None if known else "not_returned_or_location_gated"
                    ),
                    "details_observed_at": (
                        observation.get("observed_at") if known else None
                    ),
                }
            )
    return {
        "schema_version": 1,
        "started_at": started,
        "completed_at": timestamp(),
        "reset": {"state": "observed" if reset else "unknown", "date": reset},
        "scope": {
            "system": system,
            "selection": "headquarters_system",
            "reachability": "same_system_candidates_not_route_verified",
            "other_systems": "deferred",
            "freshness": "fresh_GET_only_no_historical_cache",
        },
        "game_capabilities": {
            "evidence": "client endpoints and generated API models",
            "loops": [
                "trade",
                "contracts",
                "fleet_growth",
                "market_intelligence",
                "extraction",
                "survey",
                "siphon",
                "refining",
            ],
            "availability": "API_surface_is_not_live_execution_proof",
        },
        "account_observations": {
            "agent": agent,
            "ships": ships,
            "contracts": contracts,
        },
        "opportunity_observations": {
            "waypoints": waypoints,
            "markets": markets,
            "shipyards": shipyards,
        },
        "unknowns": [
            "Route fuel, cooldowns and execution feasibility not evaluated",
            "Extraction yields, survey deposits and refining recipes untested",
            "Mounts/modules and waypoint types are prerequisite evidence only",
            "Zero-capacity tanks are scout candidates, not movement proof",
            "Shipyard components describe offered ships, not standalone stock",
            "Missing prices are unknown, not zero or evidence of no market",
        ],
    }
