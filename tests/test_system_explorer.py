from pathlib import Path

from py_st.services.intelligence import Intelligence
from py_st.services.system_explorer import system_explorer


def test_explorer_shapes_details_transit_and_missing_data(
    tmp_path: Path,
) -> None:
    store = Intelligence(tmp_path / "ledger.sqlite3")
    waypoint = {
        "symbol": "X-A-1",
        "systemSymbol": "X-A",
        "type": "PLANET",
        "x": 4,
        "y": 4,
        "traits": [{"symbol": "MARKETPLACE"}],
    }
    store.observe("r:a", "waypoint", "X-A-1", waypoint, "test")
    store.observe("r:a", "market", "X-A-1", {"tradeGoods": []}, "test")
    store.observe(
        "r:a",
        "ship",
        "A-1",
        {
            "symbol": "A-1",
            "nav": {
                "status": "IN_TRANSIT",
                "waypointSymbol": "X-A-1",
                "route": {
                    "origin": {"symbol": "X-A-2"},
                    "destination": {"symbol": "X-A-1"},
                    "arrival": "2099-01-01T00:00:00Z",
                },
            },
        },
        "test",
    )

    result = system_explorer(store, "r:a")

    point = result["systems"][0]["waypoints"][0]
    assert point["market"]["data"]["tradeGoods"] == []
    assert point["shipyard"] is None
    assert result["ships"][0]["observed_at"]
    assert result["ships"][0]["origin"] == "X-A-2"
    assert result["ships"][0]["destination"] == "X-A-1"
    store.close()


def test_explorer_never_combines_scopes(tmp_path: Path) -> None:
    store = Intelligence(tmp_path / "ledger.sqlite3")
    for scope, symbol in (("r:a", "X-A-1"), ("r:b", "X-B-1")):
        store.observe(
            scope,
            "waypoint",
            symbol,
            {"symbol": symbol, "type": "MOON", "x": 0, "y": 0, "traits": []},
        )
        store.observe(
            scope,
            "ship",
            symbol,
            {
                "symbol": symbol,
                "nav": {"status": "DOCKED", "waypointSymbol": symbol},
            },
        )

    result = system_explorer(store, "r:a")

    assert [system["symbol"] for system in result["systems"]] == ["X-A"]
    assert [ship["symbol"] for ship in result["ships"]] == ["X-A-1"]
    store.close()
