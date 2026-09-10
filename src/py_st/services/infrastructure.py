"""Bounded GET-only infrastructure observations, never execution authority."""

from __future__ import annotations

import re
from typing import Any, cast

from py_st.client.transport import JSONList, RequestAborted
from py_st.services.automation import SafetyStop, Session


def validate_infrastructure(
    system: str, max_sites: int = 10, seconds: int = 300
) -> None:
    if (
        not isinstance(system, str)
        or len(system) > 100
        or not re.fullmatch(r"[A-Z0-9]+-[A-Z0-9]+", system)
    ):
        raise ValueError("Valid system symbol required (e.g. X1-ABC)")
    if type(max_sites) is not int or not 1 <= max_sites <= 100:
        raise ValueError("max_sites must be an integer from 1 to 100")
    if type(seconds) is not int or not 1 <= seconds <= 7200:
        raise ValueError("seconds must be an integer from 1 to 7200")


def infrastructure_run(
    run: Session, system: str, max_sites: int = 10
) -> dict[str, Any]:
    """Use the session deadline and SDK pagination; count sites, not pages.

    Interrupted SDK pagination returns no waypoints, so discovery remaining
    stays unknown. Already stored waypoint/endpoint observations are retained.
    """
    validate_infrastructure(system, max_sites)
    result: dict[str, Any] = {
        "system": system,
        "execution_authorized": False,
        "status": "complete",
        "discovery_complete": False,
        "max_sites": max_sites,
        "site_attempts": 0,
        "waypoint_count": 0,
        "sites": [],
        "counts": {"jump_gates": 0, "shipyards": 0, "construction": 0},
        "note": "Observations only; connections are not proof of jump ability."
        " Missing prices and construction details remain unknown.",
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    completed = 0
    try:
        run.check()
        run.refresh()
        run.check()
        waypoints = cast(
            JSONList,
            run.client.request(
                "GET", f"/systems/{system}/waypoints", paginate=True
            ),
        )
        for waypoint in waypoints:
            run.check()
            symbol = waypoint["symbol"]
            if waypoint["systemSymbol"] != system or not re.fullmatch(
                re.escape(system) + r"-[A-Z0-9]+", symbol
            ):
                raise SafetyStop("Waypoint does not match requested system")
            run.store.observe(run.scope, "waypoint", symbol, waypoint)
            if symbol in seen:
                continue
            seen.add(symbol)
            result["waypoint_count"] = len(seen)
            if (
                waypoint["type"] == "JUMP_GATE"
                or any(t["symbol"] == "SHIPYARD" for t in waypoint["traits"])
                or waypoint.get("isUnderConstruction") is True
            ):
                candidates.append(waypoint)
        run.check()
        result["discovery_complete"] = True

        for waypoint in candidates:
            if result["site_attempts"] >= max_sites:
                result["status"] = "site limit"
                break
            run.check()
            result["site_attempts"] += 1
            symbol = waypoint["symbol"]
            site: dict[str, Any] = {
                "symbol": symbol,
                "construction_status": (
                    "unknown"
                    if waypoint.get("isUnderConstruction") is not False
                    else "not under construction"
                ),
            }
            result["sites"].append(site)
            for suffix, kind, field, matches in (
                (
                    "jump-gate",
                    "jump_gate",
                    "jump_gates",
                    waypoint["type"] == "JUMP_GATE",
                ),
                (
                    "shipyard",
                    "shipyard",
                    "shipyards",
                    any(t["symbol"] == "SHIPYARD" for t in waypoint["traits"]),
                ),
                (
                    "construction",
                    "construction",
                    "construction",
                    waypoint.get("isUnderConstruction") is True,
                ),
            ):
                if not matches:
                    continue
                run.check()
                data = run.get(
                    f"/systems/{system}/waypoints/{symbol}/{suffix}"
                )
                if data.get("symbol") != symbol:
                    raise SafetyStop("Infrastructure response symbol mismatch")
                run.store.observe(run.scope, kind, symbol, data)
                site[kind] = data
                result["counts"][field] += 1
                if kind == "shipyard":
                    site["price_status"] = (
                        "observed quotes; unquoted types unknown"
                        if data.get("ships")
                        else "unknown"
                    )
                elif kind == "construction":
                    site["construction_status"] = (
                        "complete"
                        if data.get("isComplete") is True
                        else (
                            "under construction"
                            if data.get("isComplete") is False
                            else "unknown"
                        )
                    )
            completed += 1
        run.check()
    except (SafetyStop, RequestAborted) as exc:
        stop = exc.__cause__ if isinstance(exc, RequestAborted) else exc
        if not isinstance(stop, SafetyStop) or not str(stop).startswith(
            ("STOP sentinel", "Wall-clock budget")
        ):
            raise
        result["status"] = (
            "stopped" if str(stop).startswith("STOP") else "time limit"
        )
    result["scope"] = run.scope
    result["remaining_sites"] = len(candidates) - completed
    result["remaining_unknown"] = not result["discovery_complete"]
    result["truncated"] = result["status"] != "complete"
    return result
