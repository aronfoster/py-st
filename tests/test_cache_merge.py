"""Tests for smart cache merge logic."""

from typing import cast

from py_st._generated.models import Market, Shipyard
from py_st.services.cache_merge import smart_merge_cache


def test_fresh_model_has_keep_field_uses_fresh_data() -> None:
    """Test that fresh data is used when keep_field is populated."""
    # Arrange
    cached_entry = {
        "prices_updated": "2025-01-01T00:00:00Z",
        "data": {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "IRON", "name": "", "description": ""}],
            "imports": [{"symbol": "FOOD", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": [
                {
                    "symbol": "IRON",
                    "type": "EXPORT",
                    "tradeVolume": 10,
                    "supply": "MODERATE",
                    "purchasePrice": 100,
                    "sellPrice": 90,
                }
            ],
        },
    }

    fresh_market = Market.model_validate(
        {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "COPPER", "name": "", "description": ""}],
            "imports": [{"symbol": "FUEL", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": [
                {
                    "symbol": "COPPER",
                    "type": "EXPORT",
                    "tradeVolume": 20,
                    "supply": "HIGH",
                    "purchasePrice": 200,
                    "sellPrice": 180,
                }
            ],
        }
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
    cached_entry = {
        "prices_updated": old_timestamp,
        "data": {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "IRON", "name": "", "description": ""}],
            "imports": [{"symbol": "FOOD", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": [
                {
                    "symbol": "IRON",
                    "type": "EXPORT",
                    "tradeVolume": 10,
                    "supply": "MODERATE",
                    "purchasePrice": 100,
                    "sellPrice": 90,
                }
            ],
        },
    }

    fresh_market = Market.model_validate(
        {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "COPPER", "name": "", "description": ""}],
            "imports": [{"symbol": "FUEL", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": None,
        }
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
        result_market.tradeGoods[0].symbol.value == "IRON"
    ), "Should preserve cached trade good"
    assert (
        result_timestamp == old_timestamp
    ), "Should preserve old timestamp when keeping cached field"


def test_merge_updates_other_fields_when_preserving() -> None:
    """Test that non-preserved fields are updated from fresh model."""
    # Arrange
    old_timestamp = "2025-01-01T00:00:00Z"
    cached_entry = {
        "prices_updated": old_timestamp,
        "data": {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "IRON", "name": "", "description": ""}],
            "imports": [{"symbol": "FOOD", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": [
                {
                    "symbol": "IRON",
                    "type": "EXPORT",
                    "tradeVolume": 10,
                    "supply": "MODERATE",
                    "purchasePrice": 100,
                    "sellPrice": 90,
                }
            ],
        },
    }

    fresh_market = Market.model_validate(
        {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "COPPER", "name": "", "description": ""}],
            "imports": [{"symbol": "FUEL", "name": "", "description": ""}],
            "exchange": [
                {"symbol": "ELECTRONICS", "name": "", "description": ""}
            ],
            "transactions": None,
            "tradeGoods": None,
        }
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
        and result_market.tradeGoods[0].symbol.value == "IRON"
    ), "Should still preserve cached tradeGoods"


def test_no_cache_uses_fresh_data() -> None:
    """Test that fresh data is used when there's no cache entry."""
    # Arrange
    fresh_market = Market.model_validate(
        {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "COPPER", "name": "", "description": ""}],
            "imports": [{"symbol": "FUEL", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": None,
        }
    )

    # Act
    result_market, result_timestamp = smart_merge_cache(
        Market,
        None,
        fresh_market,
        "tradeGoods",
        "prices_updated",
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
        "data": {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "IRON", "name": "", "description": ""}],
            "imports": [{"symbol": "FOOD", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": None,
        },
    }

    fresh_market = Market.model_validate(
        {
            "symbol": "X1-TEST-MARKET",
            "exports": [{"symbol": "COPPER", "name": "", "description": ""}],
            "imports": [{"symbol": "FUEL", "name": "", "description": ""}],
            "exchange": [],
            "transactions": None,
            "tradeGoods": None,
        }
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
    cached_entry = {
        "ships_updated": old_timestamp,
        "data": {
            "symbol": "X1-TEST-SHIPYARD",
            "shipTypes": [{"type": "SHIP_MINING_DRONE"}],
            "transactions": None,
            "ships": [
                {
                    "type": "SHIP_MINING_DRONE",
                    "name": "Mining Drone",
                    "description": "A mining drone",
                    "supply": "MODERATE",
                    "purchasePrice": 50000,
                    "frame": {
                        "symbol": "FRAME_DRONE",
                        "name": "Frame",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "moduleSlots": 1,
                        "mountingPoints": 1,
                        "fuelCapacity": 100,
                        "requirements": {"power": 1, "crew": 0},
                    },
                    "reactor": {
                        "symbol": "REACTOR_SOLAR_I",
                        "name": "Reactor",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "powerOutput": 3,
                        "requirements": {"crew": 0},
                    },
                    "engine": {
                        "symbol": "ENGINE_IMPULSE_DRIVE_I",
                        "name": "Engine",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "speed": 2,
                        "requirements": {"power": 1, "crew": 0},
                    },
                    "modules": [],
                    "mounts": [],
                    "crew": {"required": 0, "capacity": 0},
                }
            ],
            "modificationsFee": 1000,
        },
    }

    fresh_shipyard = Shipyard.model_validate(
        {
            "symbol": "X1-TEST-SHIPYARD",
            "shipTypes": [
                {"type": "SHIP_MINING_DRONE"},
                {"type": "SHIP_LIGHT_HAULER"},
            ],
            "transactions": None,
            "ships": None,
            "modificationsFee": 1500,
        }
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
        "data": {
            "symbol": "X1-TEST-SHIPYARD",
            "shipTypes": [{"type": "SHIP_MINING_DRONE"}],
            "transactions": None,
            "ships": None,
            "modificationsFee": 1000,
        },
    }

    fresh_shipyard = Shipyard.model_validate(
        {
            "symbol": "X1-TEST-SHIPYARD",
            "shipTypes": [{"type": "SHIP_LIGHT_HAULER"}],
            "transactions": None,
            "ships": [
                {
                    "type": "SHIP_LIGHT_HAULER",
                    "name": "Light Hauler",
                    "description": "A hauler",
                    "supply": "HIGH",
                    "purchasePrice": 75000,
                    "frame": {
                        "symbol": "FRAME_LIGHT_FREIGHTER",
                        "name": "Frame",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "moduleSlots": 3,
                        "mountingPoints": 2,
                        "fuelCapacity": 400,
                        "requirements": {"power": 3, "crew": 1},
                    },
                    "reactor": {
                        "symbol": "REACTOR_FISSION_I",
                        "name": "Reactor",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "powerOutput": 10,
                        "requirements": {"crew": 1},
                    },
                    "engine": {
                        "symbol": "ENGINE_ION_DRIVE_I",
                        "name": "Engine",
                        "description": "",
                        "condition": 1.0,
                        "integrity": 1.0,
                        "quality": 1,
                        "speed": 10,
                        "requirements": {"power": 3, "crew": 1},
                    },
                    "modules": [],
                    "mounts": [],
                    "crew": {"required": 1, "capacity": 3},
                }
            ],
            "modificationsFee": 1500,
        }
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
