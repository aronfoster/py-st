from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from py_st.cli.auto_cmd import auto_app
from py_st.services.automation import SafetyStop
from py_st.services.doctor import diagnose
from py_st.services.local_procurement import local_contract_run
from py_st.services.pilot import pilot_run
from py_st.services.procurement_recovery import abandon_procurement
from tests.test_local_procurement import local  # noqa: F401

REASON = "Expired offer; release original unaccepted local intent."


@pytest.fixture
def intent(local: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    # Arrange: create the real persisted intent before the accept budget guard.
    local["run"].remaining = 0
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    local["contract"]["deadlineToAccept"] = "2000-01-01T00:00:00Z"
    local["run"].execute = False
    return local


def test_preview_and_explicit_abandon_retain_history(
    intent: dict[str, Any],
) -> None:
    store = intent["store"]
    original = store.latest("r:A", "position")
    actions = store.actions("r:A")
    plans = store.latest("r:A", "plan")

    assert (
        abandon_procurement(intent["run"], "C")["status"] == "ready to abandon"
    )
    assert store.latest("r:A", "position") == original
    result = abandon_procurement(
        intent["run"], "C", execute=True, reason=REASON
    )

    assert result["status"] == "abandoned"
    closed = store.latest("r:A", "position")
    assert closed[0]["data"] == original[0]["data"] | {
        "status": "closed",
        "stage": "abandoned",
        "purchased": False,
        "cancellation_reason": REASON,
    }
    assert store.latest("r:A", "plan") == plans
    assert store.actions("r:A") == actions
    assert intent["posts"] == []
    assert (
        store.db.execute(
            "SELECT COUNT(*) FROM observations WHERE kind='position'"
        ).fetchone()[0]
        == 2
    )
    assert (
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)[
            "status"
        ]
        == "already abandoned"
    )
    assert store.latest("r:A", "position") == closed
    with pytest.raises(SafetyStop, match="Original local-multi"):
        local_contract_run(intent["run"], "S", "C")


@pytest.mark.parametrize(
    "status",
    ["not_sent", "rejected", "pending", "succeeded", "reviewed", "unknown"],
)
@pytest.mark.parametrize("scope", ["r:A", "old:OTHER"])
def test_all_acceptance_receipts_without_report_cap(
    intent: dict[str, Any], status: str, scope: str
) -> None:
    store = intent["store"]
    action = store.begin_action(scope, "/my/contracts/C/accept", None)
    store.finish_action(action, status, {})
    for _ in range(201):
        action = store.begin_action(scope, "/my/ships/OTHER/dock", None)
        store.finish_action(action, "succeeded", {})
    before = store.latest("r:A", "position")

    if scope != "r:A" or status in ("not_sent", "rejected"):
        assert (
            abandon_procurement(
                intent["run"], "C", execute=True, reason=REASON
            )["status"]
            == "abandoned"
        )
    else:
        with pytest.raises(SafetyStop, match="Acceptance journal"):
            abandon_procurement(
                intent["run"], "C", execute=True, reason=REASON
            )
        assert store.latest("r:A", "position") == before
    assert intent["posts"] == []


@pytest.mark.parametrize("field", ["accepted", "fulfilled"])
@pytest.mark.parametrize("value", [True, 0, 1, "false", None])
def test_contract_flags_fail_closed(
    intent: dict[str, Any], field: str, value: Any
) -> None:
    intent["contract"][field] = value
    before = intent["store"].latest("r:A", "position")
    with pytest.raises(SafetyStop, match="flags|unaccepted"):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert intent["store"].latest("r:A", "position") == before
    assert intent["posts"] == []


