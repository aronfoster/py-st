"""Tests for smart cache merge logic."""

from typing import cast

from py_st._generated.models import Market, Shipyard, TradeSymbol
from py_st._generated.models.ShipType import ShipType as ShipTypeEnum
from py_st.services.cache_merge import smart_merge_cache
from tests.factories import (
    MarketFactory,
    MarketTradeGoodFactory,
    ShipyardFactory,
    ShipyardShipFactory,
)


def test_fresh_model_has_keep_field_uses_fresh_data() -> None:
    """Test that fresh data is used when keep_field is populated."""
    # Arrange
    old_trade_good = MarketTradeGoodFactory.build_minimal(
        symbol=TradeSymbol.IRON_ORE, purchase_price=100, sell_price=90
    )
    cached_entry = {
        "prices_updated": "2025-01-01T00:00:00Z",
        "data": MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FOOD],
            trade_goods=[old_trade_good],
        ),
    }

    new_trade_good = MarketTradeGoodFactory.build_minimal(
        symbol=TradeSymbol.COPPER, purchase_price=200, sell_price=180
    )
    fresh_market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.COPPER],
            imports=[TradeSymbol.FUEL],
            trade_goods=[new_trade_good],
        )
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        cast(dict[str, object], cached_entry),
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Assert
    assert (
        result_market.tradeGoods == fresh_market.tradeGoods
    ), "Should use fresh tradeGoods when available"
    assert (
        result_market.exports == fresh_market.exports
    ), "Should use fresh exports when fresh tradeGoods available"
    assert result_timestamp is not None, "Should set new timestamp"
    assert (
        result_timestamp != cached_entry["prices_updated"]
    ), "Timestamp should be updated"


def test_preserve_keep_field_when_fresh_lacks_it() -> None:
    """Test that keep_field is preserved when fresh model lacks it."""
    # Arrange
    old_timestamp = "2025-01-01T00:00:00Z"
    old_trade_good = MarketTradeGoodFactory.build_minimal(
        symbol=TradeSymbol.IRON_ORE, purchase_price=100, sell_price=90
    )
    cached_entry = {
        "prices_updated": old_timestamp,
        "data": MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FOOD],
            trade_goods=[old_trade_good],
        ),
    }

    fresh_market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.COPPER],
            imports=[TradeSymbol.FUEL],
            trade_goods=None,
        )
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        cast(dict[str, object], cached_entry),
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Assert
    assert (
        result_market.tradeGoods is not None
    ), "Should preserve tradeGoods from cache"
    assert len(result_market.tradeGoods) == 1, "Should keep cached prices"
    assert (
        result_market.tradeGoods[0].symbol.value == "IRON_ORE"
    ), "Should preserve cached trade good"
    assert (
        result_timestamp == old_timestamp
    ), "Should preserve old timestamp when keeping cached field"


def test_merge_updates_other_fields_when_preserving() -> None:
    """Test that non-preserved fields are updated from fresh model."""
    # Arrange
    old_timestamp = "2025-01-01T00:00:00Z"
    old_trade_good = MarketTradeGoodFactory.build_minimal(
        symbol=TradeSymbol.IRON_ORE, purchase_price=100, sell_price=90
    )
    cached_entry = {
        "prices_updated": old_timestamp,
        "data": MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FOOD],
            exchange=[],
            trade_goods=[old_trade_good],
        ),
    }

    fresh_market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.COPPER],
            imports=[TradeSymbol.FUEL],
            exchange=[TradeSymbol.ELECTRONICS],
            trade_goods=None,
        )
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        cast(dict[str, object], cached_entry),
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Assert
    assert (
        result_market.exports[0].symbol.value == "COPPER"
    ), "Should update exports from fresh data"
    assert (
        result_market.imports[0].symbol.value == "FUEL"
    ), "Should update imports from fresh data"
    assert (
        len(result_market.exchange) == 1
    ), "Should update exchange from fresh data"
    assert (
        result_market.exchange[0].symbol.value == "ELECTRONICS"
    ), "Should have fresh exchange data"
    assert (
        result_market.tradeGoods is not None
        and result_market.tradeGoods[0].symbol.value == "IRON_ORE"
    ), "Should still preserve cached tradeGoods"


def test_no_cache_uses_fresh_data() -> None:
    """Test that fresh data is used when there's no cache entry."""
    # Arrange
    fresh_market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.COPPER],
            imports=[TradeSymbol.FUEL],
            trade_goods=None,
        )
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        None,
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Assert
    assert (
        result_market == fresh_market
    ), "Should return fresh market when no cache"
    assert (
        result_timestamp is None
    ), "Should have no timestamp when keep_field is None"


