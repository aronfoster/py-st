"""Unit tests for ship-related functions in services/ships.py."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from py_st._generated.models import (
    Agent,
    Extraction,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    ShipyardTransaction,
    Survey,
)
from py_st._manual_models import RefineResult
from py_st.client import APIError
from py_st.services import ships
from tests.factories import (
    AgentFactory,
    ExtractionFactory,
    MarketTransactionFactory,
    RefineResultFactory,
    ShipFactory,
    ShipyardTransactionFactory,
    SurveyFactory,
)


@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
@patch("py_st.services.ships.SpaceTradersClient")
def test_list_ships(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_ships returns a list of Ship objects."""
    # Arrange
    mock_load_cache.return_value = {}

    ship1_data = ShipFactory.build_minimal()
    ship2_data = ShipFactory.build_minimal()
    ship2_data["symbol"] = "SHIP-2"

    ship1 = Ship.model_validate(ship1_data)
    ship2 = Ship.model_validate(ship2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [ship1, ship2]

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, Ship) for s in result)
    assert result[0].symbol == "SHIP-1"
    assert result[1].symbol == "SHIP-2"

    mock_client.ships.get_ships.assert_called_once()


@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
@patch("py_st.services.ships.SpaceTradersClient")
def test_navigate_ship(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test navigate_ship calls client and marks cache dirty."""
    # Arrange
    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": "2024-01-01T00:00:00Z",
            "is_dirty": False,
            "data": [],
        }
    }

    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.navigate_ship.return_value = nav

    # Act
    result = ships.navigate_ship("fake_token", "SHIP-1", "X1-ABC-2")

    # Assert
    assert isinstance(result, ShipNav), "Should return ShipNav object"
    assert (
        result.waypointSymbol.root == "X1-ABC-1"
    ), "Should contain waypoint from factory"

    mock_client.ships.navigate_ship.assert_called_once_with(
        "SHIP-1", "X1-ABC-2"
    )

    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["ship_list"]["is_dirty"] is True
    ), "Should mark ship list cache as dirty"
    assert (
        saved_cache["ship_list"]["last_updated"] == "2024-01-01T00:00:00Z"
    ), "Should not update timestamp"


@patch("py_st.services.ships.SpaceTradersClient")
def test_orbit_ship(mock_client_class: Any) -> None:
    """Test orbit_ship calls client correctly."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.orbit_ship.return_value = nav

    # Act
    result = ships.orbit_ship("fake_token", "SHIP-1")

    # Assert
    assert isinstance(result, ShipNav), "Should return ShipNav object"
    mock_client.ships.orbit_ship.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_dock_ship(mock_client_class: Any) -> None:
    """Test dock_ship calls client correctly."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.dock_ship.return_value = nav

    # Act
    result = ships.dock_ship("fake_token", "SHIP-1")

    # Assert
    assert isinstance(result, ShipNav), "Should return ShipNav object"
    mock_client.ships.dock_ship.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_no_survey(mock_client_class: Any) -> None:
    """Test extract_resources without a survey."""
    # Arrange
    extraction_data = ExtractionFactory.build_minimal()
    extraction = Extraction.model_validate(extraction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.return_value = extraction

    # Act
    result = ships.extract_resources("fake_token", "SHIP-1", survey_json=None)

    # Assert
    assert isinstance(result, Extraction), "Should return Extraction object"
    assert result.shipSymbol == "SHIP-1", "Ship symbol should match"
    assert result.yield_.units == 10, "Should return expected yield units"

    mock_client.ships.extract_resources.assert_called_once_with(
        "SHIP-1", survey=None
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_with_survey(mock_client_class: Any) -> None:
    """Test extract_resources with a valid survey JSON string."""
    # Arrange
    extraction_data = ExtractionFactory.build_minimal()
    extraction = Extraction.model_validate(extraction_data)

    survey_data = SurveyFactory.build_minimal()
    import json

    survey_json = json.dumps(survey_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.return_value = extraction

    # Act
    result = ships.extract_resources(
        "fake_token", "SHIP-1", survey_json=survey_json
    )

    # Assert
    assert isinstance(result, Extraction), "Should return Extraction object"

    mock_client.ships.extract_resources.assert_called_once()
    call_args = mock_client.ships.extract_resources.call_args
    assert call_args[0][0] == "SHIP-1", "Ship symbol should match"
    assert isinstance(
        call_args[1]["survey"], Survey
    ), "Survey should be parsed as Survey object"


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_api_error(mock_client_class: Any) -> None:
    """Test extract_resources handles APIError and returns None."""
    # Arrange
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.side_effect = APIError(
        "Extraction failed"
    )

    # Act
    result = ships.extract_resources("fake_token", "SHIP-1", survey_json=None)

    # Assert
    assert result is None, "Should return None on API error"
    mock_client.ships.extract_resources.assert_called_once()


@patch("py_st.services.ships.SpaceTradersClient")
def test_create_survey(mock_client_class: Any) -> None:
    """Test create_survey returns a list of Survey objects."""
    # Arrange
    survey1_data = SurveyFactory.build_minimal()
    survey2_data = SurveyFactory.build_minimal()
    survey2_data["signature"] = "survey-signature-67890"

    survey1 = Survey.model_validate(survey1_data)
    survey2 = Survey.model_validate(survey2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.create_survey.return_value = [survey1, survey2]

    # Act
    result = ships.create_survey("fake_token", "SHIP-1")

    # Assert
    assert isinstance(result, list), "Should return list of surveys"
    assert len(result) == 2, "Should return 2 surveys"
    assert all(
        isinstance(s, Survey) for s in result
    ), "All items should be Survey objects"

    mock_client.ships.create_survey.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_refuel_ship_no_units(mock_client_class: Any) -> None:
    """Test refuel_ship without specifying units."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    fuel_data = ship_data["fuel"]
    fuel = ShipFuel.model_validate(fuel_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refuel_ship.return_value = (agent, fuel, transaction)

    # Act
    result_agent, result_fuel, result_transaction = ships.refuel_ship(
        "fake_token", "SHIP-1", units=None
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(result_fuel, ShipFuel), "Should return ShipFuel object"
    assert isinstance(
        result_transaction, MarketTransaction
    ), "Should return MarketTransaction object"

    mock_client.ships.refuel_ship.assert_called_once_with("SHIP-1", None)


@patch("py_st.services.ships.SpaceTradersClient")
def test_refuel_ship_with_units(mock_client_class: Any) -> None:
    """Test refuel_ship with specific units."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    fuel_data = ship_data["fuel"]
    fuel = ShipFuel.model_validate(fuel_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refuel_ship.return_value = (agent, fuel, transaction)

    # Act
    result_agent, result_fuel, result_transaction = ships.refuel_ship(
        "fake_token", "SHIP-1", units=100
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(result_fuel, ShipFuel), "Should return ShipFuel object"
    assert isinstance(
        result_transaction, MarketTransaction
    ), "Should return MarketTransaction object"

    mock_client.ships.refuel_ship.assert_called_once_with("SHIP-1", 100)


@patch("py_st.services.ships.SpaceTradersClient")
def test_jettison_cargo(mock_client_class: Any) -> None:
    """Test jettison_cargo calls client with correct arguments."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.jettison_cargo.return_value = cargo

    # Act
    result = ships.jettison_cargo("fake_token", "SHIP-1", "IRON_ORE", 50)

    # Assert
    assert isinstance(result, ShipCargo), "Should return ShipCargo object"

    mock_client.ships.jettison_cargo.assert_called_once_with(
        "SHIP-1", "IRON_ORE", 50
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_set_flight_mode(mock_client_class: Any) -> None:
    """Test set_flight_mode passes flight_mode enum correctly."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.set_flight_mode.return_value = nav

    # Act
    result = ships.set_flight_mode(
        "fake_token", "SHIP-1", ShipNavFlightMode.CRUISE
    )

    # Assert
    assert isinstance(result, ShipNav), "Should return ShipNav object"

    mock_client.ships.set_flight_mode.assert_called_once_with(
        "SHIP-1", ShipNavFlightMode.CRUISE
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_refine_materials(mock_client_class: Any) -> None:
    """Test refine_materials calls client with correct arguments."""
    # Arrange
    refine_data = RefineResultFactory.build_minimal()
    refine_result = RefineResult.model_validate(refine_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refine_materials.return_value = refine_result

    # Act
    result = ships.refine_materials("fake_token", "SHIP-1", "FUEL")

    # Assert
    assert isinstance(result, RefineResult), "Should return RefineResult"
    assert isinstance(result.cargo, ShipCargo), "Should contain ShipCargo"
    assert len(result.produced) > 0, "Should have produced items"
    assert len(result.consumed) > 0, "Should have consumed items"

    mock_client.ships.refine_materials.assert_called_once_with(
        "SHIP-1", "FUEL"
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_sell_cargo(mock_client_class: Any) -> None:
    """Test sell_cargo calls client with correct arguments."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.sell_cargo.return_value = (agent, cargo, transaction)

    # Act
    result_agent, result_cargo, result_transaction = ships.sell_cargo(
        "fake_token", "SHIP-1", "IRON_ORE", 10
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(result_cargo, ShipCargo), "Should return ShipCargo"
    assert isinstance(
        result_transaction, MarketTransaction
    ), "Should return MarketTransaction"

    mock_client.ships.sell_cargo.assert_called_once_with(
        "SHIP-1", "IRON_ORE", 10
    )


@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test purchase_cargo calls client and marks cache dirty."""
    # Arrange
    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": "2024-01-01T00:00:00Z",
            "is_dirty": False,
            "data": [],
        }
    }

    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act
    result_agent, result_cargo, result_transaction = ships.purchase_cargo(
        "fake_token", "SHIP-1", "SHIP_PARTS", 8
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(result_cargo, ShipCargo), "Should return ShipCargo"
    assert isinstance(
        result_transaction, MarketTransaction
    ), "Should return MarketTransaction"

    mock_client.ships.purchase_cargo.assert_called_once_with(
        "SHIP-1", "SHIP_PARTS", 8
    )

    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["ship_list"]["is_dirty"] is True
    ), "Should mark ship list cache as dirty"
    assert (
        saved_cache["ship_list"]["last_updated"] == "2024-01-01T00:00:00Z"
    ), "Should not update timestamp"


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo_with_different_amounts(mock_client_class: Any) -> None:
    """Test purchase_cargo with various unit amounts."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act - Test with 1 unit
    ships.purchase_cargo("fake_token", "SHIP-1", "FUEL", 1)

    # Assert
    mock_client.ships.purchase_cargo.assert_called_with("SHIP-1", "FUEL", 1)

    # Act - Test with large amount
    ships.purchase_cargo("fake_token", "SHIP-2", "IRON_ORE", 100)

    # Assert
    assert (
        mock_client.ships.purchase_cargo.call_count == 2
    ), "Should be called twice"
    mock_client.ships.purchase_cargo.assert_called_with(
        "SHIP-2", "IRON_ORE", 100
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo_multiple_goods(mock_client_class: Any) -> None:
    """Test purchasing different trade goods."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act - Purchase different goods
    goods_to_purchase = ["SHIP_PARTS", "FUEL", "IRON_ORE", "FOOD"]
    for good in goods_to_purchase:
        result_agent, result_cargo, result_transaction = ships.purchase_cargo(
            "fake_token", "SHIP-1", good, 5
        )

        # Assert each returns correct types
        assert isinstance(
            result_agent, Agent
        ), f"Should return Agent for {good}"
        assert isinstance(
            result_cargo, ShipCargo
        ), f"Should return ShipCargo for {good}"
        assert isinstance(
            result_transaction, MarketTransaction
        ), f"Should return MarketTransaction for {good}"


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo_updates_agent_credits(mock_client_class: Any) -> None:
    """Test purchase_cargo returns updated agent with decreased credits."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent_data["credits"] = 8000  # Decreased from original 42
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction_data["totalPrice"] = 2000
    transaction_data["type"] = "PURCHASE"
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act
    result_agent, result_cargo, result_transaction = ships.purchase_cargo(
        "fake_token", "SHIP-1", "SHIP_PARTS", 10
    )

    # Assert
    assert (
        result_agent.credits == 8000
    ), "Agent credits should be decreased after purchase"
    assert (
        result_transaction.totalPrice == 2000
    ), "Transaction should reflect purchase price"
    assert (
        result_transaction.type.value == "PURCHASE"
    ), "Transaction type should be PURCHASE"


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo_updates_ship_cargo(mock_client_class: Any) -> None:
    """Test purchase_cargo returns updated cargo with increased units."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo_data["units"] = 25  # Increased from some previous amount
    cargo_data["capacity"] = 40
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act
    result_agent, result_cargo, result_transaction = ships.purchase_cargo(
        "fake_token", "SHIP-1", "IRON_ORE", 15
    )

    # Assert
    assert result_cargo.units == 25, "Cargo units should be updated"
    assert result_cargo.capacity == 40, "Cargo capacity should be present"
    assert isinstance(
        result_cargo.inventory, list
    ), "Cargo should have inventory"


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_cargo_with_different_ships(mock_client_class: Any) -> None:
    """Test purchase_cargo works with different ship symbols."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_cargo.return_value = (agent, cargo, transaction)

    # Act - Test with various ship naming patterns
    ship_symbols = [
        "SHIP-1",
        "MY-SHIP-ABC",
        "TRADER-001",
        "MINING-DRONE-5",
    ]

    for ship_symbol in ship_symbols:
        ships.purchase_cargo("fake_token", ship_symbol, "FUEL", 10)

    # Assert - Verify all calls were made correctly
    assert (
        mock_client.ships.purchase_cargo.call_count == 4
    ), "Should handle different ship symbols"


@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_ship(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test purchase_ship calls client and marks cache dirty."""
    # Arrange
    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": "2024-01-01T00:00:00Z",
            "is_dirty": False,
            "data": [],
        }
    }

    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    ship = Ship.model_validate(ship_data)

    transaction_data = ShipyardTransactionFactory.build_minimal()
    transaction = ShipyardTransaction.model_validate(transaction_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_ship.return_value = (agent, ship, transaction)

    # Act
    result_agent, result_ship, result_transaction = ships.purchase_ship(
        "fake_token", "SHIP_MINING_DRONE", "X1-ABC-1"
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(result_ship, Ship), "Should return Ship object"
    assert isinstance(
        result_transaction, ShipyardTransaction
    ), "Should return ShipyardTransaction"

    mock_client.ships.purchase_ship.assert_called_once_with(
        "SHIP_MINING_DRONE", "X1-ABC-1"
    )

    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["ship_list"]["is_dirty"] is True
    ), "Should mark ship list cache as dirty"
    assert (
        saved_cache["ship_list"]["last_updated"] == "2024-01-01T00:00:00Z"
    ), "Should not update timestamp"


# ===== Cache Tests =====


@patch("py_st.services.ships.SpaceTradersClient")
@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
def test_list_ships_cache_hit(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test list_ships returns cached data when cache is clean."""
    # Arrange
    now = datetime.now(UTC)

    ship1_data = ShipFactory.build_minimal()
    ship2_data = ShipFactory.build_minimal()
    ship2_data["symbol"] = "SHIP-2"

    cached_ships = [ship1_data, ship2_data]

    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": now.isoformat(),
            "is_dirty": False,
            "data": cached_ships,
        }
    }

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of ships"
    assert len(result) == 2, "Should return 2 cached ships"
    assert all(
        isinstance(s, Ship) for s in result
    ), "All items should be Ship objects"
    assert result[0].symbol == "SHIP-1", "First ship symbol should match"
    assert result[1].symbol == "SHIP-2", "Second ship symbol should match"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_not_called()
    mock_client_class.assert_not_called()


@patch("py_st.services.ships.SpaceTradersClient")
@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
def test_list_ships_cache_miss_dirty(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test list_ships fetches fresh data when cache is dirty."""
    # Arrange
    now = datetime.now(UTC)

    old_ship_data = ShipFactory.build_minimal()
    old_ship_data["symbol"] = "OLD-SHIP"

    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": now.isoformat(),
            "is_dirty": True,
            "data": [old_ship_data],
        }
    }

    new_ship1_data = ShipFactory.build_minimal()
    new_ship2_data = ShipFactory.build_minimal()
    new_ship2_data["symbol"] = "NEW-SHIP-2"

    new_ship1 = Ship.model_validate(new_ship1_data)
    new_ship2 = Ship.model_validate(new_ship2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [new_ship1, new_ship2]

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of ships"
    assert len(result) == 2, "Should return 2 fresh ships"
    assert (
        result[0].symbol == "SHIP-1"
    ), "Should have new data, not old cached data"
    assert (
        result[1].symbol == "NEW-SHIP-2"
    ), "Should have new data, not old cached data"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.ships.get_ships.assert_called_once()

    # Verify the saved cache has is_dirty set to False
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["ship_list"]["is_dirty"] is False
    ), "Saved cache should have is_dirty set to False"


@patch("py_st.services.ships.SpaceTradersClient")
@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
def test_list_ships_cache_miss_no_dirty_flag(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test list_ships treats missing is_dirty flag as dirty."""
    # Arrange
    now = datetime.now(UTC)

    old_ship_data = ShipFactory.build_minimal()
    old_ship_data["symbol"] = "OLD-SHIP"

    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": now.isoformat(),
            "data": [old_ship_data],
        }
    }

    new_ship1_data = ShipFactory.build_minimal()
    new_ship2_data = ShipFactory.build_minimal()
    new_ship2_data["symbol"] = "NEW-SHIP-2"

    new_ship1 = Ship.model_validate(new_ship1_data)
    new_ship2 = Ship.model_validate(new_ship2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [new_ship1, new_ship2]

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of ships"
    assert len(result) == 2, "Should return 2 fresh ships"
    assert (
        result[0].symbol == "SHIP-1"
    ), "Should fetch new data when is_dirty is missing"
    assert (
        result[1].symbol == "NEW-SHIP-2"
    ), "Should fetch new data when is_dirty is missing"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.ships.get_ships.assert_called_once()

    # Verify the saved cache has is_dirty set to False
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["ship_list"]["is_dirty"] is False
    ), "Saved cache should have is_dirty set to False"


@patch("py_st.services.ships.SpaceTradersClient")
@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
def test_list_ships_cache_miss_not_found(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test list_ships fetches data when cache entry doesn't exist."""
    # Arrange
    mock_load_cache.return_value = {}

    ship1_data = ShipFactory.build_minimal()
    ship2_data = ShipFactory.build_minimal()
    ship2_data["symbol"] = "SHIP-2"

    ship1 = Ship.model_validate(ship1_data)
    ship2 = Ship.model_validate(ship2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [ship1, ship2]

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of ships"
    assert len(result) == 2, "Should return 2 ships from API"
    assert result[0].symbol == "SHIP-1", "First ship symbol should match"
    assert result[1].symbol == "SHIP-2", "Second ship symbol should match"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.ships.get_ships.assert_called_once()


@patch("py_st.services.ships.SpaceTradersClient")
@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
def test_list_ships_cache_invalid_data(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test list_ships handles invalid cached data gracefully."""
    # Arrange
    now = datetime.now(UTC)

    invalid_ship_data = {
        "symbol": "SHIP-1",
    }

    mock_load_cache.return_value = {
        "ship_list": {
            "last_updated": now.isoformat(),
            "is_dirty": False,
            "data": [invalid_ship_data],
        }
    }

    ship1_data = ShipFactory.build_minimal()
    ship2_data = ShipFactory.build_minimal()
    ship2_data["symbol"] = "SHIP-2"

    ship1 = Ship.model_validate(ship1_data)
    ship2 = Ship.model_validate(ship2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [ship1, ship2]

    # Act
    result = ships.list_ships("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of ships"
    assert len(result) == 2, "Should fetch fresh data on invalid cache"
    assert (
        result[0].symbol == "SHIP-1"
    ), "Should return valid data from API, not invalid cache"
    assert (
        result[1].symbol == "SHIP-2"
    ), "Should return valid data from API, not invalid cache"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.ships.get_ships.assert_called_once()


@patch("py_st.services.ships.cache.save_cache")
@patch("py_st.services.ships.cache.load_cache")
@patch("py_st.services.ships.SpaceTradersClient")
def test_mark_ship_list_dirty_no_cache(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test ship-mutating operations skip dirty-flag when cache missing."""
    # Arrange
    mock_load_cache.return_value = {}

    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.navigate_ship.return_value = nav

    # Act
    result = ships.navigate_ship("fake_token", "SHIP-1", "X1-ABC-2")

    # Assert
    assert isinstance(result, ShipNav), "Should return ShipNav object"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_not_called()
