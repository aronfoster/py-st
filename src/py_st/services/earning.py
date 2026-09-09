"""Bounded decisions over existing fleet, trade and scout services."""

from __future__ import annotations

from typing import Any, cast

from py_st.client.transport import JSONList
from py_st.services.automation import SafetyStop, Session
from py_st.services.repositioning import reposition_plan, reposition_run
from py_st.services.scouting import scout_run
from py_st.services.strategies import fleet_run, refuel_run, trade_run


def earn_run(
    run: Session,
    system: str,
    cycles: int = 3,
    max_age: int = 900,
    *,
    reposition: bool = False,
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
            if p["data"].get("status") != "closed"
        ]
        if positions:
            if (
                len(positions) == 1
                and positions[0]["key"].startswith("reposition:")
                and positions[0]["data"].get("status") == "open"
            ):
                return {
                    "status": "recovery only",
                    "result": reposition_run(
                        run, positions[0]["data"].get("plan", {})
                    ),
                }
            if len(positions) != 1 or any(
                not p["key"].startswith("trade:")
                or p["data"].get("status") != "open"
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
        if selected is None:
            for candidate in fleet["candidates"]:
                try:
                    refill = refuel_run(
                        run,
                        candidate["hauler"],
                        trade=candidate,
                        plan_only=True,
                    )
                except SafetyStop:
                    # Candidate economics may fail; global stops must not turn
                    # into permission to scout instead.
                    run.check()
                    if run.store.pending(run.scope) or any(
                        c["accepted"] and not c["fulfilled"]
                        for c in run.refresh()["contracts"]
                    ):
                        raise
                    continue
                selected = candidate | {"refill": refill}
                break
        return_plan = None
        if selected is None and reposition:
            return_plan = reposition_plan(run, system, max_age)
            if return_plan["status"] != "declined":
                decision = {
                    "cycle": len(decisions) + 1,
                    "kind": "reposition",
                    "selected": return_plan,
                    "remaining_actions": run.remaining,
                }
                run.store.observe(
                    run.scope, "plan", f"earn:{system}", decision, "strategy"
                )
                if return_plan["status"] == "ready":
                    decision["result"] = reposition_run(run, return_plan)
                decisions.append(decision)
                return {
                    "status": (
                        "dry run"
                        if not run.execute
                        else (
                            "reposition blocked"
                            if return_plan["status"] == "blocked"
                            else "recovery only"
                        )
                    ),
                    "decisions": decisions,
                }
        decision = {
            "cycle": len(decisions) + 1,
            "kind": "trade" if selected else "discover",
            "selected": selected,
            "remaining_actions": run.remaining,
        }
        if return_plan:
            decision["reposition"] = return_plan
        run.store.observe(
            run.scope, "plan", f"earn:{system}", decision, "strategy"
        )
        if selected:
            if any(
                p["key"] == f"reposition:{selected['hauler']}"
                and p["data"].get("status") == "closed"
                and p["data"].get("plan", {}).get("source")
                == selected["source"]
                for p in run.store.latest(run.scope, "position")
            ) and not any(
                g["symbol"] == "FUEL"
                and g.get("purchasePrice", 0) > 0
                and g.get("tradeVolume", 0) > 0
                for g in run.market(selected["source"]).get("tradeGoods", [])
            ):
                raise SafetyStop(
                    "Returned source needs fresh usable FUEL; no purchase"
                )
            decision["result"] = trade_run(
                run,
                selected["hauler"],
                selected["source"],
                selected["destination"],
                selected["good"],
                cycles=1,
                require_source=True,
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