def test_cache_lacks_keep_field_uses_fresh() -> None:
    """Test that fresh data is used when cache also lacks keep_field."""
    # Arrange
    cached_entry = {
        "prices_updated": None,
        "data": MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.IRON_ORE],
            imports=[TradeSymbol.FOOD],
            trade_goods=None,
        ),
    }

    fresh_market = Market.model_validate(
        MarketFactory.build_minimal(
            waypoint_symbol="X1-TEST-MARKET",
            exports=[TradeSymbol.COPPER],
            imports=[TradeSymbol.FUEL],
            trade_goods=None,
        )
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        cast(dict[str, object], cached_entry),
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Assert
    assert (
        result_market.tradeGoods is None
    ), "Should have None tradeGoods when both lack it"
    assert (
        result_market.exports[0].symbol.value == "COPPER"
    ), "Should use fresh exports"
    assert result_timestamp is None, "Should have no timestamp"


def test_shipyard_preserves_ships_field() -> None:
    """Test smart merge with Shipyard model preserving ships."""
    # Arrange
    old_timestamp = "2025-01-01T00:00:00Z"
    old_ship = ShipyardShipFactory.build_minimal(
        ship_type=ShipTypeEnum.SHIP_MINING_DRONE,
        name="Mining Drone",
        purchase_price=50000,
    )
    cached_entry = {
        "ships_updated": old_timestamp,
        "data": ShipyardFactory.build_minimal(
            waypoint_symbol="X1-TEST-SHIPYARD",
            ship_types=[ShipTypeEnum.SHIP_MINING_DRONE],
            modifications_fee=1000,
            ships=[old_ship],
        ),
    }

    fresh_shipyard = Shipyard.model_validate(
        ShipyardFactory.build_minimal(
            waypoint_symbol="X1-TEST-SHIPYARD",
            ship_types=[
                ShipTypeEnum.SHIP_MINING_DRONE,
                ShipTypeEnum.SHIP_LIGHT_HAULER,
            ],
            modifications_fee=1500,
            ships=None,
        )
    )

    # Act
    result_shipyard, result_timestamp = smart_merge_cache(
        Shipyard,
        cast(dict[str, object], cached_entry),
        fresh_shipyard,
        "ships",
        "ships_updated",
        ["shipTypes"],
    )

    # Assert
    assert (
        result_shipyard.ships is not None
    ), "Should preserve ships from cache"
    assert len(result_shipyard.ships) == 1, "Should keep cached ship"
    assert (
        result_shipyard.ships[0].type.value == "SHIP_MINING_DRONE"
    ), "Should preserve cached ship data"
    assert len(result_shipyard.shipTypes) == 2, "Should update shipTypes"
    assert (
        result_shipyard.modificationsFee == 1000
    ), "Should preserve modificationsFee from cache"
    assert result_timestamp == old_timestamp, "Should preserve old timestamp"


def test_shipyard_uses_fresh_when_ships_populated() -> None:
    """Test that fresh shipyard is used when ships are available."""
    # Arrange
    cached_entry = {
        "ships_updated": "2025-01-01T00:00:00Z",
        "data": ShipyardFactory.build_minimal(
            waypoint_symbol="X1-TEST-SHIPYARD",
            ship_types=[ShipTypeEnum.SHIP_MINING_DRONE],
            modifications_fee=1000,
            ships=None,
        ),
    }

    new_ship = ShipyardShipFactory.build_minimal(
        ship_type=ShipTypeEnum.SHIP_LIGHT_HAULER,
        name="Light Hauler",
        purchase_price=75000,
    )
    fresh_shipyard = Shipyard.model_validate(
        ShipyardFactory.build_minimal(
            waypoint_symbol="X1-TEST-SHIPYARD",
            ship_types=[ShipTypeEnum.SHIP_LIGHT_HAULER],
            modifications_fee=1500,
            ships=[new_ship],
        )
    )

    # Act
    result_shipyard, result_timestamp = smart_merge_cache(
        Shipyard,
        cast(dict[str, object], cached_entry),
        fresh_shipyard,
        "ships",
        "ships_updated",
        ["shipTypes"],
    )

    # Assert
    assert (
        result_shipyard.ships is not None
    ), "Should use fresh ships when available"
    assert len(result_shipyard.ships) == 1, "Should have fresh ship"
    assert (
        result_shipyard.ships[0].type.value == "SHIP_LIGHT_HAULER"
    ), "Should use fresh ship data"
    assert result_timestamp is not None, "Should set new timestamp"
    assert (
        result_timestamp != cached_entry["ships_updated"]
    ), "Should update timestamp"
