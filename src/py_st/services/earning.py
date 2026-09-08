"""Bounded decisions over existing fleet, trade and scout services."""

from __future__ import annotations

from typing import Any, cast

from py_st.client.transport import JSONList
from py_st.services.automation import SafetyStop, Session
from py_st.services.scouting import scout_run
from py_st.services.strategies import fleet_run, trade_run


def earn_run(
    run: Session, system: str, cycles: int = 3, max_age: int = 900
) -> dict[str, Any]:
    if not 1 <= cycles <= 5 or not 1 <= max_age <= 86400:
        raise ValueError("Bounds: 1..5 cycles, 1..86400 max-age seconds")
    decisions: list[dict[str, Any]] = []
    visited: set[str] = set()
    for _ in range(cycles):
        run.check()
        state = run.refresh()
        if run.store.pending(run.scope):
            raise SafetyStop("Pending action requires explicit reconciliation")
        if any(
            c["accepted"] and not c["fulfilled"] for c in state["contracts"]
        ):
            raise SafetyStop(
                "Earn blocked by contract obligations; fulfill first"
            )
        positions = [
            p
            for p in run.store.latest(run.scope, "position")
            if p["data"]["status"] != "closed"
        ]
        if positions:
            if len(positions) != 1 or any(
                not p["key"].startswith("trade:")
                or p["data"]["status"] != "open"
                for p in positions
            ):
                raise SafetyStop(
                    "Multiple/unknown positions; inspect recovery first"
                )
            # Recovery is account-wide and terminal, even for another system.
            return {"status": "recovery only", "result": fleet_run(run)}
        if not any(s["nav"]["systemSymbol"] == system for s in state["ships"]):
            raise SafetyStop("Earn requires an owned ship in the same system")
        if not decisions:
            run.check()
            waypoints = cast(
                JSONList,
                run.client.request(
                    "GET", f"/systems/{system}/waypoints", paginate=True
                ),
            )
            for waypoint in waypoints:
                run.check()
                run.store.observe(
                    run.scope, "waypoint", waypoint["symbol"], waypoint
                )
        fleet = fleet_run(run, plan_only=True, system=system)
        if "resume" in fleet:
            raise SafetyStop("Position appeared during planning; resume first")
        selected = next(
            (p for p in fleet["candidates"] if p["fuel_ready"]), None
        )
        decision = {
            "cycle": len(decisions) + 1,
            "kind": "trade" if selected else "discover",
            "selected": selected,
            "remaining_actions": run.remaining,
        }
        run.store.observe(
            run.scope, "plan", f"earn:{system}", decision, "strategy"
        )
        if selected:
            decision["result"] = trade_run(
                run,
                selected["hauler"],
                selected["source"],
                selected["destination"],
                selected["good"],
                cycles=1,
            )
        else:
            discovery = scout_run(
                run, system, attempts=1, max_age=max_age, excluded=visited
            )
            decision["result"] = discovery
            visited.update(v["target"] for v in discovery.get("visits", []))
        decisions.append(decision)
        if not run.execute:
            return {"status": "dry run", "decisions": decisions}
        if not selected and not discovery["visits"]:
            return {
                "status": "no ready routes or scout targets",
                "decisions": decisions,
            }
    return {"status": "cycle limit", "decisions": decisions}
