from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.client import SpaceTradersClient
from py_st.services.automation import Session
from py_st.services.intelligence import Intelligence
from py_st.services.mining import diagnose_mining

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


@pytest.fixture
def ship() -> dict[str, Any]:
    return {
        "symbol": "S",
        "nav": {
            "systemSymbol": "X-A",
            "waypointSymbol": "X-A-1",
            "status": "IN_ORBIT",
        },
        "mounts": [{"symbol": "MOUNT_MINING_LASER_II"}],
        "cargo": {"capacity": 40, "units": 0},
        "cooldown": {"remainingSeconds": 0},
    }


@pytest.fixture
def waypoint() -> dict[str, Any]:
    return {"symbol": "X-A-1", "type": "ASTEROID_FIELD", "traits": []}


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("ORBITAL_STATION", "unknown"),
        ("ASTEROID_FIELD", "documented_example"),
        ("ASTEROID", "unknown"),
        ("ENGINEERED_ASTEROID", "unknown"),
        ("ASTEROID_BASE", "unknown"),
    ],
)
def test_type_evidence_not_invented(
    ship: dict[str, Any], waypoint: dict[str, Any], kind: str, expected: str
) -> None:
    # Arrange
    waypoint["type"] = kind
    before = deepcopy((ship, waypoint))
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert: no positive authorization even for a documented example.
    assert result["extractability"] == expected
    assert not result["blockers"]
    assert result["assessment"] == "unknown"
    assert result["execution_authorized"] is False
    assert "prior owner's failure" in result["note"]
    assert (ship, waypoint) == before


@pytest.mark.parametrize("status", ["DOCKED", "IN_TRANSIT"])
def test_orbit_blocker(
    ship: dict[str, Any], waypoint: dict[str, Any], status: str
) -> None:
    # Arrange
    ship["nav"]["status"] = status
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert "Extraction requires IN_ORBIT" in result["blockers"]


def test_missing_laser_full_cargo_and_location(
    ship: dict[str, Any], waypoint: dict[str, Any]
) -> None:
    # Arrange: a siphon/surveyor is not an ore laser.
    ship["mounts"] = [{"symbol": "MOUNT_GAS_SIPHON_II"}]
    ship["cargo"]["units"] = 40
    waypoint["symbol"] = "X-A-2"
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert result["free_cargo"] == 0
    assert len(result["blockers"]) == 3
    assert any("Mining Laser" in item for item in result["blockers"])
    assert result["assessment"] == "blocked"


@pytest.mark.parametrize(
    "remaining,expiration,unknown",
    [
        (20, "2026-09-08T12:00:20Z", False),
        (20, "2026-09-08T11:00:00Z", True),
        (0, "2026-09-08T12:00:00+00:00", False),
        (0, "2026-09-08T14:00:00+02:00", False),
        (0, "2026-09-08T12:00:20Z", True),
        (0, "2026-09-08T12:00:00", True),
        (0, "not-a-date", True),
        (0, 123, True),
    ],
)
def test_cooldown_timezone_safety(
    ship: dict[str, Any],
    waypoint: dict[str, Any],
    remaining: int,
    expiration: Any,
    unknown: bool,
) -> None:
    # Arrange
    ship["cooldown"] = {
        "remainingSeconds": remaining,
        "expiration": expiration,
    }
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert bool(result["blockers"]) == (remaining > 0)
    assert any("Cooldown" in item for item in result["unknowns"]) == unknown


def test_naive_clock_and_missing_snapshot_fields(
    ship: dict[str, Any], waypoint: dict[str, Any]
) -> None:
    # Arrange
    ship["cooldown"]["expiration"] = "2026-09-08T12:00:00Z"
    # Act
    naive = diagnose_mining(ship, waypoint, now=NOW.replace(tzinfo=None))
    missing = diagnose_mining({}, {}, now=NOW)
    # Assert
    assert any("timezone" in item for item in naive["unknowns"])
    assert not missing["blockers"]
    assert len(missing["unknowns"]) == 7


@pytest.mark.parametrize("field", ["traits", "modifiers"])
def test_stripped_is_not_non_extractability(
    ship: dict[str, Any], waypoint: dict[str, Any], field: str
) -> None:
    # Arrange
    waypoint["traits"] = [{"symbol": "COMMON_METAL_DEPOSITS"}]
    waypoint.setdefault(field, []).append(
        {"symbol": "STRIPPED", "description": "Depleted from over-mining"}
    )
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert not result["blockers"]
    assert result[field] == waypoint[field]
    assert "not proof" in result["warnings"][0]
    assert "do not guarantee" in result["note"]