@pytest.mark.parametrize(
    "change",
    [
        "cargo",
        "inventory",
        "units",
        "moved",
        "mode",
        "transit",
        "other",
        "pending",
        "position",
        "missing",
        "scope",
        "unknown",
        "identity",
        "closed",
    ],
)
def test_blockers_never_close(intent: dict[str, Any], change: str) -> None:
    store = intent["store"]
    ship = intent["ship"]
    if change == "cargo":
        ship["cargo"].update(
            units=1, inventory=[{"symbol": "IRON", "units": 1}]
        )
    elif change == "inventory":
        ship["cargo"]["inventory"] = [{"symbol": "IRON", "units": 0}]
    elif change == "units":
        ship["cargo"]["units"] = False
    elif change == "moved":
        ship["nav"]["waypointSymbol"] = "X-A-OTHER"
    elif change == "mode":
        ship["nav"]["flightMode"] = "DRIFT"
    elif change == "transit":
        ship["nav"]["status"] = "IN_TRANSIT"
    elif change == "other":
        intent["contracts"].append(
            {"id": "OTHER", "accepted": True, "fulfilled": False}
        )
    elif change == "pending":
        store.begin_action("r:A", "/my/ships/OTHER/dock", None)
    elif change == "position":
        store.observe("r:A", "position", "trade:OTHER", {"status": "open"})
    elif change == "missing":
        intent["contracts"].clear()
    elif change in ("scope", "unknown"):
        intent["run"].scope = ""
        intent["client"].status.return_value = {
            "resetDate": "other" if change == "scope" else None
        }
    elif change in ("identity", "closed"):
        p = store.latest("r:A", "position")[0]["data"]
        if change == "identity":
            p["plan"]["contract"] = "OTHER"
        else:
            p.update(status="closed", stage="fulfilled")
        store.observe("r:A", "position", "procurement:C", p)
    before = store.latest("r:A", "position")
    with pytest.raises(SafetyStop):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert store.latest("r:A", "position") == before
    assert intent["posts"] == []


@pytest.mark.parametrize(
    "change",
    ["contract", "ship", "position", "pending", "stop", "time", "duplicate"],
)
def test_changed_preflight_state(intent: dict[str, Any], change: str) -> None:
    request = intent["client"].request.side_effect
    reads = 0

    def changed(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal reads
        if path == "/my/ships/S":
            reads += 1
            if reads == 1:
                if change == "contract":
                    intent["contract"]["accepted"] = True
                elif change == "ship":
                    intent["ship"]["nav"]["waypointSymbol"] = "X-A-OTHER"
                elif change == "position":
                    p = intent["store"].latest("r:A", "position")[0]["data"]
                    intent["store"].observe(
                        "r:A", "position", "procurement:C", p
                    )
                elif change == "pending":
                    intent["store"].begin_action(
                        "r:A", "/my/ships/OTHER/dock", None
                    )
                elif change == "stop":
                    (intent["root"] / "STOP").touch()
                elif change == "time":
                    intent["run"].deadline = 0
        result = request(method, path, **kwargs)
        if path == "/my/ships" and change == "duplicate":
            result.append(deepcopy(result[0]))
        return result

    intent["client"].request.side_effect = changed
    with pytest.raises(SafetyStop):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert (
        intent["store"].latest("r:A", "position")[0]["data"]["status"]
        == "open"
    )
    assert intent["posts"] == []
    if change == "stop":
        assert (intent["root"] / "STOP").exists()


def test_old_remote_plan_supported(intent: dict[str, Any]) -> None:
    p = intent["store"].latest("r:A", "position")[0]["data"]
    p.pop("strategy")
    p["plan"] = {
        "ship": "S",
        "source": "X-A-M",
        "destination": "X-A-D",
        "contract": "C",
        "good": "IRON",
    }
    intent["contract"]["terms"]["deliver"] = [
        intent["contract"]["terms"]["deliver"][0]
    ]
    intent["contract"]["terms"]["deliver"][0]["destinationSymbol"] = "X-A-D"
    intent["store"].observe("r:A", "position", "procurement:C", p)
    assert (
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)[
            "status"
        ]
        == "abandoned"
    )
    assert intent["posts"] == []


@pytest.mark.parametrize("reason", ["", "too short", " " * 30])
def test_execution_reason_required(
    intent: dict[str, Any], reason: str
) -> None:
    with pytest.raises(SafetyStop, match="reason"):
        abandon_procurement(intent["run"], "C", execute=True, reason=reason)


