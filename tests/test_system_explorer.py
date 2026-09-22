from pathlib import Path

import pytest

from py_st.services.flight_demo import SCOPE, create_demo
from py_st.services.intelligence import Intelligence
from py_st.services.system_explorer import system_explorer


def test_explorer_includes_fleet_systems_before_waypoint_refresh(
    tmp_path: Path,
) -> None:
    # Arrange: initial observation has fleet evidence but no waypoint history.
    store = Intelligence(tmp_path / "ledger.sqlite3")
    for scope, ship, system in (
        ("r:a", "A-1", "X-A"),
        ("r:a", "A-2", "X-A"),
        ("r:a", "A-3", "X-B"),
        ("old:a", "A-1", "X-OLD"),
        ("r:other", "OTHER-1", "X-OTHER"),
    ):
        store.observe(scope, "ship", ship, {"nav": {"systemSymbol": system}})

    # Act / Assert: deduplicate current fleet systems without inventing points.
    assert system_explorer(store, "r:a")["systems"] == [
        {"symbol": "X-A", "waypoints": []},
        {"symbol": "X-B", "waypoints": []},
    ]
    store.observe("r:a", "waypoint", "X-A-1", {"systemSymbol": "X-A"})
    result = system_explorer(store, "r:a")
    assert [system["symbol"] for system in result["systems"]] == [
        "X-A",
        "X-B",
    ]
    assert len(result["systems"][0]["waypoints"]) == 1
    assert result["systems"][1]["waypoints"] == []
    store.close()


@pytest.mark.parametrize("system", [None, "", 123, []])
def test_explorer_ignores_missing_or_nonstring_fleet_system(
    tmp_path: Path, system: object
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "ledger.sqlite3")
    store.observe("r:a", "ship", "A-1", {"nav": {"systemSymbol": system}})

    # Act / Assert
    assert system_explorer(store, "r:a")["systems"] == []
    store.close()


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


def test_dense_fixture_preserves_all_members_and_market_evidence(
    tmp_path: Path,
) -> None:
    # Arrange: deterministic crowded system with colocated orbitals.
    create_demo(tmp_path, layout="dense")
    store = Intelligence(tmp_path / ".state/intelligence.sqlite3")

    # Act
    result = system_explorer(store, SCOPE)
    points = result["systems"][0]["waypoints"]
    by_symbol = {w["symbol"]: w for w in points}

    # Assert: discoverable members retain their individual evidence.
    assert len(points) >= 85
    assert {w["symbol"] for w in points if w.get("x") == w.get("y") == 0} >= {
        "X-DEMO-A1",
        "X-DEMO-A2",
        "X-DEMO-A3",
        "X-DEMO-A4",
    }
    assert by_symbol["X-DEMO-A4"]["orbits"] == "X-DEMO-A1"
    assert by_symbol["X-DEMO-A4"]["has_market"]
    assert "tradeGoods" not in by_symbol["X-DEMO-A4"]["market"]["data"]
    assert by_symbol["X-DEMO-UNKNOWN"]["x"] is None
    store.close()