@pytest.mark.parametrize(
    "field,evidence",
    [("nav", "Orbit"), ("cargo", "Cargo"), ("cooldown", "Cooldown")],
)
@pytest.mark.parametrize("value", [None, [], "invalid", 123])
def test_malformed_ship_sections_are_unknown(
    ship: dict[str, Any],
    waypoint: dict[str, Any],
    field: str,
    evidence: str,
    value: Any,
) -> None:
    # Arrange
    ship[field] = value
    before = deepcopy(ship)
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert not result["blockers"]
    assert any(evidence in item for item in result["unknowns"])
    assert ship == before


@pytest.mark.parametrize("field", ["traits", "modifiers"])
@pytest.mark.parametrize(
    "value", [None, {}, "invalid", 123, [None], ["STRIPPED"], [{}]]
)
def test_malformed_waypoint_lists_are_unknown(
    ship: dict[str, Any],
    waypoint: dict[str, Any],
    field: str,
    value: Any,
) -> None:
    # Arrange
    waypoint[field] = value
    before = deepcopy(waypoint)
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert not result["blockers"]
    assert not result["warnings"]
    assert any(field in item for item in result["unknowns"])
    assert result[field] == value
    assert waypoint == before


@pytest.mark.parametrize(
    "mounts",
    [
        None,
        {},
        "invalid",
        [None],
        [{}],
        [{"symbol": None}],
        [{"symbol": ""}],
        [{"symbol": "   "}],
        [{"symbol": 123}],
        [{"symbol": "MOUNT_GAS_SIPHON_II"}, {}],
    ],
)
def test_incomplete_mount_evidence_does_not_confirm_absence(
    ship: dict[str, Any], waypoint: dict[str, Any], mounts: Any
) -> None:
    # Arrange
    ship["mounts"] = mounts
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert not result["blockers"]
    assert any("mount evidence" in item for item in result["unknowns"])


def test_empty_mount_list_confirms_absence(
    ship: dict[str, Any], waypoint: dict[str, Any]
) -> None:
    # Arrange
    ship["mounts"] = []
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert result["blockers"] == [
        "No installed Mining Laser for ore extraction"
    ]


def test_partial_traits_preserve_known_stripped_warning(
    ship: dict[str, Any], waypoint: dict[str, Any]
) -> None:
    # Arrange
    waypoint["traits"] = [None, {"symbol": "STRIPPED"}]
    # Act
    result = diagnose_mining(ship, waypoint, now=NOW)
    # Assert
    assert any("traits" in item for item in result["unknowns"])
    assert len(result["warnings"]) == 1
    assert not result["blockers"]


def test_cli_fresh_get_only_default(
    tmp_path: Path, ship: dict[str, Any], waypoint: dict[str, Any]
) -> None:
    # Arrange: stale fleet differs from the individual fresh ship.
    requests: list[tuple[str, str]] = []

    def request(req: httpx.Request) -> httpx.Response:
        requests.append((req.method, req.url.path))
        assert req.method == "GET"
        if req.url.path == "/":
            return httpx.Response(200, json={"resetDate": "r"})
        data = {
            "/my/agent": {"symbol": "a", "credits": 100000},
            "/my/ships": [{"symbol": "S", "nav": {"status": "DOCKED"}}],
            "/my/contracts": [],
            "/my/ships/S": ship,
            "/systems/X-A/waypoints/X-A-1": waypoint,
        }[req.url.path]
        return httpx.Response(200, json={"data": data})

    with SpaceTradersClient(
        "fake",
        httpx.Client(
            transport=httpx.MockTransport(request), base_url="https://test"
        ),
    ) as client:
        client._transport._interval = 0
        store = Intelligence(tmp_path / "db")
        run = Session(client, store, root=tmp_path, execute=False, actions=1)
        try:
            with patch("py_st.cli.auto_cmd.session") as factory:
                factory.return_value.__enter__.return_value = run
                # Act
                result = CliRunner().invoke(app, ["auto", "mining", "S"])
                # Assert
                assert result.exit_code == 0, result.output
                factory.assert_called_once_with(False, 120, 1)
                assert '"blockers": []' in result.output
                assert '"execution_authorized": false' in result.output
                assert requests[-2:] == [
                    ("GET", "/my/ships/S"),
                    ("GET", "/systems/X-A/waypoints/X-A-1"),
                ]
                assert not store.actions("r:a")
        finally:
            run.close()
            store.close()


def test_cli_has_no_execute_option() -> None:
    # Arrange / Act
    with patch("py_st.cli.auto_cmd.session") as factory:
        result = CliRunner().invoke(app, ["auto", "mining", "S", "--execute"])
    # Assert: reject before credentials, database or network access.
    assert result.exit_code == 2
    factory.assert_not_called()
