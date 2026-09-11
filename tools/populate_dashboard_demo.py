"""Create a separate, synthetic Flight Ledger demonstration database."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from py_st.services.intelligence import Intelligence


def populate(root: Path) -> Path:
    database = root / ".state/intelligence.sqlite3"
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    store = Intelligence(database)
    scope = "DEMO-RESET:SYNTHETIC"
    try:
        waypoints: tuple[dict[str, Any], ...] = (
            {
                "symbol": "X-DEMO-A1",
                "systemSymbol": "X-DEMO",
                "type": "PLANET",
                "x": 0,
                "y": 0,
                "traits": [{"symbol": "MARKETPLACE"}],
            },
            {
                "symbol": "X-DEMO-B2",
                "systemSymbol": "X-DEMO",
                "type": "ORBITAL_STATION",
                "x": 34,
                "y": -18,
                "traits": [{"symbol": "SHIPYARD"}],
            },
            {
                "symbol": "X-DEMO-GATE",
                "systemSymbol": "X-DEMO",
                "type": "JUMP_GATE",
                "x": -22,
                "y": 25,
                "traits": [],
            },
            {
                "symbol": "X-DEMO-MOON",
                "systemSymbol": "X-DEMO",
                "type": "MOON",
                "x": 0,
                "y": 0,
            },
        )
        for waypoint in waypoints:
            store.observe(
                scope,
                "waypoint",
                waypoint["symbol"],
                waypoint,
                "synthetic-demo",
            )
        store.observe(
            scope,
            "agent",
            "SYNTHETIC",
            {"symbol": "SYNTHETIC", "credits": 123456},
            "synthetic-demo",
        )
        store.observe(
            scope,
            "market",
            "X-DEMO-A1",
            {
                "exports": [{"symbol": "FUEL"}],
                "tradeGoods": [
                    {
                        "symbol": "FUEL",
                        "purchasePrice": 72,
                        "sellPrice": 69,
                        "tradeVolume": 40,
                    }
                ],
            },
            "synthetic-demo",
        )
        store.observe(
            scope,
            "shipyard",
            "X-DEMO-B2",
            {"shipTypes": [{"type": "SHIP_PROBE"}], "ships": []},
            "synthetic-demo",
        )
        store.observe(
            scope,
            "jump_gate",
            "X-DEMO-GATE",
            {"symbol": "X-DEMO-GATE", "connections": []},
            "synthetic-demo",
        )
        for ship in (
            _ship("SYNTHETIC-1", "DOCKED", "X-DEMO-A1"),
            _ship(
                "SYNTHETIC-2",
                "IN_TRANSIT",
                "X-DEMO-B2",
                "X-DEMO-A1",
                "2099-01-01T00:10:00Z",
            ),
        ):
            store.observe(
                scope, "ship", ship["symbol"], ship, "synthetic-demo"
            )
    finally:
        store.close()
    return database


def _ship(
    symbol: str,
    status: str,
    destination: str,
    origin: str | None = None,
    arrival: str | None = None,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "nav": {
            "systemSymbol": "X-DEMO",
            "waypointSymbol": destination,
            "status": status,
            "flightMode": "CRUISE",
            "route": {
                "origin": {"symbol": origin or destination},
                "destination": {"symbol": destination},
                "arrival": arrival,
            },
        },
        "fuel": {"current": 100, "capacity": 100},
        "cargo": {"units": 0, "capacity": 40, "inventory": []},
        "cooldown": {"remainingSeconds": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(".cache/nightly/system-explorer-demo"),
    )
    args = parser.parse_args()
    database = populate(args.root)
    print(f"Created synthetic demo ledger: {database}")


if __name__ == "__main__":
    main()
