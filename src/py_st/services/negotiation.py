"""One offer request, never acceptance or automatic retry of negotiation."""

from typing import Any

from py_st.services.automation import SafetyStop, Session


def negotiate_run(run: Session, symbol: str) -> dict[str, Any]:
    run.check()
    state = run.refresh()
    ship = next((s for s in state["ships"] if s["symbol"] == symbol), None)
    if ship is None:
        raise SafetyStop("Ship not found in fresh fleet; use its full symbol")
    nav = ship["nav"]
    waypoint = run.get(
        f"/systems/{nav['systemSymbol']}/waypoints/{nav['waypointSymbol']}"
    )
    run.store.observe(run.scope, "waypoint", waypoint["symbol"], waypoint)
    contracts = {c["id"]: c for c in state["contracts"]}
    active = [c for c in contracts.values() if not c["fulfilled"]]
    blockers = []
    if run.store.pending(run.scope):
        blockers.append("Pending action: reconcile before negotiation")
    if active:
        blockers.append(
            "Existing unfulfilled contract(s); inspect instead of negotiating"
        )
    if any(
        c["id"] not in contracts
        for c in run.store.negotiated_contracts(run.scope)
    ):
        blockers.append(
            "Journaled offer missing from fresh list; review, never replay"
        )
    if nav["status"] not in ("DOCKED", "IN_ORBIT"):
        blockers.append("Ship must be stationary; no automatic arrival wait")
    faction = waypoint.get("faction", {}).get("symbol")
    if not faction:
        blockers.append("Current waypoint has no faction")
    plan = {
        "ship": symbol,
        "waypoint": waypoint["symbol"],
        "nav_status": nav["status"],
        "faction": faction,
        "cooldown": ship.get("cooldown"),
        "cooldown_note": "Negotiation docs specify no cooldown prerequisite; "
        "reported only. Server rejection stops without retry.",
        "contract_limit": 1,
        "eligibility_note": "Conservatively block all unfulfilled contracts, "
        "including expired offers, until reviewed. Dock/orbit both permitted.",
        "contracts": active,
        "blockers": blockers,
        "eligible": not blockers,
        "note": "One offer POST only; no acceptance, travel or spending. "
        "Existing FOS-63 authority covers guarded negotiation.",
    }
    run.store.observe(run.scope, "plan", f"negotiate:{symbol}", plan)
    if not run.execute:
        return {"status": "dry run", "plan": plan}
    if blockers:
        raise SafetyStop("; ".join(blockers))
    result = run.mutate(f"/my/ships/{symbol}/negotiate/contract")
    refreshed = run.refresh()
    if not any(
        c["id"] == result["contract"]["id"] for c in refreshed["contracts"]
    ):
        raise SafetyStop("Offer journaled but missing from refresh; review")
    return {
        "status": "offer negotiated; not accepted",
        "contract": result["contract"],
        "plan": plan,
    }
