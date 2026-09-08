import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.intelligence import Intelligence
from py_st.services.route_history import RouteScenario, evaluate_route

BASE = datetime(2026, 9, 7, tzinfo=UTC)
SOURCE = "X-A-1"
BUYER = "X-A-2"


def stamp(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Intelligence]:
    store = Intelligence(tmp_path / "history.db")
    yield store
    store.close()


def quote(
    store: Intelligence,
    key: str,
    seconds: int,
    *,
    buy: int = 100,
    sell: int = 200,
    volume: int = 40,
    scope: str = "r:a",
    provenance: str = "live-api",
    sparse: bool = False,
) -> int:
    data = {
        "tradeGoods": (
            []
            if sparse
            else [
                {
                    "symbol": "IRON",
                    "purchasePrice": buy,
                    "sellPrice": sell,
                    "tradeVolume": volume,
                }
            ]
        )
    }
    with store.db:
        cursor = store.db.execute(
            "INSERT INTO observations "
            "(scope,kind,key,observed_at,source,data) "
            "VALUES (?,'market',?,?,?,?)",
            (scope, key, stamp(seconds), provenance, json.dumps(data)),
        )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def scenario(**changes: Any) -> RouteScenario:
    return replace(
        RouteScenario(
            scope="r:a",
            source=SOURCE,
            destination=BUYER,
            good="IRON",
            start=stamp(0),
            end=stamp(1000),
            leg_seconds=60,
            fuel_allowance=100,
        ),
        **changes,
    )


def test_rounding_volume_cost_and_losses(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange: a profitable entry quote crashes before arrival.
    quote(ledger, BUYER, -1, volume=12)
    source_id = quote(ledger, SOURCE, 0, buy=101, volume=20)
    exit_id = quote(ledger, BUYER, 60, sell=90)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario())
    # Assert: ceil(101*1.05)=107, floor(90*.95)=85; fuel charged once.
    attempt = result["attempts"][0]
    assert attempt["source_quote"]["observation_id"] == source_id
    assert attempt["exit_quote"]["observation_id"] == exit_id
    assert attempt["units"] == 12
    assert attempt["buy_unit_assumption"] == 107
    assert attempt["sell_unit_assumption"] == 85
    assert attempt["entry_net_estimate"] == 896
    assert attempt["scenario_net"] == -364
    assert result["summary"]["losses"] == 1
    assert result["summary"]["worst_settled_net"] == -364
    assert result["summary"]["ending_cash"] == 174636


@pytest.mark.parametrize("buyer_time", [1, 0])
def test_future_or_later_id_buyer_cannot_enable_entry(
    ledger: Intelligence, tmp_path: Path, buyer_time: int
) -> None:
    # Arrange: even a same-timestamp buyer recorded later is unknown at entry.
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, buyer_time, sell=99999)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario())
    # Assert
    assert result["summary"]["entries"] == 0
    assert result["summary"]["skipped"] == {"missing_or_stale_entry_buyer": 1}


def test_future_prices_do_not_change_entry_or_past_exit(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, 60, sell=120)
    before = evaluate_route(tmp_path / "history.db", scenario())
    # Act: huge prices after arrival, then outside the report horizon.
    quote(ledger, BUYER, 61, sell=999999)
    quote(ledger, BUYER, 1001, sell=999999)
    after = evaluate_route(tmp_path / "history.db", scenario())
    # Assert
    assert before == after
    assert after["attempts"][0]["sell_unit_assumption"] == 114


def test_future_rally_cannot_rescue_unprofitable_entry(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange
    quote(ledger, BUYER, -1, sell=90)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, 60, sell=99999)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario())
    # Assert
    assert result["attempts"] == []
    assert result["summary"]["skipped"] == {"nonpositive_entry_margin": 1}


