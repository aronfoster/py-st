"""Unit tests for ship-related functions in services/ships.py."""

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


@patch("py_st.services.ships.SpaceTradersClient")
def test_list_ships(mock_client_class: Any) -> None:
    """Test list_ships returns a list of Ship objects."""
    # Create mock ships
    ship1_data = ShipFactory.build_minimal()
    ship2_data = ShipFactory.build_minimal()
    ship2_data["symbol"] = "SHIP-2"

    ship1 = Ship.model_validate(ship1_data)
    ship2 = Ship.model_validate(ship2_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.get_ships.return_value = [ship1, ship2]

    # Call the function
    result = ships.list_ships("fake_token")

    # Assertions
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, Ship) for s in result)
    assert result[0].symbol == "SHIP-1"
    assert result[1].symbol == "SHIP-2"

    # Verify client was called correctly
    mock_client.ships.get_ships.assert_called_once()


@patch("py_st.services.ships.SpaceTradersClient")
def test_navigate_ship(mock_client_class: Any) -> None:
    """Test navigate_ship calls client with correct arguments."""
    # Create mock ShipNav
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.navigate_ship.return_value = nav

    # Call the function
    result = ships.navigate_ship("fake_token", "SHIP-1", "X1-ABC-2")

    # Assertions
    assert isinstance(result, ShipNav)
    assert result.waypointSymbol.root == "X1-ABC-1"

    # Verify client was called with correct arguments
    mock_client.ships.navigate_ship.assert_called_once_with(
        "SHIP-1", "X1-ABC-2"
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_orbit_ship(mock_client_class: Any) -> None:
    """Test orbit_ship calls client correctly."""
    # Create mock ShipNav
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.orbit_ship.return_value = nav

    # Call the function
    result = ships.orbit_ship("fake_token", "SHIP-1")

    # Assertions
    assert isinstance(result, ShipNav)

    # Verify client was called with correct arguments
    mock_client.ships.orbit_ship.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_dock_ship(mock_client_class: Any) -> None:
    """Test dock_ship calls client correctly."""
    # Create mock ShipNav
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.dock_ship.return_value = nav

    # Call the function
    result = ships.dock_ship("fake_token", "SHIP-1")

    # Assertions
    assert isinstance(result, ShipNav)

    # Verify client was called with correct arguments
    mock_client.ships.dock_ship.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_no_survey(mock_client_class: Any) -> None:
    """Test extract_resources without a survey."""
    # Create mock Extraction
    extraction_data = ExtractionFactory.build_minimal()
    extraction = Extraction.model_validate(extraction_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.return_value = extraction

    # Call the function
    result = ships.extract_resources("fake_token", "SHIP-1", survey_json=None)

    # Assertions
    assert isinstance(result, Extraction)
    assert result.shipSymbol == "SHIP-1"
    assert result.yield_.units == 10

    # Verify client was called with survey=None
    mock_client.ships.extract_resources.assert_called_once_with(
        "SHIP-1", survey=None
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_with_survey(mock_client_class: Any) -> None:
    """Test extract_resources with a valid survey JSON string."""
    # Create mock Extraction
    extraction_data = ExtractionFactory.build_minimal()
    extraction = Extraction.model_validate(extraction_data)

    # Create a survey JSON string
    survey_data = SurveyFactory.build_minimal()
    import json

    survey_json = json.dumps(survey_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.return_value = extraction

    # Call the function
    result = ships.extract_resources(
        "fake_token", "SHIP-1", survey_json=survey_json
    )

    # Assertions
    assert isinstance(result, Extraction)

    # Verify client was called with a Survey object
    mock_client.ships.extract_resources.assert_called_once()
    call_args = mock_client.ships.extract_resources.call_args
    assert call_args[0][0] == "SHIP-1"
    assert isinstance(call_args[1]["survey"], Survey)


@patch("py_st.services.ships.SpaceTradersClient")
def test_extract_resources_api_error(mock_client_class: Any) -> None:
    """Test extract_resources handles APIError and returns None."""
    # Configure mock client to raise APIError
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.extract_resources.side_effect = APIError(
        "Extraction failed"
    )

    # Call the function
    result = ships.extract_resources("fake_token", "SHIP-1", survey_json=None)

    # Assertions
    assert result is None

    # Verify client was called
    mock_client.ships.extract_resources.assert_called_once()


@patch("py_st.services.ships.SpaceTradersClient")
def test_create_survey(mock_client_class: Any) -> None:
    """Test create_survey returns a list of Survey objects."""
    # Create mock surveys
    survey1_data = SurveyFactory.build_minimal()
    survey2_data = SurveyFactory.build_minimal()
    survey2_data["signature"] = "survey-signature-67890"

    survey1 = Survey.model_validate(survey1_data)
    survey2 = Survey.model_validate(survey2_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.create_survey.return_value = [survey1, survey2]

    # Call the function
    result = ships.create_survey("fake_token", "SHIP-1")

    # Assertions
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, Survey) for s in result)

    # Verify client was called correctly
    mock_client.ships.create_survey.assert_called_once_with("SHIP-1")


@patch("py_st.services.ships.SpaceTradersClient")
def test_refuel_ship_no_units(mock_client_class: Any) -> None:
    """Test refuel_ship without specifying units."""
    # Create mock data
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    fuel_data = ship_data["fuel"]
    fuel = ShipFuel.model_validate(fuel_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refuel_ship.return_value = (agent, fuel, transaction)

    # Call the function
    result_agent, result_fuel, result_transaction = ships.refuel_ship(
        "fake_token", "SHIP-1", units=None
    )

    # Assertions
    assert isinstance(result_agent, Agent)
    assert isinstance(result_fuel, ShipFuel)
    assert isinstance(result_transaction, MarketTransaction)

    # Verify client was called with units=None
    mock_client.ships.refuel_ship.assert_called_once_with("SHIP-1", None)


@patch("py_st.services.ships.SpaceTradersClient")
def test_refuel_ship_with_units(mock_client_class: Any) -> None:
    """Test refuel_ship with specific units."""
    # Create mock data
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    fuel_data = ship_data["fuel"]
    fuel = ShipFuel.model_validate(fuel_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refuel_ship.return_value = (agent, fuel, transaction)

    # Call the function
    result_agent, result_fuel, result_transaction = ships.refuel_ship(
        "fake_token", "SHIP-1", units=100
    )

    # Assertions
    assert isinstance(result_agent, Agent)
    assert isinstance(result_fuel, ShipFuel)
    assert isinstance(result_transaction, MarketTransaction)

    # Verify client was called with units=100
    mock_client.ships.refuel_ship.assert_called_once_with("SHIP-1", 100)


@patch("py_st.services.ships.SpaceTradersClient")
def test_jettison_cargo(mock_client_class: Any) -> None:
    """Test jettison_cargo calls client with correct arguments."""
    # Create mock ShipCargo
    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.jettison_cargo.return_value = cargo

    # Call the function
    result = ships.jettison_cargo("fake_token", "SHIP-1", "IRON_ORE", 50)

    # Assertions
    assert isinstance(result, ShipCargo)

    # Verify client was called with correct arguments
    mock_client.ships.jettison_cargo.assert_called_once_with(
        "SHIP-1", "IRON_ORE", 50
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_set_flight_mode(mock_client_class: Any) -> None:
    """Test set_flight_mode passes flight_mode enum correctly."""
    # Create mock ShipNav
    ship_data = ShipFactory.build_minimal()
    nav_data = ship_data["nav"]
    nav = ShipNav.model_validate(nav_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.set_flight_mode.return_value = nav

    # Call the function
    result = ships.set_flight_mode(
        "fake_token", "SHIP-1", ShipNavFlightMode.CRUISE
    )

    # Assertions
    assert isinstance(result, ShipNav)

    # Verify client was called with correct flight mode
    mock_client.ships.set_flight_mode.assert_called_once_with(
        "SHIP-1", ShipNavFlightMode.CRUISE
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_refine_materials(mock_client_class: Any) -> None:
    """Test refine_materials calls client with correct arguments."""
    # Create mock RefineResult
    refine_data = RefineResultFactory.build_minimal()
    refine_result = RefineResult.model_validate(refine_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.refine_materials.return_value = refine_result

    # Call the function
    result = ships.refine_materials("fake_token", "SHIP-1", "FUEL")

    # Assertions
    assert isinstance(result, RefineResult)
    assert isinstance(result.cargo, ShipCargo)
    assert len(result.produced) > 0
    assert len(result.consumed) > 0

    # Verify client was called with correct arguments
    mock_client.ships.refine_materials.assert_called_once_with(
        "SHIP-1", "FUEL"
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_sell_cargo(mock_client_class: Any) -> None:
    """Test sell_cargo calls client with correct arguments."""
    # Create mock data
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo = ShipCargo.model_validate(cargo_data)

    transaction_data = MarketTransactionFactory.build_minimal()
    transaction = MarketTransaction.model_validate(transaction_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.sell_cargo.return_value = (agent, cargo, transaction)

    # Call the function
    result_agent, result_cargo, result_transaction = ships.sell_cargo(
        "fake_token", "SHIP-1", "IRON_ORE", 10
    )

    # Assertions
    assert isinstance(result_agent, Agent)
    assert isinstance(result_cargo, ShipCargo)
    assert isinstance(result_transaction, MarketTransaction)

    # Verify client was called with correct arguments
    mock_client.ships.sell_cargo.assert_called_once_with(
        "SHIP-1", "IRON_ORE", 10
    )


@patch("py_st.services.ships.SpaceTradersClient")
def test_purchase_ship(mock_client_class: Any) -> None:
    """Test purchase_ship calls client with correct arguments."""
    # Create mock data
    agent_data = AgentFactory.build_minimal()
    agent = Agent.model_validate(agent_data)

    ship_data = ShipFactory.build_minimal()
    ship = Ship.model_validate(ship_data)

    transaction_data = ShipyardTransactionFactory.build_minimal()
    transaction = ShipyardTransaction.model_validate(transaction_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.ships.purchase_ship.return_value = (agent, ship, transaction)

    # Call the function
    result_agent, result_ship, result_transaction = ships.purchase_ship(
        "fake_token", "SHIP_MINING_DRONE", "X1-ABC-1"
    )

    # Assertions
    assert isinstance(result_agent, Agent)
    assert isinstance(result_ship, Ship)
    assert isinstance(result_transaction, ShipyardTransaction)

    # Verify client was called with correct arguments
    mock_client.ships.purchase_ship.assert_called_once_with(
        "SHIP_MINING_DRONE", "X1-ABC-1"
    )
