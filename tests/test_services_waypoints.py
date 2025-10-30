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
    """Test list_waypoints returns waypoints via internal fetch function."""
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

    # Verify client was called correctly (via _fetch_and_cache_waypoints)
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


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_legacy(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test get_market returns a Market from the client (legacy test)."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

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


# ============================================================================
# Smart Caching Tests for get_market
# ============================================================================


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_cache_hit_no_refresh(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 1: Cache hit, no refresh.

    Returns cached data without API call.
    """
    from py_st._generated.models import MarketTradeGood, SupplyLevel
    from py_st._generated.models.MarketTradeGood import (
        Type as MarketTradeGoodType,
    )

    # Setup: populate cache with market data (with tradeGoods)
    trade_goods = [
        MarketTradeGood(
            symbol=TradeSymbol.IRON_ORE,
            type=MarketTradeGoodType.EXPORT,
            tradeVolume=100,
            supply=SupplyLevel.ABUNDANT,
            purchasePrice=50,
            sellPrice=45,
        )
    ]

    market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    market_dict = Market.model_validate(market_data).model_dump(mode="json")
    market_dict["tradeGoods"] = [
        tg.model_dump(mode="json") for tg in trade_goods
    ]

    cached_data = {
        "market_X1-ABC-1": {
            "prices_updated": "2025-10-29T12:00:00+00:00",
            "data": market_dict,
        }
    }
    mock_load_cache.return_value = cached_data

    # Configure mock client (should NOT be called)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Call the function without force_refresh
    result = systems.get_market("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API was NOT called
    mock_client.systems.get_market.assert_not_called()

    # Assert: result matches cached data
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"
    assert result.tradeGoods is not None
    assert len(result.tradeGoods) == 1
    assert result.tradeGoods[0].symbol == TradeSymbol.IRON_ORE

    # Assert: save_cache was NOT called
    mock_save_cache.assert_not_called()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_cache_miss_with_prices(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test Case 2a: Cache miss, API returns with prices."""
    from py_st._generated.models import MarketTradeGood, SupplyLevel
    from py_st._generated.models.MarketTradeGood import (
        Type as MarketTradeGoodType,
    )

    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock market with tradeGoods
    trade_goods = [
        MarketTradeGood(
            symbol=TradeSymbol.IRON_ORE,
            type=MarketTradeGoodType.EXPORT,
            tradeVolume=100,
            supply=SupplyLevel.ABUNDANT,
            purchasePrice=50,
            sellPrice=45,
        )
    ]

    market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    market = Market.model_validate(market_data)
    market.tradeGoods = trade_goods

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_market.return_value = market

    # Call the function
    result = systems.get_market("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API was called
    mock_client.systems.get_market.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result matches API response
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"
    assert result.tradeGoods is not None
    assert len(result.tradeGoods) == 1

    # Assert: save_cache was called with new data and new timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert "market_X1-ABC-1" in saved_cache
    cache_entry = saved_cache["market_X1-ABC-1"]
    assert "prices_updated" in cache_entry
    assert cache_entry["prices_updated"] is not None
    assert "data" in cache_entry
    assert cache_entry["data"]["tradeGoods"] is not None


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_cache_miss_without_prices(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test Case 2b: Cache miss, API returns without prices."""
    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock market WITHOUT tradeGoods
    market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    market = Market.model_validate(market_data)
    # tradeGoods is already None from factory

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_market.return_value = market

    # Call the function
    result = systems.get_market("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API was called
    mock_client.systems.get_market.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result matches API response
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"
    assert result.tradeGoods is None

    # Assert: save_cache was called with new data and None timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert "market_X1-ABC-1" in saved_cache
    cache_entry = saved_cache["market_X1-ABC-1"]
    assert "prices_updated" in cache_entry
    assert cache_entry["prices_updated"] is None
    assert "data" in cache_entry
    assert cache_entry["data"]["tradeGoods"] is None


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_force_refresh_with_prices(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test Case 3: Cache hit, force_refresh=True, API returns with prices."""
    from py_st._generated.models import MarketTradeGood, SupplyLevel
    from py_st._generated.models.MarketTradeGood import (
        Type as MarketTradeGoodType,
    )

    # Setup: populate cache with old market data
    old_trade_goods = [
        MarketTradeGood(
            symbol=TradeSymbol.IRON_ORE,
            type=MarketTradeGoodType.EXPORT,
            tradeVolume=100,
            supply=SupplyLevel.ABUNDANT,
            purchasePrice=50,
            sellPrice=45,
        )
    ]

    old_market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    old_market_dict = Market.model_validate(old_market_data).model_dump(
        mode="json"
    )
    old_market_dict["tradeGoods"] = [
        tg.model_dump(mode="json") for tg in old_trade_goods
    ]

    cached_data = {
        "market_X1-ABC-1": {
            "prices_updated": "2025-10-29T10:00:00+00:00",
            "data": old_market_dict,
        }
    }
    mock_load_cache.return_value = cached_data

    # Create new mock market with DIFFERENT tradeGoods
    new_trade_goods = [
        MarketTradeGood(
            symbol=TradeSymbol.IRON_ORE,
            type=MarketTradeGoodType.EXPORT,
            tradeVolume=100,
            supply=SupplyLevel.MODERATE,
            purchasePrice=60,  # Different price
            sellPrice=55,  # Different price
        )
    ]

    new_market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    new_market = Market.model_validate(new_market_data)
    new_market.tradeGoods = new_trade_goods

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_market.return_value = new_market

    # Call the function with force_refresh=True
    result = systems.get_market(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )

    # Assertions: API WAS called despite cache hit
    mock_client.systems.get_market.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result matches new API response
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"
    assert result.tradeGoods is not None
    assert len(result.tradeGoods) == 1
    assert result.tradeGoods[0].purchasePrice == 60  # New price

    # Assert: save_cache was called with new data and new timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["market_X1-ABC-1"]
    assert cache_entry["prices_updated"] is not None
    assert cache_entry["data"]["tradeGoods"] is not None
    assert cache_entry["data"]["tradeGoods"][0]["purchasePrice"] == 60


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_market_force_refresh_without_prices_preserves_old_prices(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 4 (CRITICAL): force_refresh=True, no prices from API.

    When API returns without prices, preserves old prices.
    """
    from py_st._generated.models import MarketTradeGood, SupplyLevel
    from py_st._generated.models.MarketTradeGood import (
        Type as MarketTradeGoodType,
    )

    # Setup: populate cache with old market data WITH tradeGoods
    old_trade_goods = [
        MarketTradeGood(
            symbol=TradeSymbol.IRON_ORE,
            type=MarketTradeGoodType.EXPORT,
            tradeVolume=100,
            supply=SupplyLevel.ABUNDANT,
            purchasePrice=50,
            sellPrice=45,
        )
    ]

    old_market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.IRON_ORE],
        imports=[TradeSymbol.FUEL],
        exchange=[TradeSymbol.FOOD],
    )
    old_market_dict = Market.model_validate(old_market_data).model_dump(
        mode="json"
    )
    old_market_dict["tradeGoods"] = [
        tg.model_dump(mode="json") for tg in old_trade_goods
    ]

    old_timestamp = "2025-10-29T10:00:00+00:00"
    cached_data = {
        "market_X1-ABC-1": {
            "prices_updated": old_timestamp,
            "data": old_market_dict,
        }
    }
    mock_load_cache.return_value = cached_data

    # Create new mock market WITHOUT tradeGoods but with UPDATED static fields
    new_market_data = MarketFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        exports=[TradeSymbol.COPPER_ORE],  # Different exports
        imports=[TradeSymbol.AMMUNITION],  # Different imports
        exchange=[TradeSymbol.FOOD],
    )
    new_market = Market.model_validate(new_market_data)
    # tradeGoods is None

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_market.return_value = new_market

    # Call the function with force_refresh=True
    result = systems.get_market(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )

    # Assertions: API WAS called
    mock_client.systems.get_market.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result has OLD tradeGoods (preserved) but NEW static fields
    assert isinstance(result, Market)
    assert result.symbol == "X1-ABC-1"

    # OLD prices preserved
    assert result.tradeGoods is not None
    assert len(result.tradeGoods) == 1
    assert result.tradeGoods[0].symbol == TradeSymbol.IRON_ORE
    assert result.tradeGoods[0].purchasePrice == 50
    assert result.tradeGoods[0].sellPrice == 45

    # NEW static fields updated
    assert len(result.exports) == 1
    assert result.exports[0].symbol == TradeSymbol.COPPER_ORE
    assert len(result.imports) == 1
    assert result.imports[0].symbol == TradeSymbol.AMMUNITION

    # Assert: save_cache was called
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["market_X1-ABC-1"]

    # Verify OLD timestamp preserved
    assert cache_entry["prices_updated"] == old_timestamp

    # Verify saved data has OLD prices
    assert cache_entry["data"]["tradeGoods"] is not None
    assert len(cache_entry["data"]["tradeGoods"]) == 1
    assert cache_entry["data"]["tradeGoods"][0]["symbol"] == "IRON_ORE"
    assert cache_entry["data"]["tradeGoods"][0]["purchasePrice"] == 50

    # Verify saved data has NEW static fields
    assert len(cache_entry["data"]["exports"]) == 1
    assert cache_entry["data"]["exports"][0]["symbol"] == "COPPER_ORE"
    assert len(cache_entry["data"]["imports"]) == 1
    assert cache_entry["data"]["imports"][0]["symbol"] == "AMMUNITION"


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
# Caching Tests for _fetch_and_cache_waypoints
# ============================================================================


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_fetch_and_cache_waypoints_cache_miss(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

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
def test_fetch_and_cache_waypoints_cache_hit(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

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
def test_fetch_and_cache_waypoints_invalid_cache_entry_missing_keys(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

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
def test_fetch_and_cache_waypoints_invalid_cache_entry_bad_data(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

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
def test_fetch_and_cache_waypoints_cache_entry_not_dict(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

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
def test_fetch_and_cache_waypoints_cache_data_not_list(
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
    result = systems._fetch_and_cache_waypoints("fake_token", "X1-ABC")

    # Assertions: API was called due to invalid data type
    mock_client.systems.list_waypoints_all.assert_called_once_with(
        "X1-ABC", traits=None
    )

    # Assert: result matches API response
    assert len(result) == 1
    assert result[0].symbol.root == "X1-ABC-1"

    # Assert: save_cache was called to update cache
    mock_save_cache.assert_called_once()


# ============================================================================
# get_shipyard tests with smart merge caching
# ============================================================================


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard_cache_hit_no_refresh(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 1: Cache hit, no refresh.

    API should NOT be called when cache exists and force_refresh=False.
    """
    from py_st._generated.models import ShipType as ShipTypeEnum

    # Setup: populate cache with shipyard data
    shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[ShipTypeEnum.SHIP_PROBE, ShipTypeEnum.SHIP_MINING_DRONE],
    )

    old_timestamp = "2025-10-29T10:00:00+00:00"
    cached_data = {
        "shipyard_X1-ABC-1": {
            "ships_updated": old_timestamp,
            "data": shipyard_data,
        }
    }
    mock_load_cache.return_value = cached_data

    # Configure mock client (should not be called)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Call the function
    result = systems.get_shipyard("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API was NOT called
    mock_client.systems.get_shipyard.assert_not_called()

    # Assert: result is from cache
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"

    # Assert: save_cache was NOT called
    mock_save_cache.assert_not_called()


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard_cache_miss_with_ships(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 2a: Cache miss, API returns WITH ships.

    API should be called and new data (with ships) should be cached with
    new timestamp.
    """
    from py_st._generated.models import (
        ShipType as ShipTypeEnum,
    )
    from py_st._generated.models import (
        ShipyardShip,
    )

    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock shipyard WITH ships
    shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[ShipTypeEnum.SHIP_PROBE],
    )
    shipyard = Shipyard.model_validate(shipyard_data)

    # Add a ship to the shipyard
    # Create a minimal ShipyardShip for testing
    mock_ship = {
        "type": "SHIP_PROBE",
        "name": "Test Probe",
        "description": "A test probe ship",
        "supply": "ABUNDANT",
        "purchasePrice": 50000,
        "frame": {
            "symbol": "FRAME_PROBE",
            "name": "Frame Probe",
            "description": "Test frame",
            "moduleSlots": 0,
            "mountingPoints": 0,
            "fuelCapacity": 100,
            "requirements": {"power": 1, "crew": 1},
        },
        "reactor": {
            "symbol": "REACTOR_SOLAR_I",
            "name": "Solar Reactor I",
            "description": "Test reactor",
            "condition": 100,
            "powerOutput": 10,
            "requirements": {"crew": 1},
        },
        "engine": {
            "symbol": "ENGINE_IMPULSE_DRIVE_I",
            "name": "Impulse Drive I",
            "description": "Test engine",
            "condition": 100,
            "speed": 10,
            "requirements": {"power": 1, "crew": 1},
        },
        "modules": [],
        "mounts": [],
        "crew": {"required": 1, "capacity": 2},
    }
    shipyard.ships = [ShipyardShip.model_validate(mock_ship)]

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_shipyard.return_value = shipyard

    # Call the function
    result = systems.get_shipyard("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API WAS called
    mock_client.systems.get_shipyard.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result has ships
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"
    assert result.ships is not None
    assert len(result.ships) == 1
    assert result.ships[0].name == "Test Probe"

    # Assert: save_cache was called with new timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["shipyard_X1-ABC-1"]

    # Verify new timestamp exists
    assert cache_entry["ships_updated"] is not None

    # Verify saved data has ships
    assert cache_entry["data"]["ships"] is not None
    assert len(cache_entry["data"]["ships"]) == 1


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard_cache_miss_without_ships(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 2b: Cache miss, API returns WITHOUT ships.

    API should be called and new data (without ships) should be cached
    with None timestamp.
    """
    from py_st._generated.models import ShipType as ShipTypeEnum

    # Setup: empty cache (cache miss)
    mock_load_cache.return_value = {}

    # Create mock shipyard WITHOUT ships
    shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[ShipTypeEnum.SHIP_PROBE],
    )
    shipyard = Shipyard.model_validate(shipyard_data)
    # ships is None by default from factory

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_shipyard.return_value = shipyard

    # Call the function
    result = systems.get_shipyard("fake_token", "X1-ABC", "X1-ABC-1")

    # Assertions: API WAS called
    mock_client.systems.get_shipyard.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result has no ships
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"
    assert result.ships is None

    # Assert: save_cache was called with None timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["shipyard_X1-ABC-1"]

    # Verify timestamp is None
    assert cache_entry["ships_updated"] is None

    # Verify saved data has no ships
    assert cache_entry["data"]["ships"] is None


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard_force_refresh_with_ships(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 3: Cache hit, force_refresh=True, API returns WITH ships.

    API should be called and new data (with ships) should be cached with
    new timestamp.
    """
    from py_st._generated.models import (
        ShipType as ShipTypeEnum,
    )
    from py_st._generated.models import (
        ShipyardShip,
    )

    # Setup: populate cache with old shipyard data
    old_shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[ShipTypeEnum.SHIP_PROBE],
    )

    old_timestamp = "2025-10-29T10:00:00+00:00"
    cached_data = {
        "shipyard_X1-ABC-1": {
            "ships_updated": old_timestamp,
            "data": old_shipyard_data,
        }
    }
    mock_load_cache.return_value = cached_data

    # Create new mock shipyard WITH ships
    new_shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[
            ShipTypeEnum.SHIP_PROBE,
            ShipTypeEnum.SHIP_MINING_DRONE,
        ],  # Different ship types
    )
    new_shipyard = Shipyard.model_validate(new_shipyard_data)

    # Add a new ship
    mock_ship = {
        "type": "SHIP_MINING_DRONE",
        "name": "New Mining Drone",
        "description": "A new mining drone",
        "supply": "ABUNDANT",
        "purchasePrice": 75000,
        "frame": {
            "symbol": "FRAME_DRONE",
            "name": "Frame Drone",
            "description": "Test frame",
            "moduleSlots": 1,
            "mountingPoints": 1,
            "fuelCapacity": 50,
            "requirements": {"power": 1, "crew": 0},
        },
        "reactor": {
            "symbol": "REACTOR_SOLAR_I",
            "name": "Solar Reactor I",
            "description": "Test reactor",
            "condition": 100,
            "powerOutput": 10,
            "requirements": {"crew": 0},
        },
        "engine": {
            "symbol": "ENGINE_IMPULSE_DRIVE_I",
            "name": "Impulse Drive I",
            "description": "Test engine",
            "condition": 100,
            "speed": 10,
            "requirements": {"power": 1, "crew": 0},
        },
        "modules": [],
        "mounts": [],
        "crew": {"required": 0, "capacity": 0},
    }
    new_shipyard.ships = [ShipyardShip.model_validate(mock_ship)]

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_shipyard.return_value = new_shipyard

    # Call the function with force_refresh=True
    result = systems.get_shipyard(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )

    # Assertions: API WAS called
    mock_client.systems.get_shipyard.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result has new ships
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"
    assert result.ships is not None
    assert len(result.ships) == 1
    assert result.ships[0].name == "New Mining Drone"

    # Assert: shipTypes updated
    assert len(result.shipTypes) == 2

    # Assert: save_cache was called with new timestamp
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["shipyard_X1-ABC-1"]

    # Verify new timestamp exists (different from old)
    assert cache_entry["ships_updated"] is not None
    assert cache_entry["ships_updated"] != old_timestamp

    # Verify saved data has new ships
    assert cache_entry["data"]["ships"] is not None
    assert len(cache_entry["data"]["ships"]) == 1
    assert cache_entry["data"]["ships"][0]["name"] == "New Mining Drone"


@patch("py_st.services.systems.save_cache")
@patch("py_st.services.systems.load_cache")
@patch("py_st.services.systems.SpaceTradersClient")
def test_get_shipyard_force_refresh_without_ships_preserves_old_ships(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """
    Test Case 4 (CRITICAL): force_refresh=True, no ships from API.

    When API returns without ships, preserves old ships and timestamp,
    but updates static fields (shipTypes).
    """
    from py_st._generated.models import (
        ShipType as ShipTypeEnum,
    )

    # Setup: populate cache with old shipyard data WITH ships
    old_shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[ShipTypeEnum.SHIP_PROBE],
        modifications_fee=1000,
    )
    old_shipyard_dict = Shipyard.model_validate(old_shipyard_data).model_dump(
        mode="json"
    )

    # Add old ships to cache
    old_ship = {
        "type": "SHIP_PROBE",
        "name": "Old Probe",
        "description": "An old probe ship",
        "supply": "ABUNDANT",
        "purchasePrice": 50000,
        "frame": {
            "symbol": "FRAME_PROBE",
            "name": "Frame Probe",
            "description": "Test frame",
            "moduleSlots": 0,
            "mountingPoints": 0,
            "fuelCapacity": 100,
            "requirements": {"power": 1, "crew": 1},
        },
        "reactor": {
            "symbol": "REACTOR_SOLAR_I",
            "name": "Solar Reactor I",
            "description": "Test reactor",
            "condition": 100,
            "powerOutput": 10,
            "requirements": {"crew": 1},
        },
        "engine": {
            "symbol": "ENGINE_IMPULSE_DRIVE_I",
            "name": "Impulse Drive I",
            "description": "Test engine",
            "condition": 100,
            "speed": 10,
            "requirements": {"power": 1, "crew": 1},
        },
        "modules": [],
        "mounts": [],
        "crew": {"required": 1, "capacity": 2},
    }
    old_shipyard_dict["ships"] = [old_ship]

    old_timestamp = "2025-10-29T10:00:00+00:00"
    cached_data = {
        "shipyard_X1-ABC-1": {
            "ships_updated": old_timestamp,
            "data": old_shipyard_dict,
        }
    }
    mock_load_cache.return_value = cached_data

    # Create new mock shipyard WITHOUT ships but with UPDATED static fields
    new_shipyard_data = ShipyardFactory.build_minimal(
        waypoint_symbol="X1-ABC-1",
        ship_types=[
            ShipTypeEnum.SHIP_PROBE,
            ShipTypeEnum.SHIP_MINING_DRONE,
            ShipTypeEnum.SHIP_LIGHT_HAULER,
        ],  # Different ship types
        modifications_fee=1500,  # Different fee
    )
    new_shipyard = Shipyard.model_validate(new_shipyard_data)
    # ships is None

    # Configure mock client
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.systems.get_shipyard.return_value = new_shipyard

    # Call the function with force_refresh=True
    result = systems.get_shipyard(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )

    # Assertions: API WAS called
    mock_client.systems.get_shipyard.assert_called_once_with(
        "X1-ABC", "X1-ABC-1"
    )

    # Assert: result has OLD ships (preserved)
    assert isinstance(result, Shipyard)
    assert result.symbol == "X1-ABC-1"
    assert result.ships is not None
    assert len(result.ships) == 1
    assert result.ships[0].name == "Old Probe"
    assert result.ships[0].purchasePrice == 50000

    # Assert: NEW static fields updated (shipTypes)
    assert len(result.shipTypes) == 3
    ship_type_values = [st.type.value for st in result.shipTypes]
    assert "SHIP_PROBE" in ship_type_values
    assert "SHIP_MINING_DRONE" in ship_type_values
    assert "SHIP_LIGHT_HAULER" in ship_type_values

    # Assert: OLD dynamic fields preserved (modificationsFee)
    assert result.modificationsFee == 1000  # Original value, not new 1500

    # Assert: save_cache was called
    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    cache_entry = saved_cache["shipyard_X1-ABC-1"]

    # Verify OLD timestamp preserved
    assert cache_entry["ships_updated"] == old_timestamp

    # Verify saved data has OLD ships
    assert cache_entry["data"]["ships"] is not None
    assert len(cache_entry["data"]["ships"]) == 1
    assert cache_entry["data"]["ships"][0]["name"] == "Old Probe"
    assert cache_entry["data"]["ships"][0]["purchasePrice"] == 50000

    # Verify saved data has NEW static fields (shipTypes)
    assert len(cache_entry["data"]["shipTypes"]) == 3
    saved_ship_types = [st["type"] for st in cache_entry["data"]["shipTypes"]]
    assert "SHIP_PROBE" in saved_ship_types
    assert "SHIP_MINING_DRONE" in saved_ship_types
    assert "SHIP_LIGHT_HAULER" in saved_ship_types

    # Verify saved data has OLD dynamic fields (modificationsFee)
    assert cache_entry["data"]["modificationsFee"] == 1000
