import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from py_st.services.intelligence import Intelligence
from py_st.services.market_history import market_history

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
QUOTE = {
    "symbol": "ORE",
    "purchasePrice": 10,
    "sellPrice": 8,
    "tradeVolume": 7,
    "supply": "HIGH",
    "activity": "WEAK",
}


def record(
    store: Intelligence, when: str, quotes: list[Any], scope: str = "r:a"
) -> int:
    with store.db:
        cursor = store.db.execute(
            "INSERT INTO observations "
            "(scope,kind,key,observed_at,source,data) "
            "VALUES (?,'market','X-A-M',?,'synthetic-detail',?)",
            (scope, when, json.dumps({"tradeGoods": quotes})),
        )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def test_history_original_sparse_scope_order_limit_and_wal(
    tmp_path: Path,
) -> None:
    # Arrange: insertion order differs from time order; keep the writer open.
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    times = [(NOW - timedelta(minutes=m)).isoformat() for m in (60, 1, 20)]
    ids = [record(store, when, [QUOTE]) for when in times]
    record(store, NOW.isoformat(), [])
    record(store, NOW.isoformat(), [QUOTE | {"purchasePrice": 999}], "r:b")
    before = store.db.execute("SELECT * FROM observations").fetchall()
    connect = sqlite3.connect
    statements: list[str] = []

    def read_only(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        assert args[0].endswith("?mode=ro") and kwargs["uri"]
        db: sqlite3.Connection = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    try:
        # Act: no Session, auth, filesystem reads or API client allowed.
        with (
            patch("sqlite3.connect", side_effect=read_only),
            patch(
                "py_st.services.automation.Session", side_effect=AssertionError
            ),
            patch(
                "py_st.client.SpaceTradersClient", side_effect=AssertionError
            ),
            patch("dotenv.load_dotenv", side_effect=AssertionError),
            patch("dotenv.find_dotenv", side_effect=AssertionError),
            patch("pathlib.Path.open", side_effect=AssertionError),
        ):
            result = market_history(
                database, "r:a", "X-A-M", "ORE", 2, now=NOW
            )
        # Assert: newest two by actual time, not insertion ID or sparse advert.
        assert result["truncated"]
        assert result["latest_market"]["observed_at"] == NOW.isoformat()
        assert [p["id"] for p in result["points"]] == [ids[2], ids[1]]
        assert [p["observed_at"] for p in result["points"]] == [
            times[2],
            times[1],
        ]
        assert [p["stale"] for p in result["points"]] == [True, False]
        for point in result["points"]:
            assert point["visibility"] == "retained_history"
            assert point["source"] == "synthetic-detail"
            assert (
                point["purchase_price"],
                point["sell_price"],
                point["trade_volume"],
            ) == (10, 8, 7)
            assert (point["supply"], point["activity"]) == ("HIGH", "WEAK")
        assert (
            store.db.execute("SELECT * FROM observations").fetchall() == before
        )
        assert all(
            s.startswith(("SELECT", "BEGIN", "PRAGMA user_version"))
            for s in statements
        )
        assert (
            market_history(database, "r:b", "X-A-M", "ORE", now=NOW)["points"][
                0
            ]["purchase_price"]
            == 999
        )
    finally:
        store.close()


@pytest.mark.parametrize("value", [None, 0, -1, True, "12", 1.2, float("nan")])
def test_malformed_prices_are_independent_gaps(
    tmp_path: Path, value: Any
) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    record(
        store,
        NOW.isoformat(),
        [QUOTE | {"purchasePrice": value, "tradeVolume": value}],
    )
    store.close()
    result = market_history(database, "r:a", "X-A-M", "ORE", now=NOW)
    point = result["points"][0]
    assert point["purchase_price"] is point["trade_volume"] is None
    assert point["sell_price"] == 8
    assert point["visibility"] == "current_detail"
    assert not point["stale"]
    assert len(result["points"]) == 1
    json.dumps(result, allow_nan=False)


def test_history_skips_bad_times_and_marks_duplicate_quotes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    record(store, "invalid", [QUOTE])
    record(store, "2026-09-08T11:00:00", [QUOTE])
    record(store, (NOW + timedelta(seconds=1)).isoformat(), [QUOTE])
    record(store, "2026-09-08T13:00:00+01:00", [QUOTE, QUOTE])
    record(store, NOW.isoformat(), [{"symbol": "OTHER", "purchasePrice": 100}])
    store.close()
    result = market_history(database, "r:a", "X-A-M", "ORE", now=NOW)
    assert result["skipped"] == {
        "invalid_timestamp": 2,
        "future_timestamp": 1,
        "invalid_data": 0,
    }
    assert len(result["points"]) == 1
    point = result["points"][0]
    assert point["quote_status"] == "duplicate_good"
    assert point["purchase_price"] is point["sell_price"] is None
    assert point["observed_at"] == "2026-09-08T13:00:00+01:00"
    assert (
        market_history(database, "r:a", "X-A-M", "MISSING", now=NOW)["points"]
        == []
    )


def test_basic_iso_preserves_provenance_and_normalizes_plot_time(
    tmp_path: Path,
) -> None:
    # Arrange: Python accepts basic ISO, but browser Date.parse does not.
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    record(store, "2026-09-08T11:30:00+00:00", [QUOTE])
    record(store, "20260908T110000+0000", [QUOTE])
    store.close()

    # Act / Assert: raw timestamps survive; plotting uses actual UTC time.
    result = market_history(database, "r:a", "X-A-M", "ORE", now=NOW)
    points = result["points"]
    assert [p["observed_at"] for p in points] == [
        "20260908T110000+0000",
        "2026-09-08T11:30:00+00:00",
    ]
    assert [p["observed_at_ms"] for p in points] == [
        (NOW - timedelta(minutes=60)).timestamp() * 1000,
        (NOW - timedelta(minutes=30)).timestamp() * 1000,
    ]
    assert not any(result["skipped"].values())


@pytest.mark.parametrize("data", [None, [], 12, True, "text"])
def test_nonobject_data_is_malformed_not_sparse(
    tmp_path: Path,
    data: Any,
) -> None:
    # Arrange: legitimate sparse objects must not inflate the malformed count.
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    record(store, NOW.isoformat(), [QUOTE])
    payload: Any
    for payload in ({}, {"tradeGoods": []}, data):
        store.observe("r:a", "market", "X-A-M", payload, "synthetic")
    store.close()

    # Act / Assert
    result = market_history(database, "r:a", "X-A-M", "ORE", now=NOW)
    assert result["skipped"] == {
        "invalid_data": 1,
        "invalid_timestamp": 0,
        "future_timestamp": 0,
    }
    assert len(result["points"]) == 1
    assert result["points"][0]["purchase_price"] == 10


@pytest.mark.parametrize("limit", [1, 50, 100])
def test_history_bounds(tmp_path: Path, limit: int) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    for i in range(105):
        record(store, (NOW - timedelta(seconds=105 - i)).isoformat(), [QUOTE])
    store.close()
    points = market_history(database, "r:a", "X-A-M", "ORE", limit, now=NOW)[
        "points"
    ]
    assert len(points) == limit
    assert [p["id"] for p in points] == list(range(106 - limit, 106))
    assert (
        len(market_history(database, "r:a", "X-A-M", "ORE", now=NOW)["points"])
        == 50
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", ""),
        ("scope", "bad"),
        ("scope", "r:z"),
        ("waypoint", ""),
        ("waypoint", "X-A-OTHER"),
        ("waypoint", "../db"),
        ("good", ""),
        ("good", "ORE' OR 1=1"),
        ("good", "x" * 101),
        ("limit", 0),
        ("limit", 101),
        ("limit", True),
        ("limit", 1.5),
    ],
)
def test_history_validation(tmp_path: Path, field: str, value: Any) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    record(store, NOW.isoformat(), [QUOTE])
    store.close()
    args: dict[str, Any] = {
        "scope": "r:a",
        "waypoint": "X-A-M",
        "good": "ORE",
        "limit": 50,
    }
    with pytest.raises(ValueError):
        market_history(database, **(args | {field: value}), now=NOW)


def test_missing_database_not_created(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="none created"):
        market_history(
            tmp_path / "missing" / "ledger.sqlite3", "r:a", "X-A-M", "ORE"
        )
    assert list(tmp_path.iterdir()) == []
