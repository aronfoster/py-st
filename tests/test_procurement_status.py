"""Offline progress joins use synthetic records, never execution authority."""

from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from py_st.services.doctor import diagnose
from py_st.services.intelligence import Intelligence
from py_st.services.procurement_status import procurement_status


@pytest.fixture
def evidence() -> tuple[dict[str, Any], list[Any], list[Any]]:
    position = {
        "key": "procurement:C",
        "observed_at": "2026-09-10T00:00:00Z",
        "data": {
            "status": "open",
            "plan": {
                "contract": "C",
                "ship": "S",
                "source": "X-A-M",
                "destination": "X-A-M",
            },
        },
    }
    contract = {
        "key": "C",
        "observed_at": "2026-09-10T00:01:00Z",
        "data": {
            "id": "C",
            "accepted": True,
            "fulfilled": False,
            "deadlineToAccept": "2099-01-01T00:00:00Z",
            "terms": {
                "deadline": "2099-01-02T00:00:00Z",
                "deliver": [
                    {
                        "tradeSymbol": good,
                        "destinationSymbol": "X-A-M",
                        "unitsRequired": required,
                        "unitsFulfilled": delivered,
                    }
                    for good, required, delivered in (
                        ("IRON", 10, 4),
                        ("COPPER", 5, 0),
                    )
                ],
            },
        },
    }
    ship = {
        "key": "S",
        "observed_at": "2026-09-10T00:02:00Z",
        "data": {
            "symbol": "S",
            "cargo": {
                "units": 3,
                "inventory": [{"symbol": "IRON", "units": 3}],
            },
        },
    }
    return position, [contract], [ship]


def test_partial_progress_preserves_provenance_and_inputs(
    evidence: tuple[dict[str, Any], list[Any], list[Any]],
) -> None:
    before = deepcopy(evidence)

    result = procurement_status(*evidence)

    assert result["execution_authorized"] is False
    assert result["status"] == "recorded"
    assert "owned cargo" in result["next_step"]
    assert result["goods"] == [
        {
            "good": "IRON",
            "required": 10,
            "delivered": 4,
            "remaining": 6,
            "held": 3,
            "to_acquire": 3,
            "excess": 0,
        },
        {
            "good": "COPPER",
            "required": 5,
            "delivered": 0,
            "remaining": 5,
            "held": 0,
            "to_acquire": 5,
            "excess": 0,
        },
    ]
    assert len(set(result["observations"].values())) == 3
    assert evidence == before


@pytest.mark.parametrize(
    "change",
    ["missing_ship", "wrong_identity", "duplicate", "inventory", "quantity"],
)
def test_unknown_evidence_never_invents_empty_cargo_or_complete_delivery(
    evidence: tuple[dict[str, Any], list[Any], list[Any]], change: str
) -> None:
    _, contracts, ships = evidence
    if change == "missing_ship":
        ships.clear()
    elif change == "wrong_identity":
        contracts[0]["data"]["id"] = "OTHER"
    elif change == "duplicate":
        terms = contracts[0]["data"]["terms"]["deliver"]
        terms.append(deepcopy(terms[0]))
    elif change == "inventory":
        ships[0]["data"]["cargo"]["inventory"] = []
    else:
        contracts[0]["data"]["terms"]["deliver"][0]["unitsFulfilled"] = True

    result = procurement_status(*evidence)

    assert result["status"] == "unknown"
    assert result["goods"] == []
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("stage", ["offered", "acquire", "fulfill", "closed"])
def test_recorded_next_step(
    evidence: tuple[dict[str, Any], list[Any], list[Any]], stage: str
) -> None:
    _, contracts, ships = evidence
    contract = contracts[0]["data"]
    ships[0]["data"]["cargo"].update(units=0, inventory=[])
    expected = "whole-obligation funding"
    if stage == "offered":
        contract["accepted"] = False
        expected = "original offer"
    elif stage in ("fulfill", "closed"):
        for term in contract["terms"]["deliver"]:
            term["unitsFulfilled"] = term["unitsRequired"]
        expected = "Review fulfillment"
        if stage == "closed":
            contract["fulfilled"] = True
            expected = "local closure"

    result = procurement_status(*evidence)

    assert result["status"] == "recorded"
    assert expected in result["next_step"]


