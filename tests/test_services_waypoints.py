"""Unit tests for waypoint-related functions in systems.py."""

from typing import Any
from unittest.mock import MagicMock, patch

from py_st._generated.models import (
    Market,
    Shipyard,
    TradeSymbol,
    Waypoint,
    WaypointTraitSymbol,
)
from py_st.services import systems
from py_st.services.systems import MarketGoods, SystemGoods
from tests.factories import MarketFactory, ShipyardFactory, WaypointFactory


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_basic(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_waypoints returns waypoints via list_waypoints_all."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock waypoints
    waypoint1_data = WaypointFactory.build_minimal()
    waypoint2_data = WaypointFactory.build_minimal(symbol="X1-ABC-2")

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
    ]

    # Call the function
    result = systems.list_waypoints("fake_token", "X1-ABC", None)

    # Assertions
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(wp, Waypoint) for wp in result)
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"

    # Verify client was called correctly (via list_waypoints_all)
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_filter_single_trait(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_waypoints filters by a single trait."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints with different traits
    waypoint1_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-1", traits=[WaypointTraitSymbol.MARKETPLACE]
    )
    waypoint2_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-2", traits=[WaypointTraitSymbol.SHIPYARD]
    )
    waypoint3_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-3", traits=[WaypointTraitSymbol.MARKETPLACE]
    )

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)
    waypoint3 = Waypoint.model_validate(waypoint3_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
        waypoint3,
    ]

    # Call the function with single trait filter
    traits_filter = ["MARKETPLACE"]
    result = systems.list_waypoints("fake_token", "X1-ABC", traits_filter)

    # Assertions: only waypoints with MARKETPLACE trait are returned
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-3"

    # Verify that list_waypoints_all is called without traits
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_filter_multiple_traits_and_logic(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_waypoints filters using AND logic with multiple traits."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints with different trait combinations
    waypoint1_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-1",
        traits=[WaypointTraitSymbol.MARKETPLACE, WaypointTraitSymbol.SHIPYARD],
    )
    waypoint2_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-2", traits=[WaypointTraitSymbol.MARKETPLACE]
    )
    waypoint3_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-3", traits=[WaypointTraitSymbol.SHIPYARD]
    )
    waypoint4_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-4",
        traits=[
            WaypointTraitSymbol.MARKETPLACE,
            WaypointTraitSymbol.SHIPYARD,
            WaypointTraitSymbol.OUTPOST,
        ],
    )

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)
    waypoint3 = Waypoint.model_validate(waypoint3_data)
    waypoint4 = Waypoint.model_validate(waypoint4_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
        waypoint3,
        waypoint4,
    ]

    # Call the function with multiple trait filters (AND logic)
    traits_filter = ["MARKETPLACE", "SHIPYARD"]
    result = systems.list_waypoints("fake_token", "X1-ABC", traits_filter)

    # Assertions: only waypoints with BOTH traits are returned
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-4"

    # Verify that list_waypoints_all is called without traits
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_filter_excludes_partial_matches(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that waypoints with only some requested traits are excluded."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints where none have all three traits
    waypoint1_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-1",
        traits=[WaypointTraitSymbol.MARKETPLACE, WaypointTraitSymbol.SHIPYARD],
    )
    waypoint2_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-2",
        traits=[WaypointTraitSymbol.MARKETPLACE, WaypointTraitSymbol.OUTPOST],
    )
    waypoint3_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-3",
        traits=[WaypointTraitSymbol.SHIPYARD, WaypointTraitSymbol.OUTPOST],
    )

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)
    waypoint3 = Waypoint.model_validate(waypoint3_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
        waypoint3,
    ]

    # Request three traits - no waypoint has all three
    traits_filter = ["MARKETPLACE", "SHIPYARD", "OUTPOST"]
    result = systems.list_waypoints("fake_token", "X1-ABC", traits_filter)

    # Assertions: no waypoints returned (none have all three traits)
    assert isinstance(result, list)
    assert len(result) == 0


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_filter_includes_extra_traits(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that waypoints with requested traits plus extras are included."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints where some have extra traits beyond requested
    waypoint1_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-1",
        traits=[WaypointTraitSymbol.MARKETPLACE, WaypointTraitSymbol.SHIPYARD],
    )
    waypoint2_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-2",
        traits=[
            WaypointTraitSymbol.MARKETPLACE,
            WaypointTraitSymbol.SHIPYARD,
            WaypointTraitSymbol.OUTPOST,
            WaypointTraitSymbol.TRADING_HUB,
        ],
    )
    waypoint3_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-3", traits=[WaypointTraitSymbol.MARKETPLACE]
    )

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)
    waypoint3 = Waypoint.model_validate(waypoint3_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
        waypoint3,
    ]

    # Request two traits
    traits_filter = ["MARKETPLACE", "SHIPYARD"]
    result = systems.list_waypoints("fake_token", "X1-ABC", traits_filter)

    # Assertions: waypoints with both traits (including extras) are returned
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_no_traits_returns_all(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_waypoints returns all waypoints when no traits provided."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints
    waypoint1_data = WaypointFactory.build_minimal(symbol="X1-ABC-1")
    waypoint2_data = WaypointFactory.build_minimal(symbol="X1-ABC-2")

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
    ]

    # Call the function with None traits
    result = systems.list_waypoints("fake_token", "X1-ABC", None)

    # Assertions: all waypoints returned
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_empty_traits_returns_all(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_waypoints returns all waypoints with empty traits list."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create waypoints
    waypoint1_data = WaypointFactory.build_minimal(symbol="X1-ABC-1")
    waypoint2_data = WaypointFactory.build_minimal(symbol="X1-ABC-2")

    waypoint1 = Waypoint.model_validate(waypoint1_data)
    waypoint2 = Waypoint.model_validate(waypoint2_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
    ]

    # Call the function with empty traits list
    result = systems.list_waypoints("fake_token", "X1-ABC", [])

    # Assertions: all waypoints returned
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_filter_works_with_cached_data(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test filtering works correctly when data comes from cache."""
    # Setup: populate cache with waypoint data
    waypoint1_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-1",
        traits=[WaypointTraitSymbol.MARKETPLACE, WaypointTraitSymbol.SHIPYARD],
    )
    waypoint2_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-2", traits=[WaypointTraitSymbol.MARKETPLACE]
    )

    cached_data = {
        "waypoints_X1-ABC": {
            "last_updated": "2025-10-29T12:00:00+00:00",
            "data": [waypoint1_data, waypoint2_data],
        }
    }
    mock_load_cache.return_value = cached_data

    # Configure mock client (should NOT be called due to cache hit)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Call the function with trait filter
    traits_filter = ["MARKETPLACE", "SHIPYARD"]
    result = systems.list_waypoints("fake_token", "X1-ABC", traits_filter)

    # Assertions: filtering works correctly with cached data
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Verify API was NOT called (cache hit)
    mock_client.systems.list_waypoints_all.assert_not_called()
    mock_save_cache.assert_not_called()


@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard(mock_client_class: Any) -> None:
    """Test get_shipyard returns a Shipyard from the client."""
    # Create mock shipyard
    shipyard_data = ShipyardFactory.build_minimal(waypoint_symbol="X1-ABC-1")
    shipyard = Shipyard.model_validate(shipyard_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_shipyard.return_value = shipyard

    # Call the function
    result = systems.get_shipyard("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"
    assert len(result.shipTypes) == 2
    assert result.modificationsFee == 1000

    # Verify client was called correctly
    mock_client.systems.get_shipyard.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )


@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market(mock_client_class: Any) -> None:
    """Test get_market returns a Market from the client."""
    # Create mock market
    market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    market = Market.model_validate(market_data)

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_market.return_value = market

    # Call the function
    result = systems.get_market("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"
    assert len(result.exports) == 1
    assert result.exports[0].symbol == TradeSymbol.IRON_ORE
    assert len(result.imports) == 1
    assert result.imports[0].symbol == TradeSymbol.FUEL
    assert len(result.exchange) == 1
    assert result.exchange[0].symbol == TradeSymbol.FOOD

    # Verify client was called correctly
    mock_client.systems.get_market.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )


@patch("py_st.services.systems.SpaceTradersClient")
def test_list_system_goods_basic(mock_client_class: Any) -> None:
    """Test list_system_goods aggregates goods from multiple markets."""
    # Create waypoints - one with marketplace, one without
    waypoint1 = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-1", traits=[WaypointTraitSymbol.MARKETPLACE]
        )
    )
    waypoint2 = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-2", traits=[WaypointTraitSymbol.OUTPOST]
        )
    )
    waypoint3 = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-3", traits=[WaypointTraitSymbol.MARKETPLACE]
        )
    )

    # Create markets
    market1 = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-ABC-1",
            exports=[TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FUEL],
            exchange=[TradeSymbol.FOOD],
        )
    )
    market3 = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-ABC-3",
            exports=[TradeSymbol.COPPER_ORE],
            imports=[TradeSymbol.IRON_ORE],
            exchange=[TradeSymbol.FOOD],
        )
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
        waypoint3,
    ]

    # Mock get_market to return different markets
    def get_market_side_effect(system: str, waypoint: str) -> Market:
        if waypoint == "X1-ABC-1":
            return market1
        elif waypoint == "X1-ABC-3":
            return market3
        raise ValueError(f"Unexpected waypoint: {waypoint}")

    mock_client.systems.get_market.side_effect = get_market_side_effect

    # Call the function
    result = systems.list_system_goods("fake_token", "X1-ABC")

    # Assertions
    assert isinstance(result, SystemGoods)
    assert len(result.by_waypoint) == 2  # Only waypoints with marketplaces

    # Check waypoint1 goods
    assert "X1-ABC-1" in result.by_waypoint
    wp1_goods = result.by_waypoint["X1-ABC-1"]
    assert isinstance(wp1_goods, MarketGoods)

    # Waypoint1 sells: exports (IRON_ORE) + exchange (FOOD)
    assert len(wp1_goods.sells) == 2
    sell_symbols = [good.symbol for good in wp1_goods.sells]
    assert TradeSymbol.FOOD in sell_symbols
    assert TradeSymbol.IRON_ORE in sell_symbols

    # Waypoint1 buys: imports (FUEL) + exchange (FOOD)
    assert len(wp1_goods.buys) == 2
    buy_symbols = [good.symbol for good in wp1_goods.buys]
    assert TradeSymbol.FOOD in buy_symbols
    assert TradeSymbol.FUEL in buy_symbols

    # Check waypoint3 goods
    assert "X1-ABC-3" in result.by_waypoint
    wp3_goods = result.by_waypoint["X1-ABC-3"]

    # Waypoint3 sells: exports (COPPER_ORE) + exchange (FOOD)
    assert len(wp3_goods.sells) == 2
    sell_symbols3 = [good.symbol for good in wp3_goods.sells]
    assert TradeSymbol.COPPER_ORE in sell_symbols3
    assert TradeSymbol.FOOD in sell_symbols3

    # Waypoint3 buys: imports (IRON_ORE) + exchange (FOOD)
    assert len(wp3_goods.buys) == 2
    buy_symbols3 = [good.symbol for good in wp3_goods.buys]
    assert TradeSymbol.FOOD in buy_symbols3
    assert TradeSymbol.IRON_ORE in buy_symbols3

    # Check by_good index
    assert "FOOD" in result.by_good
    assert "IRON_ORE" in result.by_good
    assert "FUEL" in result.by_good
    assert "COPPER_ORE" in result.by_good

    # FOOD is sold and bought at both waypoints
    food_data = result.by_good["FOOD"]
    assert sorted(food_data["sells"]) == ["X1-ABC-1", "X1-ABC-3"]
    assert sorted(food_data["buys"]) == ["X1-ABC-1", "X1-ABC-3"]

    # IRON_ORE is sold at waypoint1, bought at waypoint3
    iron_ore_data = result.by_good["IRON_ORE"]
    assert iron_ore_data["sells"] == ["X1-ABC-1"]
    assert iron_ore_data["buys"] == ["X1-ABC-3"]

    # Verify client calls
    mock_client.systems.list_waypoints_all.assert_called_once_with("X1-ABC")
    assert (
        mock_client.systems.get_market.call_count == 2
    )  # Called for 2 marketplaces


@patch("py_st.services.systems.SpaceTradersClient")
def test_list_system_goods_no_marketplaces(mock_client_class: Any) -> None:
    """Test list_system_goods handles systems with no marketplaces."""
    # Create waypoints without marketplaces
    waypoint1 = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-1", traits=[WaypointTraitSymbol.OUTPOST]
        )
    )
    waypoint2 = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-2", traits=[WaypointTraitSymbol.SHIPYARD]
        )
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
    ]

    # Call the function
    result = systems.list_system_goods("fake_token", "X1-ABC")

    # Assertions
    assert isinstance(result, SystemGoods)
    assert len(result.by_waypoint) == 0
    assert len(result.by_good) == 0

    # Verify get_market was never called
    mock_client.systems.get_market.assert_not_called()


@patch("py_st.services.systems.SpaceTradersClient")
def test_list_system_goods_deduplicates_goods(mock_client_class: Any) -> None:
    """Test list_system_goods deduplicates goods in sells/buys lists."""
    # Create waypoint with marketplace
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-1", traits=[WaypointTraitSymbol.MARKETPLACE]
        )
    )

    # Create market where FOOD appears in both exports and exchange
    # This should only appear once in the sells list
    market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-ABC-1",
            exports=[TradeSymbol.FOOD, TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FUEL],
            exchange=[TradeSymbol.FOOD],  # FOOD appears again
        )
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]
    mock_client.systems.get_market.return_value = market

    # Call the function
    result = systems.list_system_goods("fake_token", "X1-ABC")

    # Assertions
    wp_goods = result.by_waypoint["X1-ABC-1"]

    # FOOD should only appear once in sells
    sell_symbols = [good.symbol for good in wp_goods.sells]
    assert sell_symbols.count(TradeSymbol.FOOD) == 1

    # FOOD should also appear in buys (from exchange)
    buy_symbols = [good.symbol for good in wp_goods.buys]
    assert TradeSymbol.FOOD in buy_symbols


@patch("py_st.services.systems.SpaceTradersClient")
def test_list_system_goods_sorts_goods(mock_client_class: Any) -> None:
    """Test list_system_goods returns sorted lists of goods."""
    # Create waypoint with marketplace
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(
            symbol="X1-ABC-1", traits=[WaypointTraitSymbol.MARKETPLACE]
        )
    )

    # Create market with multiple goods
    market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-ABC-1",
            exports=[
                TradeSymbol.IRON_ORE,
                TradeSymbol.COPPER_ORE,
                TradeSymbol.FUEL,
            ],
            imports=[TradeSymbol.FOOD, TradeSymbol.AMMUNITION],
            exchange=[],
        )
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]
    mock_client.systems.get_market.return_value = market

    # Call the function
    result = systems.list_system_goods("fake_token", "X1-ABC")

    # Assertions
    wp_goods = result.by_waypoint["X1-ABC-1"]

    # Check that sells are sorted
    sell_symbols = [good.symbol.value for good in wp_goods.sells]
    assert sell_symbols == sorted(sell_symbols)

    # Check that buys are sorted
    buy_symbols = [good.symbol.value for good in wp_goods.buys]
    assert buy_symbols == sorted(buy_symbols)


# ============================================================================
# Caching Tests for list_waypoints_all
# ============================================================================


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_cache_miss(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that cache miss causes API call and saves data to cache."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock waypoints
    waypoint1 = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-1")
    )
    waypoint2 = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-2")
    )

    # Configure mock client to return waypoints
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [
        waypoint1,
        waypoint2,
    ]

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was called
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 2
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"

    # Assert: save_cache was called with proper structure
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert "waypoints_X1-ABC" in saved_cache
    cache_entry = saved_cache["waypoints_X1-ABC"]
    assert "last_updated" in cache_entry
    assert "data" in cache_entry
    assert isinstance(cache_entry["data"], list)
    assert len(cache_entry["data"]) == 2


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_cache_hit(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that cache hit returns data without calling API."""
    # Setup: populate cache with waypoint data
    waypoint1_data = WaypointFactory.build_minimal(symbol="X1-ABC-1")
    waypoint2_data = WaypointFactory.build_minimal(symbol="X1-ABC-2")

    cached_data = {
        "waypoints_X1-ABC": {
            "last_updated": "2025-10-29T12:00:00+00:00",
            "data": [waypoint1_data, waypoint2_data],
        }
    }
    mock_load_cache.return_value = cached_data

    # Configure mock client (should NOT be called)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was NOT called
    mock_client.systems.list_waypoints_all.assert_not_called()

    # Assert: result matches cached data
    assert len(result) == 2
    assert isinstance(result[0], Waypoint)
    assert isinstance(result[1], Waypoint)
    assert result[0].symbol.root == "X1-ABC-1"
    assert result[1].symbol.root == "X1-ABC-2"

    # Assert: save_cache was NOT called
    mock_save_cache.assert_not_called()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_invalid_cache_entry_missing_keys(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that invalid cache entry (missing keys) triggers API call."""
    # Setup: cache with invalid entry (missing 'data' key)
    cached_data = {
        "waypoints_X1-ABC": {
            "last_updated": "2025-10-29T12:00:00+00:00",
            # Missing 'data' key
        }
    }
    mock_load_cache.return_value = cached_data

    # Create mock waypoints
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-1")
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was called due to invalid cache
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Assert: save_cache was called to update cache
    mock_save_cache.assert_called_once()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_invalid_cache_entry_bad_data(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that invalid cache data (failed validation) triggers API call."""
    # Setup: cache with malformed waypoint data
    cached_data = {
        "waypoints_X1-ABC": {
            "last_updated": "2025-10-29T12:00:00+00:00",
            "data": [
                {"invalid": "data", "missing": "required_fields"}
            ],  # Invalid waypoint
        }
    }
    mock_load_cache.return_value = cached_data

    # Create mock waypoints
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-1")
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was called due to validation failure
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Assert: save_cache was called to update cache with valid data
    mock_save_cache.assert_called_once()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_cache_entry_not_dict(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that cache entry that's not a dict triggers API call."""
    # Setup: cache with entry that's not a dict
    cached_data = {
        "waypoints_X1-ABC": "invalid_string_value"  # Should be a dict
    }
    mock_load_cache.return_value = cached_data

    # Create mock waypoints
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-1")
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was called due to invalid cache structure
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Assert: save_cache was called to update cache
    mock_save_cache.assert_called_once()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_list_waypoints_all_cache_data_not_list(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test that cache entry with non-list data triggers API call."""
    # Setup: cache with data that's not a list
    cached_data = {
        "waypoints_X1-ABC": {
            "last_updated": "2025-10-29T12:00:00+00:00",
            "data": "should_be_a_list_not_string",  # Invalid: not a list
        }
    }
    mock_load_cache.return_value = cached_data

    # Create mock waypoints
    waypoint = Waypoint.model_validate(
        WaypointFactory.build_minimal(symbol="X1-ABC-1")
    )

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.list_waypoints_all.return_value = [waypoint]

    # Call the function
    result = systems.list_waypoints_all("fake_token", "X1-ABC")

    # Assertions: API was called due to invalid data type
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Assert: save_cache was called to update cache
    mock_save_cache.assert_called_once()
