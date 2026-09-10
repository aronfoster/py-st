"""Shape scoped ledger observations for the read-only system explorer."""

from __future__ import annotations

from typing import Any

from py_st.services.intelligence import Intelligence


def _system(symbol: str, data: dict[str, Any]) -> str:
    value = data.get("systemSymbol")
    if isinstance(value, str) and value:
        return value
    return symbol.rsplit("-", 1)[0] if "-" in symbol else symbol


def system_explorer(store: Intelligence, scope: str) -> dict[str, Any]:
    """Return latest explorer evidence without crossing the supplied scope."""
    waypoints = store.latest(scope, "waypoint")
    markets = {row["key"]: row for row in store.latest(scope, "market")}
    shipyards = {row["key"]: row for row in store.latest(scope, "shipyard")}
    gates = {row["key"]: row for row in store.latest(scope, "jump_gate")}
    systems: dict[str, list[dict[str, Any]]] = {}
    for row in waypoints:
        data = row["data"] if isinstance(row["data"], dict) else {}
        symbol = row["key"]
        system = _system(symbol, data)
        traits = data.get("traits")
        trait_symbols = (
            [
                trait.get("symbol")
                for trait in traits
                if isinstance(trait, dict)
                and isinstance(trait.get("symbol"), str)
            ]
            if isinstance(traits, list)
            else None
        )
        market = markets.get(symbol)
        shipyard = shipyards.get(symbol)
        gate = gates.get(symbol)
        systems.setdefault(system, []).append(
            {
                "symbol": symbol,
                "type": data.get("type"),
                "x": data.get("x"),
                "y": data.get("y"),
                "traits": trait_symbols,
                "observed_at": row.get("observed_at"),
                "market": market,
                "shipyard": shipyard,
                "jump_gate": gate,
                "has_market": market is not None
                or "MARKETPLACE" in (trait_symbols or []),
                "has_shipyard": shipyard is not None
                or "SHIPYARD" in (trait_symbols or []),
                "has_jump_gate": gate is not None
                or data.get("type") == "JUMP_GATE",
            }
        )
    ships: list[dict[str, Any]] = []
    for row in store.latest(scope, "ship"):
        ship_data: dict[str, Any] = (
            row["data"] if isinstance(row["data"], dict) else {}
        )
        nav_value = ship_data.get("nav")
        nav: dict[str, Any] = nav_value if isinstance(nav_value, dict) else {}
        route_value = nav.get("route")
        route: dict[str, Any] = (
            route_value if isinstance(route_value, dict) else {}
        )
        origin_value = route.get("origin")
        origin: dict[str, Any] = (
            origin_value if isinstance(origin_value, dict) else {}
        )
        destination_value = route.get("destination")
        destination: dict[str, Any] = (
            destination_value if isinstance(destination_value, dict) else {}
        )
        ships.append(
            {
                "symbol": ship_data.get("symbol", row["key"]),
                "status": nav.get("status"),
                "waypoint": nav.get("waypointSymbol"),
                "system": nav.get("systemSymbol"),
                "origin": origin.get("symbol"),
                "destination": destination.get("symbol"),
                "arrival": route.get("arrival"),
                "observed_at": row.get("observed_at"),
            }
        )
    return {
        "systems": [
            {
                "symbol": symbol,
                "waypoints": sorted(points, key=lambda p: p["symbol"]),
            }
            for symbol, points in sorted(systems.items())
        ],
        "ships": ships,
    }
