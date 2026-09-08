from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.contract_planning import plan_contract_procurement


def contract(*, accepted: bool = False) -> dict[str, object]:
    deadline = datetime.now(UTC) + timedelta(hours=8)
    return {
        "id": "C-MULTI",
        "accepted": accepted,
        "terms": {
            "deadline": deadline.isoformat(),
            "payment": {"onAccepted": 10_000, "onFulfilled": 80_000},
            "deliver": [
                {
                    "tradeSymbol": "EQUIPMENT",
                    "destinationSymbol": "X-A-D",
                    "unitsRequired": 55,
                    "unitsFulfilled": 5,
                },
                {
                    "tradeSymbol": "MEDICINE",
                    "destinationSymbol": "X-A-D",
                    "unitsRequired": 10,
                    "unitsFulfilled": 0,
                },
            ],
        },
    }


def quotes() -> list[dict[str, object]]:
    return [
        {
            "trade_symbol": "EQUIPMENT",
            "source": "X-A-CHEAP",
            "destination": "X-A-D",
            "purchase_price": 400,
            "trade_volume": 20,
            "available_units": 30,
            "fuel_cost": 100,
            "travel_seconds": 600,
        },
        {
            "trade_symbol": "EQUIPMENT",
            "source": "X-A-BULK",
            "destination": "X-A-D",
            "purchase_price": 450,
            "trade_volume": 50,
            "available_units": 50,
            "fuel_cost": 100,
            "travel_seconds": 300,
        },
        {
            "trade_symbol": "MEDICINE",
            "source": "X-A-MED",
            "destination": "X-A-D",
            "purchase_price": 500,
            "trade_volume": 5,
            "fuel_cost": 50,
            "travel_seconds": 200,
        },
    ]


def test_models_all_goods_loads_batches_and_reserves() -> None:
    # Arrange / Act
    plan = plan_contract_procurement(
        contract(), quotes(), ship_capacity=40, credits=150_000
    )

    # Assert
    assert plan["feasible"] is True
    assert plan["execution_authorized"] is False
    assert plan["remaining_units"] == 60
    assert plan["cargo_trips"] == 3
    assert [(step["source"], step["units"]) for step in plan["steps"]] == [
        ("X-A-CHEAP", 30),
        ("X-A-BULK", 20),
        ("X-A-MED", 10),
    ]
    assert [step["purchase_batches"] for step in plan["steps"]] == [2, 1, 2]
    assert plan["required_credits"] == 82_450
    assert plan["conservative_net"] == 57_550


def test_reports_every_independent_infeasibility() -> None:
    # Arrange
    offer = contract()
    offer["terms"]["deadline"] = (  # type: ignore[index]
        datetime.now(UTC) + timedelta(minutes=5)
    ).isoformat()

    # Act
    plan = plan_contract_procurement(
        offer,
        quotes()[:1],
        ship_capacity=40,
        credits=1_000,
    )

    # Assert
    assert plan["feasible"] is False
    assert plan["reasons"] == [
        "Missing 20 units of EQUIPMENT capacity",
        "Missing 10 units of MEDICINE capacity",
        "Insufficient modeled deadline margin",
        "Insufficient credits for goods, fuel, and reserves",
    ]


def test_accepted_obligation_does_not_require_future_profit() -> None:
    # Arrange
    offer = contract(accepted=True)
    offer["terms"]["payment"] = {  # type: ignore[index]
        "onAccepted": 10_000,
        "onFulfilled": 1,
    }

    # Act
    plan = plan_contract_procurement(
        offer, quotes(), ship_capacity=40, credits=150_000
    )

    # Assert
    assert plan["future_revenue"] == 1
    assert plan["conservative_net"] < 0
    assert plan["feasible"] is True


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data.update(ship_capacity=0), "ship_capacity"),
        (
            lambda data: data["quotes"][0].update(purchase_price=0),
            "purchase_price",
        ),
        (
            lambda data: data["contract"]["terms"]["deliver"][0].update(
                unitsFulfilled=56
            ),
            "unitsFulfilled",
        ),
    ],
)
def test_rejects_unsafe_or_malformed_inputs(
    change: Callable[[dict[str, object]], None], message: str
) -> None:
    # Arrange
    data = {
        "contract": contract(),
        "quotes": quotes(),
        "ship_capacity": 40,
        "credits": 150_000,
    }
    change(data)

    # Act / Assert
    with pytest.raises(ValueError, match=message):
        plan_contract_procurement(
            data["contract"],  # type: ignore[arg-type]
            data["quotes"],  # type: ignore[arg-type]
            ship_capacity=data["ship_capacity"],  # type: ignore[arg-type]
            credits=data["credits"],  # type: ignore[arg-type]
        )


def test_offline_cli_never_opens_a_session(tmp_path: Path) -> None:
    # Arrange
    fixture = tmp_path / "contract.json"
    fixture.write_text(
        json.dumps(
            {
                "contract": contract(),
                "quotes": quotes(),
                "ship_capacity": 40,
                "credits": 150_000,
            }
        ),
        encoding="utf-8",
    )

    # Act
    result = CliRunner().invoke(app, ["auto", "contract-model", str(fixture)])

    # Assert
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["mode"] == "offline counterfactual"
    assert output["contract"] == "C-MULTI"
    assert output["execution_authorized"] is False
