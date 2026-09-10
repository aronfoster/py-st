import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.contract_sources import contract_sources
from py_st.services.intelligence import Intelligence

SCOPE = "reset:agent"
NOW = datetime(2090, 1, 1, tzinfo=UTC)


def observe(
    path: Path,
    kind: str,
    key: str,
    data: Any,
    *,
    age: int = 0,
    scope: str = SCOPE,
) -> None:
    store = Intelligence(path)
    try:
        store.observe(scope, kind, key, data, source="synthetic")
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? "
                "WHERE id=(SELECT MAX(id) FROM observations)",
                ((NOW - timedelta(seconds=age)).isoformat(),),
            )
    finally:
        store.close()


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.sqlite3"
    observe(
        path,
        "contract",
        "C",
        {
            "id": "C",
            "accepted": False,
            "fulfilled": False,
            "deadlineToAccept": "2091-01-01T00:00:00Z",
            "terms": {
                "deadline": "2092-01-01T00:00:00Z",
                "deliver": [
                    {
                        "tradeSymbol": good,
                        "destinationSymbol": "X-A-D",
                        "unitsRequired": 12,
                        "unitsFulfilled": 2,
                    }
                    for good in ("ORE", "MEDICINE", "ORE")
                ],
            },
        },
    )
    for symbol, x, category in (
        ("X-A-D", 0, "imports"),
        ("X-A-E", 10, "exports"),
        ("X-A-X", 5, "exchange"),
        ("X-B-E", 1, "exports"),
    ):
        observe(
            path,
            "waypoint",
            symbol,
            {
                "symbol": symbol,
                "systemSymbol": symbol.rsplit("-", 1)[0],
                "x": x,
                "y": 0,
            },
        )
        observe(
            path,
            "market",
            symbol,
            {
                category: [{"symbol": "ORE"}, {"symbol": "ORE"}],
                "tradeGoods": [
                    {"symbol": "ORE", "purchasePrice": 100, "tradeVolume": 5}
                ],
            },
            age=100,
        )
    return path


def shortlist(path: Path, **kwargs: Any) -> dict[str, Any]:
    return contract_sources(path, SCOPE, "C", now=NOW, **kwargs)


def ore_sources(path: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = shortlist(path)["deliveries"][1]["sources"]
    return sources


def test_rank_all_goods_and_deduplicate(ledger: Path) -> None:
    result = shortlist(ledger)
    medicine, ore = result["deliveries"]
    assert medicine["source_status"] == "no_same_system_adverts"
    assert medicine["remaining_units"] == 10
    assert ore["remaining_units"] == 20
    assert [s["source"] for s in ore["sources"]] == [
        "X-A-X",
        "X-A-E",
        "X-A-D",
    ]
    assert [s["distance"] for s in ore["sources"]] == [5, 10, 0]
    assert all(s["purchase_price"] == 100 for s in ore["sources"])
    assert all(s["actionable_quote"] for s in ore["sources"])
    assert result["execution_authorized"] is False


def test_contract_observation_matches_transaction_snapshot(
    ledger: Path,
) -> None:
    store = Intelligence(ledger, read_only=True)
    try:
        original = store.latest(SCOPE, "contract")[0]
    finally:
        store.close()
    updated = original["data"] | {"accepted": True}
    updated["terms"] = original["data"]["terms"] | {
        "deliver": [
            {
                "tradeSymbol": "ORE",
                "destinationSymbol": "X-A-D",
                "unitsRequired": 10,
                "unitsFulfilled": 5,
            }
        ]
    }
    latest = Intelligence.latest

    def advance_contract(
        store: Intelligence,
        scope: str,
        kind: str,
        *,
        priced_only: bool = False,
    ) -> list[dict[str, Any]]:
        # Commit progress after the contract read, while sources still reads
        # markets in its original read-only transaction.
        if kind == "market" and not priced_only:
            observe(ledger, "contract", "C", updated)
        return latest(store, scope, kind, priced_only=priced_only)

    with patch.object(Intelligence, "latest", new=advance_contract):
        result = shortlist(ledger)

    assert result["contract_observation"] == original
    assert result["contract_observed_at"] == original["observed_at"]
    assert result["accepted"] is False
    assert result["deliveries"][1]["remaining_units"] == 20
    refreshed = shortlist(ledger)
    assert refreshed["contract_observation"]["data"] == updated
    assert refreshed["contract_observation"]["id"] > original["id"]
    assert refreshed["accepted"] is True
    assert refreshed["deliveries"][0]["remaining_units"] == 5
    assert refreshed["execution_authorized"] is False


def test_one_market_can_advertise_multiple_goods_without_extra_sources(
    ledger: Path,
) -> None:
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "exports": [{"symbol": g} for g in ("ORE", "MEDICINE")],
            "exchange": [{"symbol": "ORE"}],
            "tradeGoods": [
                {"symbol": g, "purchasePrice": p, "tradeVolume": v}
                for g, p, v in (("ORE", 100, 5), ("MEDICINE", 200, 2))
            ],
        },
    )
    medicine, ore = shortlist(ledger)["deliveries"]
    assert len(medicine["sources"]) == 1
    assert medicine["sources"][0]["purchase_price"] == 200
    assert medicine["sources"][0]["trade_volume"] == 2
    assert len(ore["sources"]) == 3
    assert ore["sources"][1]["category"] == "exports"
    assert ore["sources"][1]["purchase_price"] == 100