def test_cli_help_and_local_only_authority(intent: dict[str, Any]) -> None:
    runner = CliRunner()
    assert (
        runner.invoke(auto_app, ["abandon-procurement", "--help"]).exit_code
        == 0
    )
    with patch("py_st.cli.auto_cmd.session") as session:
        session.return_value.__enter__.return_value = intent["run"]
        result = runner.invoke(
            auto_app,
            ["abandon-procurement", "C", "--execute", "--reason", REASON],
        )
        assert result.exit_code == 0, result.output
        session.assert_called_once_with(False, 120, 1)
    assert not intent["run"].execute
    assert intent["posts"] == []


@pytest.mark.parametrize("field", ["purchased", "held", "delivered"])
def test_recorded_acquisition_is_not_discarded(
    intent: dict[str, Any], field: str
) -> None:
    store = intent["store"]
    p = store.latest("r:A", "position")[0]["data"]
    p[field] = True if field == "purchased" else 1
    store.observe("r:A", "position", "procurement:C", p)
    before = store.latest("r:A", "position")
    with pytest.raises(SafetyStop, match="Recorded acquisition"):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert store.latest("r:A", "position") == before


@pytest.mark.parametrize("location", ["position", "plan"])
@pytest.mark.parametrize("change", ["held", "delivered", "missing", "invalid"])
def test_multi_good_evidence_is_not_discarded(
    intent: dict[str, Any], location: str, change: str
) -> None:
    # Arrange: fresh empty cargo does not erase contradictory saved progress.
    store = intent["store"]
    position = store.latest("r:A", "position")[0]["data"]
    record = position if location == "position" else position["plan"]
    if change == "held":
        record["goods"]["IRON"].update(held=1, to_buy=4)
    elif change == "delivered":
        record["goods"]["IRON"].update(remaining=4, to_buy=4)
    elif change == "missing":
        record["goods"].pop("IRON")
    else:
        record["goods"]["IRON"]["held"] = False
    store.observe("r:A", "position", "procurement:C", position)
    before = store.latest("r:A", "position")

    # Act / Assert
    with pytest.raises(SafetyStop, match="Recorded multi-good"):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert store.latest("r:A", "position") == before
    assert intent["posts"] == []


def test_final_refresh_contract_change_blocks_write(
    intent: dict[str, Any],
) -> None:
    request = intent["client"].request.side_effect
    reads = 0

    def changed(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal reads
        if path == "/my/contracts":
            reads += 1
            if reads == 2:
                intent["contract"]["accepted"] = True
        return request(method, path, **kwargs)

    intent["client"].request.side_effect = changed
    before = intent["store"].latest("r:A", "position")
    with pytest.raises(SafetyStop, match="unaccepted"):
        abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    assert reads == 2
    assert intent["store"].latest("r:A", "position") == before
    assert intent["posts"] == []


def test_no_intent_is_not_created(local: dict[str, Any]) -> None:  # noqa: F811
    with pytest.raises(SafetyStop, match="original procurement intent"):
        abandon_procurement(local["run"], "C", execute=True, reason=REASON)
    assert local["store"].latest("r:A", "position") == []
    assert local["store"].latest("r:A", "automation_run") == []
    assert local["posts"] == []


def test_invalid_cli_reason_does_not_start_session() -> None:
    with patch("py_st.cli.auto_cmd.session") as session:
        result = CliRunner().invoke(
            auto_app, ["abandon-procurement", "C", "--execute"]
        )
    assert result.exit_code == 2
    session.assert_not_called()


def test_closed_intent_is_not_a_doctor_or_pilot_recovery(
    intent: dict[str, Any],
) -> None:
    abandon_procurement(intent["run"], "C", execute=True, reason=REASON)
    result = diagnose(
        intent["root"] / "ledger.sqlite3", "r:A", root=intent["root"]
    )
    assert result["exit_code"] == 0
    with (
        patch("py_st.services.pilot.contract_run") as recover,
        patch(
            "py_st.services.pilot.earn_run", return_value={"status": "dry run"}
        ) as earn,
        pytest.raises(SafetyStop, match="No open procurement"),
    ):
        pilot_run(intent["run"], "X-A", recover_contracts=True)
    recover.assert_not_called()
    earn.assert_not_called()
    assert intent["posts"] == []
