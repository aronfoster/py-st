from datetime import datetime, timezone
from typing import Any


class AgentFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Agent payload dict."""
        return {
            "symbol": "FOO",
            "headquarters": "X1-ABC-1",
            "credits": 42,
            "startingFaction": "COSMIC",
            "shipCount": 1,
        }


class ContractFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Contract payload dict."""
        return {
            "id": "contract-1",
            "factionSymbol": "COSMIC",
            "type": "PROCUREMENT",
            "terms": {
                "deadline": "2023-12-31T23:59:59Z",
                "payment": {"onAccepted": 1000, "onFulfilled": 5000},
                "deliver": [],
            },
            "accepted": False,
            "fulfilled": False,
            "expiration": "2023-12-31T23:59:59Z",
        }


class ShipFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Ship payload dict."""
        return {
            "symbol": "SHIP-1",
            "registration": {
                "name": "Test Ship",
                "factionSymbol": "COSMIC",
                "role": "COMMAND",
            },
            "nav": {
                "systemSymbol": "X1-ABC",
                "waypointSymbol": "X1-ABC-1",
                "route": {
                    "departure": {
                        "symbol": "X1-ABC-1",
                        "type": "PLANET",
                        "systemSymbol": "X1-ABC",
                        "x": 0,
                        "y": 0,
                    },
                    "destination": {
                        "symbol": "X1-ABC-2",
                        "type": "PLANET",
                        "systemSymbol": "X1-ABC",
                        "x": 1,
                        "y": 1,
                    },
                    "origin": {
                        "symbol": "X1-ABC-1",
                        "type": "PLANET",
                        "systemSymbol": "X1-ABC",
                        "x": 0,
                        "y": 0,
                    },
                    "departureTime": "2023-01-01T00:00:00Z",
                    "arrival": "2023-01-01T01:00:00Z",
                },
                "status": "IN_TRANSIT",
                "flightMode": "CRUISE",
            },
            "crew": {
                "current": 1,
                "required": 1,
                "capacity": 5,
                "rotation": "STRICT",
                "morale": 100,
                "wages": 0,
            },
            "frame": {
                "symbol": "FRAME_FRIGATE",
                "name": "Frigate",
                "description": "A sturdy frigate.",
                "condition": 1.0,
                "integrity": 1.0,
                "quality": 1.0,
                "moduleSlots": 5,
                "mountingPoints": 5,
                "fuelCapacity": 100,
                "requirements": {"power": 1, "crew": 1},
            },
            "reactor": {
                "symbol": "REACTOR_FISSION_I",
                "name": "Fission Reactor I",
                "description": "A basic fission reactor.",
                "condition": 1.0,
                "integrity": 1.0,
                "quality": 1.0,
                "powerOutput": 10,
                "requirements": {"crew": 1},
            },
            "engine": {
                "symbol": "ENGINE_ION_DRIVE_I",
                "name": "Ion Drive I",
                "description": "A basic ion drive.",
                "condition": 1.0,
                "integrity": 1.0,
                "quality": 1.0,
                "speed": 10,
                "requirements": {"power": 2, "crew": 1},
            },
            "cooldown": {
                "shipSymbol": "SHIP-1",
                "totalSeconds": 0,
                "remainingSeconds": 0,
                "expiration": "2023-01-01T00:00:00Z",
            },
            "modules": [],
            "mounts": [],
            "cargo": {
                "capacity": 100,
                "units": 0,
                "inventory": [],
            },
            "fuel": {
                "current": 100,
                "capacity": 100,
            },
        }


class WaypointFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Waypoint payload dict."""
        return {
            "symbol": "X1-ABC-1",
            "type": "PLANET",
            "systemSymbol": "X1-ABC",
            "x": 0,
            "y": 0,
            "orbitals": [],
            "traits": [],
            "isUnderConstruction": False,
        }


class CacheFactory:
    @staticmethod
    def build_valid_cache_data() -> dict[str, Any]:
        """Build valid cache data with ISO 8601 timestamp strings."""
        return {
            "agent": {
                "last_updated": "2025-10-26T18:00:00Z",
                "data": {"symbol": "AGENT-1", "credits": 1000},
            },
            "ships": {
                "SHIP-A": {
                    "last_updated": "2025-10-26T17:55:00Z",
                    "data": {"symbol": "SHIP-A", "fuel": 100},
                }
            },
        }

    @staticmethod
    def build_invalid_json_string() -> str:
        """Return a string that is not valid JSON."""
        return '{"key": "value", missing_quote}'

    @staticmethod
    def build_data_with_datetime() -> dict[str, Any]:
        """Return a dictionary containing a datetime object."""
        return {
            "timestamp": datetime(
                2025, 10, 26, 18, 10, 0, tzinfo=timezone.utc
            ),
            "value": "some data",
        }