@pytest.mark.parametrize("volume", [40, 1])
def test_latest_exit_cannot_fall_back_to_better_older_quote(
    ledger: Intelligence, tmp_path: Path, volume: int
) -> None:
    # Arrange: a favorable post-entry quote is superseded before arrival.
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, 30, sell=99999)
    latest_id = quote(ledger, BUYER, 60, sell=50, volume=volume)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario())
    # Assert
    attempt = result["attempts"][0]
    assert attempt["exit_quote"]["observation_id"] == latest_id
    if volume == 40:
        assert attempt["scenario_net"] == -2420
    else:
        assert attempt["reason"] == "insufficient_exit_volume"
        assert result["summary"]["unresolved"] == 1


@pytest.mark.parametrize(
    ("exit_time", "volume", "reason"),
    [
        (61, 40, "missing_post_entry_exit_quote"),
        (0, 40, "missing_post_entry_exit_quote"),
        (1, 40, "stale_exit_quote"),
        (60, 39, "insufficient_exit_volume"),
    ],
)
def test_unresolved_exit_blocks_reentry_and_retains_exposure(
    ledger: Intelligence,
    tmp_path: Path,
    exit_time: int,
    volume: int,
    reason: str,
) -> None:
    # Arrange
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, exit_time, volume=volume)
    quote(ledger, SOURCE, 120)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario(max_age=30))
    # Assert: no invented sale, no marking inventory at a stale price.
    summary = result["summary"]
    assert result["attempts"][0]["reason"] == reason
    assert summary["entries"] == summary["unresolved"] == 1
    assert summary["settled"] == summary["settled_scenario_net"] == 0
    assert summary["worst_settled_net"] is None
    assert summary["cash_change"] == -4300
    assert summary["unvalued_inventory_units"] == 40
    assert summary["skipped"] == {"unresolved_position": 1}


def test_capital_reuse_only_after_round_trip(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange: first trip is cash-limited to 10 units; gains fund 19 next time.
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, 60)
    quote(ledger, SOURCE, 60)
    quote(ledger, SOURCE, 119)
    quote(ledger, SOURCE, 120)
    quote(ledger, BUYER, 180)
    # Act
    result = evaluate_route(
        tmp_path / "history.db",
        scenario(initial_credits=51100, slippage_bps=0),
    )
    # Assert
    assert [a["units"] for a in result["attempts"]] == [10, 19]
    assert result["summary"]["skipped"] == {"in_transit": 2}
    assert result["summary"]["settled_scenario_net"] == 2700
    assert result["summary"]["ending_cash"] == 53800


def test_sparse_quotes_do_not_refresh_price_age(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange
    quote(ledger, BUYER, -31)
    quote(ledger, BUYER, -1, sparse=True)
    quote(ledger, SOURCE, 0)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario(max_age=30))
    # Assert
    assert result["summary"]["skipped"] == {"missing_or_stale_entry_buyer": 1}


def test_scope_provenance_good_and_time_isolation(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange: valid buyer data exists, but not for this scope/provenance/good.
    quote(ledger, BUYER, -1, scope="other:a")
    quote(ledger, BUYER, -1, provenance="strategy")
    quote(ledger, BUYER, -1)
    with ledger.db:
        ledger.db.execute(
            "UPDATE observations SET data=replace(data,'IRON','COPPER') "
            "WHERE id=3"
        )
    quote(ledger, SOURCE, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, SOURCE, 1001)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario())
    # Assert
    assert result["summary"]["source_candidates"] == 1
    assert result["summary"]["entries"] == 0


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"initial_credits": 50000}, "credit_reserve"),
        ({"fuel_allowance": 10000}, "nonpositive_entry_margin"),
        ({"end": stamp(119)}, "insufficient_horizon"),
        ({"leg_seconds": 10**30}, "insufficient_horizon"),
    ],
)
def test_entry_rejections(
    ledger: Intelligence,
    tmp_path: Path,
    changes: dict[str, Any],
    reason: str,
) -> None:
    # Arrange
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    # Act
    result = evaluate_route(tmp_path / "history.db", scenario(**changes))
    # Assert
    assert result["summary"]["skipped"] == {reason: 1}
    assert result["summary"]["cash_change"] == 0