def test_acceptance_unknown_and_delivery_expired(ledger: Path) -> None:
    observe(
        ledger,
        "contract",
        "C",
        {
            "accepted": False,
            "fulfilled": False,
            "deadlineToAccept": None,
            "expiration": "2091-01-01T00:00:00Z",
            "terms": {"deliver": [], "deadline": NOW.isoformat()},
        },
    )
    result = shortlist(ledger)
    assert result["deadline_status"] == {
        "acceptance": "unknown",
        "delivery": "expired",
    }
    assert result["sourcing_blockers"] == ["Delivery deadline expired"]


@pytest.mark.parametrize("price,volume", [(0, 5), (None, 5), (100, 0)])
def test_invalid_quote_never_substitutes_older_price(
    ledger: Path,
    price: int | None,
    volume: int,
) -> None:
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "exports": [{"symbol": "ORE"}],
            "tradeGoods": [
                {
                    "symbol": "ORE",
                    "purchasePrice": price,
                    "tradeVolume": volume,
                }
            ],
        },
    )
    source = ore_sources(ledger)[1]
    assert source["quote_status"] == "invalid_price_or_volume"
    assert source["purchase_price"] is None
    assert source["trade_volume"] is None
    assert not source["actionable_quote"]


@pytest.mark.parametrize(
    "age,status,price",
    [
        (901, "stale", None),
        (900, "fresh_historical", 123),
        (-1, "invalid_timestamp", None),
    ],
)
def test_sparse_preserves_original_quote_age(
    ledger: Path,
    age: int,
    status: str,
    price: int | None,
) -> None:
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "tradeGoods": [
                {"symbol": "ORE", "purchasePrice": 123, "tradeVolume": 4}
            ],
        },
        age=age,
    )
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "exports": [{"symbol": "ORE"}],
            "tradeGoods": [],
        },
    )
    source = ore_sources(ledger)[1]
    assert source["quote_status"] == status
    assert source["quote_age_seconds"] == age
    assert (
        source["quote_observed_at"]
        == (NOW - timedelta(seconds=age)).isoformat()
    )
    assert source["purchase_price"] == price
    assert not source["actionable_quote"]


def test_missing_quote_geometry_and_no_per_good_history_fallback(
    ledger: Path,
) -> None:
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "exports": [{"symbol": "ORE"}],
            "tradeGoods": [
                {"symbol": "MEDICINE", "purchasePrice": 1, "tradeVolume": 1}
            ],
        },
    )
    observe(
        ledger,
        "market",
        "X-A-M",
        {
            "exports": [{"symbol": "ORE"}],
        },
    )
    sources = ore_sources(ledger)
    assert sources[1]["quote_status"] == "missing"
    assert sources[1]["quote_observed_at"] is None
    assert sources[2]["source"] == "X-A-M"
    assert sources[2]["distance"] is None
    assert sources[2]["geometry_status"] == "missing_waypoint_coordinates"
    assert sources[2]["purchase_price"] is None


@pytest.mark.parametrize(
    "accepted,fulfilled,blocker",
    [
        (False, True, "Contract already fulfilled"),
        (False, False, "Acceptance deadline expired"),
        (True, False, None),
    ],
)
def test_current_contract_status(
    ledger: Path,
    accepted: bool,
    fulfilled: bool,
    blocker: str | None,
) -> None:
    observe(
        ledger,
        "contract",
        "C",
        {
            "accepted": accepted,
            "fulfilled": fulfilled,
            "deadlineToAccept": "2089-01-01T00:00:00Z",
            "terms": {"deliver": [], "deadline": "2091-01-01T00:00:00Z"},
        },
    )
    result = shortlist(ledger)
    assert result["accepted"] == accepted
    assert result["fulfilled"] == fulfilled
    assert result["deliveries"] == []
    if blocker:
        assert blocker in result["sourcing_blockers"]
    else:
        assert not result["sourcing_blockers"]


