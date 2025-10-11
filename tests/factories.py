from __future__ import annotations


class AgentFactory:
    @staticmethod
    def build_minimal() -> dict:
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
    def build_minimal() -> dict:
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
    def build_minimal() -> dict:
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
    def build_minimal() -> dict:
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