def test_timezone_order_and_exact_age_horizon_boundaries(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange: lexical time ordering differs from UTC time ordering.
    quote(ledger, BUYER, -30)
    quote(ledger, SOURCE, 0)
    exit_id = quote(ledger, BUYER, 30)
    with ledger.db:
        ledger.db.execute(
            "UPDATE observations SET observed_at=? WHERE id=?",
            ("2026-09-07T01:00:30+01:00", exit_id),
        )
    # Act
    result = evaluate_route(
        tmp_path / "history.db", scenario(max_age=30, end=stamp(120))
    )
    # Assert: both quotes at age=30 and full round trip at end are allowed.
    assert result["summary"]["settled"] == 1
    assert result["attempts"][0]["exit_quote"]["age_seconds"] == 30


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "2026-09-07T00:00:00"},
        {"end": stamp(0)},
        {"scope": "unknown"},
        {"destination": SOURCE},
        {"destination": "X-B-2"},
        {"credit_floor": 49999},
        {"initial_credits": 49999},
        {"capacity": 0},
        {"leg_seconds": 0},
        {"fuel_allowance": -1},
        {"max_age": 0},
        {"slippage_bps": -1},
        {"slippage_bps": 10000},
    ],
)
def test_invalid_scenario(
    ledger: Intelligence, tmp_path: Path, changes: dict[str, Any]
) -> None:
    # Arrange
    quote(ledger, SOURCE, 0)
    # Act / Assert
    with pytest.raises(ValueError):
        evaluate_route(tmp_path / "history.db", scenario(**changes))


def test_malformed_quote_and_schema_fail_closed(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange
    quote(ledger, SOURCE, 0, buy=0)
    # Act / Assert
    with pytest.raises(ValueError, match="Invalid quote"):
        evaluate_route(tmp_path / "history.db", scenario())
    with ledger.db:
        ledger.db.execute("PRAGMA user_version=2")
    with pytest.raises(ValueError, match="schema"):
        evaluate_route(tmp_path / "history.db", scenario())


def test_duplicate_good_rejected_and_empty_history_explicit(
    ledger: Intelligence, tmp_path: Path
) -> None:
    # Arrange
    quote(ledger, SOURCE, 0, sparse=True)
    empty = evaluate_route(tmp_path / "history.db", scenario())
    identifier = quote(ledger, SOURCE, 1)
    row = ledger.db.execute(
        "SELECT data FROM observations WHERE id=?", (identifier,)
    ).fetchone()
    data = json.loads(row[0])
    data["tradeGoods"] *= 2
    with ledger.db:
        ledger.db.execute(
            "UPDATE observations SET data=? WHERE id=?",
            (json.dumps(data), identifier),
        )
    # Act / Assert
    assert empty["summary"]["source_candidates"] == 0
    assert empty["summary"]["worst_settled_net"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate_route(tmp_path / "history.db", scenario())


def test_missing_database_not_created(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "absent.db"
    # Act / Assert
    with pytest.raises(sqlite3.OperationalError):
        evaluate_route(path, scenario())
    assert not path.exists()


def test_cli_offline_read_only_with_stop(
    ledger: Intelligence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    quote(ledger, BUYER, -1)
    quote(ledger, SOURCE, 0)
    quote(ledger, BUYER, 60)
    before = list(ledger.db.iterdump())
    stop = tmp_path / "STOP"
    stop.write_text("remain stopped\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ST_TOKEN", raising=False)
    args = [
        "auto",
        "backtest",
        SOURCE,
        BUYER,
        "IRON",
        "--scope",
        "r:a",
        "--start",
        stamp(0),
        "--end",
        stamp(1000),
        "--leg-seconds",
        "60",
        "--fuel-allowance",
        "100",
        "--database",
        str(tmp_path / "history.db"),
    ]
    # Act
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch("httpx.Client.request") as request,
    ):
        result = CliRunner().invoke(app, args)
    # Assert
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["summary"]["settled"] == 1
    session.assert_not_called()
    request.assert_not_called()
    assert list(ledger.db.iterdump()) == before
    assert stop.read_text() == "remain stopped\n"
    invalid = CliRunner().invoke(app, args + ["--max-age", "0"])
    assert invalid.exit_code == 2
    assert "Invalid scenario" in invalid.output