def test_scope_isolation(ledger: Path) -> None:
    observe(
        ledger,
        "market",
        "X-A-E",
        {
            "exports": [{"symbol": "MEDICINE"}],
        },
        scope="other:agent",
    )
    assert len(ore_sources(ledger)) == 3
    with pytest.raises(ValueError, match="Unknown reset/agent scope"):
        contract_sources(ledger, "reset:other", "C")
    with pytest.raises(ValueError, match="Contract not found"):
        contract_sources(ledger, "other:agent", "C")


def test_closed_wal_retains_latest_committed_quote(ledger: Path) -> None:
    # Leave committed synthetic records in WAL even after closing the writer.
    no_checkpoint = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
    if no_checkpoint is None:
        pytest.skip("No-checkpoint-on-close config requires Python 3.12")
    before = ledger.read_bytes()
    store = Intelligence(ledger)
    try:
        setconfig = getattr(store.db, "setconfig", None)
        assert setconfig is not None
        setconfig(no_checkpoint, True)
        store.db.execute("PRAGMA wal_autocheckpoint=0")
        store.observe(
            SCOPE,
            "market",
            "X-A-E",
            {
                "exports": [{"symbol": "ORE"}],
                "tradeGoods": [
                    {"symbol": "ORE", "purchasePrice": 321, "tradeVolume": 7}
                ],
            },
            source="synthetic",
        )
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? "
                "WHERE id=(SELECT MAX(id) FROM observations)",
                (NOW.isoformat(),),
            )
    finally:
        store.close()
    assert ledger.read_bytes() == before
    assert Path(str(ledger) + "-wal").stat().st_size > 32

    source = ore_sources(ledger)[1]

    assert source["purchase_price"] == 321
    assert source["trade_volume"] == 7
    assert source["quote_age_seconds"] == 0
    assert source["actionable_quote"]


def test_cli_offline_no_record_writes_credentials_or_session(
    ledger: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ledger.parent)
    before = ledger.read_bytes()
    original_connect = sqlite3.connect
    statements: list[str] = []

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        assert args[0].endswith("?mode=ro") and kwargs["uri"]
        db: sqlite3.Connection = original_connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    with (
        patch("py_st.cli.auto_cmd.session", side_effect=AssertionError),
        patch("py_st.cli.auto_cmd.Session", side_effect=AssertionError),
        patch(
            "py_st.cli.auto_cmd.SpaceTradersClient", side_effect=AssertionError
        ),
        patch("py_st.cli.auto_cmd.load_dotenv", side_effect=AssertionError),
        patch("py_st.cli.auto_cmd.find_dotenv", side_effect=AssertionError),
        patch("sqlite3.connect", side_effect=connect),
    ):
        result = CliRunner().invoke(
            app,
            [
                "auto",
                "sources",
                "C",
                "--scope",
                SCOPE,
                "--database",
                str(ledger),
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "offline_only"
    # Main-file bytes and SQL are checked, not sidecar absence or immutability.
    # SQLite may create -wal/-shm or update shared memory in mode=ro.
    assert ledger.read_bytes() == before
    assert all(
        s.startswith(("SELECT", "BEGIN", "PRAGMA user_version"))
        for s in statements
    )
    assert not (ledger.parent / ".state").exists()


@pytest.mark.parametrize("force_color", [False, True])
def test_cli_missing_database_and_required_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    force_color: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    if force_color:
        monkeypatch.setenv("FORCE_COLOR", "1")
    else:
        monkeypatch.delenv("FORCE_COLOR", raising=False)
    result = CliRunner().invoke(app, ["auto", "sources", "C"])
    assert result.exit_code != 0
    assert "--scope" in unstyle(result.output)
    result = CliRunner().invoke(
        app,
        [
            "auto",
            "sources",
            "C",
            "--scope",
            SCOPE,
        ],
    )
    assert result.exit_code != 0
    assert "existing intelligence database" in unstyle(result.output)
    assert not (tmp_path / ".state").exists()