@pytest.mark.parametrize("change", ["excess", "unrelated", "false_completion"])
def test_contradictory_cargo_or_completion_needs_review(
    evidence: tuple[dict[str, Any], list[Any], list[Any]], change: str
) -> None:
    _, contracts, ships = evidence
    cargo = ships[0]["data"]["cargo"]
    if change == "excess":
        cargo["units"] = cargo["inventory"][0]["units"] = 7
    elif change == "unrelated":
        cargo["inventory"][0]["symbol"] = "OTHER"
    else:
        contracts[0]["data"]["fulfilled"] = True

    result = procurement_status(*evidence)

    assert result["status"] == "needs_review"
    assert "untracked cargo" in result["next_step"]
    assert result["execution_authorized"] is False


def test_doctor_joins_latest_scoped_progress_without_writing(
    evidence: tuple[dict[str, Any], list[Any], list[Any]], tmp_path: Path
) -> None:
    # Arrange: another reset's identically named ship must not supply cargo.
    path = tmp_path / "ledger.sqlite3"
    position, contracts, ships = evidence
    with closing(Intelligence(path)) as store:
        for kind, record in (
            ("position", position),
            ("contract", contracts[0]),
            ("ship", ships[0]),
        ):
            store.observe("reset:A", kind, record["key"], record["data"])
        newer = deepcopy(contracts[0]["data"])
        newer["terms"]["deliver"][0]["unitsFulfilled"] = 6
        store.observe("reset:A", "contract", "C", newer)
        other = deepcopy(ships[0]["data"])
        other["cargo"].update(units=0, inventory=[])
        store.observe("other:A", "ship", "S", other)
        before = store.db.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]

        # Act
        report = diagnose(
            path, "reset:A", root=tmp_path, now=datetime.now(UTC)
        )

        # Assert: latest progress, original scope cargo, no local mutation.
        finding = next(
            f
            for f in report["findings"]
            if f["code"] == "procurement_recovery"
        )
        iron = finding["procurement"]["goods"][0]
        assert (iron["remaining"], iron["held"], iron["to_acquire"]) == (
            4,
            3,
            1,
        )
        assert finding["procurement"]["execution_authorized"] is False
        assert (
            store.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            == before
        )


@pytest.mark.parametrize(
    "stamp,state",
    [
        ("2026-09-10T00:00:01Z", "open"),
        ("2026-09-10T00:00:00Z", "expired"),
        ("2026-09-09T23:59:59Z", "expired"),
        ("2026-09-10T00:00:01", "unknown"),
        (None, "unknown"),
    ],
)
@pytest.mark.parametrize("kind", ["acceptance", "delivery"])
def test_recorded_deadlines_use_explicit_report_clock(
    evidence: tuple[dict[str, Any], list[Any], list[Any]],
    stamp: str | None,
    state: str,
    kind: str,
) -> None:
    contract = evidence[1][0]["data"]
    if kind == "acceptance":
        contract.update(accepted=False, deadlineToAccept=stamp)
    else:
        contract["terms"]["deadline"] = stamp

    result = procurement_status(
        *evidence, now=datetime(2026, 9, 10, tzinfo=UTC)
    )

    assert result["deadlines"][kind]["state"] == state
    assert result["status"] == (
        "recorded" if state == "open" else "needs_review"
    )
    if state == "unknown":
        assert result["deadlines"][kind]["remaining_seconds"] is None
    elif state == "open":
        assert result["deadlines"][kind]["remaining_seconds"] == 1
    assert result["execution_authorized"] is False


def test_completed_contract_can_still_need_local_closure_after_deadline(
    evidence: tuple[dict[str, Any], list[Any], list[Any]],
) -> None:
    _, contracts, ships = evidence
    contracts[0]["data"]["fulfilled"] = True
    contracts[0]["data"]["terms"]["deadline"] = "2026-09-09T00:00:00Z"
    for term in contracts[0]["data"]["terms"]["deliver"]:
        term["unitsFulfilled"] = term["unitsRequired"]
    ships[0]["data"]["cargo"].update(units=0, inventory=[])

    result = procurement_status(
        *evidence, now=datetime(2026, 9, 10, tzinfo=UTC)
    )

    assert result["deadlines"]["delivery"]["state"] == "expired"
    assert result["status"] == "recorded"
    assert "closure" in result["next_step"]
