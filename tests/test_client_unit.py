import httpx

from py_st._generated.models import Agent, Contract, Ship, Waypoint
from py_st.client import SpaceTradersClient
from tests.factories import (
    AgentFactory,
    ContractFactory,
    MarketTransactionFactory,
    ShipFactory,
    WaypointFactory,
)


def test_get_agent_parses_response() -> None:
    # Use factory for minimal valid Agent payload
    agent_json = AgentFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        # client base_url is ".../v2", and method calls "/my/agent"
        assert request.url.path == "/v2/my/agent"
        return httpx.Response(200, json={"data": agent_json})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    agent = st.agent.get_agent()

    # Type & field assertions
    assert isinstance(agent, Agent)
    assert agent.symbol == "FOO"
    assert agent.headquarters == "X1-ABC-1"
    assert agent.credits == 42
    assert agent.startingFaction == "COSMIC"
    assert agent.shipCount == 1


def test_get_contracts_parses_response() -> None:
    contract_json = ContractFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/contracts"
        return httpx.Response(200, json={"data": [contract_json]})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    contracts = st.contracts.get_contracts()

    assert len(contracts) == 1
    assert isinstance(contracts[0], Contract)
    assert contracts[0].id == "contract-1"
    assert contracts[0].factionSymbol == "COSMIC"
    assert contracts[0].type.value == "PROCUREMENT"


def test_get_ships_parses_response() -> None:
    ship_json = ShipFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/ships"
        return httpx.Response(200, json={"data": [ship_json]})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    ships = st.ships.get_ships()

    assert len(ships) == 1
    assert isinstance(ships[0], Ship)
    assert ships[0].symbol == "SHIP-1"


def test_negotiate_contract_parses_response() -> None:
    contract_json = ContractFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/ships/SHIP-1/negotiate/contract"
        assert request.method == "POST"
        return httpx.Response(200, json={"data": {"contract": contract_json}})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    result = st.contracts.negotiate_contract("SHIP-1")

    assert isinstance(result, Contract)
    assert result.id == "contract-1"
    assert result.factionSymbol == "COSMIC"


def test_accept_contract_parses_response() -> None:
    agent_json = AgentFactory.build_minimal()
    agent_json["credits"] = 1042  # Simulate update
    contract_json = ContractFactory.build_minimal()
    contract_json["accepted"] = True

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/contracts/contract-1/accept"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "data": {
                    "agent": agent_json,
                    "contract": contract_json,
                }
            },
        )

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    result = st.contracts.accept_contract("contract-1")

    assert "agent" in result
    assert "contract" in result
    assert isinstance(result["agent"], Agent)
    assert isinstance(result["contract"], Contract)
    assert result["agent"].credits == 1042
    assert result["contract"].accepted is True


def test_get_waypoints_in_system_parses_response() -> None:
    waypoint_json = WaypointFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/systems/X1-ABC/waypoints"
        return httpx.Response(200, json={"data": [waypoint_json]})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)
    waypoints = st.systems.get_waypoints_in_system("X1-ABC")

    assert len(waypoints) == 1
    assert isinstance(waypoints[0], Waypoint)
    assert waypoints[0].symbol.root == "X1-ABC-1"
    assert waypoints[0].type.value == "PLANET"


def test_purchase_cargo_parses_response() -> None:
    """Test purchase_cargo endpoint parses response correctly."""
    # Arrange
    agent_json = AgentFactory.build_minimal()
    agent_json["credits"] = 8500  # Simulate decreased credits after purchase

    ship_json = ShipFactory.build_minimal()
    cargo_json = ship_json["cargo"]
    cargo_json["units"] = 8
    cargo_json["capacity"] = 40

    transaction_json = MarketTransactionFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/ships/SHIP-1/purchase"
        assert request.method == "POST"
        # Verify payload
        import json

        payload = json.loads(request.content)
        assert payload["symbol"] == "SHIP_PARTS"
        assert payload["units"] == 8
        return httpx.Response(
            201,
            json={
                "data": {
                    "agent": agent_json,
                    "cargo": cargo_json,
                    "transaction": transaction_json,
                }
            },
        )

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)

    # Act
    result_agent, result_cargo, result_transaction = st.ships.purchase_cargo(
        "SHIP-1", "SHIP_PARTS", 8
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert result_agent.credits == 8500, "Agent credits should be updated"
    assert result_cargo.units == 8, "Cargo units should match purchase"
    assert result_cargo.capacity == 40, "Cargo capacity should be present"


def test_sell_cargo_parses_response() -> None:
    """Test sell_cargo endpoint parses response correctly."""
    # Arrange
    agent_json = AgentFactory.build_minimal()
    agent_json["credits"] = 11500  # Simulate increased credits after sale

    ship_json = ShipFactory.build_minimal()
    cargo_json = ship_json["cargo"]
    cargo_json["units"] = 2
    cargo_json["capacity"] = 40

    transaction_json = MarketTransactionFactory.build_minimal()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/ships/SHIP-1/sell"
        assert request.method == "POST"
        # Verify payload
        import json

        payload = json.loads(request.content)
        assert payload["symbol"] == "IRON_ORE"
        assert payload["units"] == 10
        return httpx.Response(
            201,
            json={
                "data": {
                    "agent": agent_json,
                    "cargo": cargo_json,
                    "transaction": transaction_json,
                }
            },
        )

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )
    st = SpaceTradersClient(token="T", client=fake_client)

    # Act
    result_agent, result_cargo, result_transaction = st.ships.sell_cargo(
        "SHIP-1", "IRON_ORE", 10
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert result_agent.credits == 11500, "Agent credits should be updated"
    assert result_cargo.units == 2, "Cargo units should be decreased"
    assert result_cargo.capacity == 40, "Cargo capacity should be present"
