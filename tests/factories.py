from datetime import UTC, datetime, timedelta
from typing import Any

from py_st._generated.models import (
    Agent,
    Contract,
    ContractPayment,
    ContractTerms,
    Cooldown,
    Ship,
    ShipCargo,
    ShipComponentCondition,
    ShipComponentIntegrity,
    ShipComponentQuality,
    ShipCrew,
    ShipEngine,
    ShipFrame,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    ShipNavRoute,
    ShipNavRouteWaypoint,
    ShipNavStatus,
    ShipReactor,
    ShipRegistration,
    ShipRequirements,
    ShipRole,
    SystemSymbol,
    Waypoint,
    WaypointSymbol,
    WaypointType,
)
from py_st._generated.models.Contract import Type as ContractType
from py_st._generated.models.ShipCrew import Rotation
from py_st._generated.models.ShipEngine import Symbol as EngineSymbol
from py_st._generated.models.ShipFrame import Symbol as FrameSymbol
from py_st._generated.models.ShipReactor import Symbol as ReactorSymbol


class AgentFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Agent payload dict."""
        agent = Agent(
            accountId=None,
            symbol="FOO",
            headquarters="X1-ABC-1",
            credits=42,
            startingFaction="COSMIC",
            shipCount=1,
        )
        return agent.model_dump(mode="json")  # type: ignore[return-value]


class ContractFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Contract payload dict."""
        payment = ContractPayment(
            onAccepted=1000,
            onFulfilled=5000,
        )
        terms = ContractTerms(
            deadline=datetime.now(UTC) + timedelta(days=30),
            payment=payment,
            deliver=[],
        )
        contract = Contract(
            id="contract-1",
            factionSymbol="COSMIC",
            type=ContractType.PROCUREMENT,
            terms=terms,
            accepted=False,
            fulfilled=False,
            expiration=datetime.now(UTC) + timedelta(days=30),
            deadlineToAccept=None,
        )
        return contract.model_dump(mode="json")  # type: ignore[return-value]


class ShipFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Ship payload dict."""
        # Build nested models
        registration = ShipRegistration(
            name="Test Ship",
            factionSymbol="COSMIC",
            role=ShipRole.COMMAND,
        )

        # Build route waypoints
        destination_waypoint = ShipNavRouteWaypoint(
            symbol="X1-ABC-2",
            type=WaypointType.PLANET,
            systemSymbol=SystemSymbol("X1-ABC"),
            x=1,
            y=1,
        )
        origin_waypoint = ShipNavRouteWaypoint(
            symbol="X1-ABC-1",
            type=WaypointType.PLANET,
            systemSymbol=SystemSymbol("X1-ABC"),
            x=0,
            y=0,
        )

        # Build route
        route = ShipNavRoute(
            destination=destination_waypoint,
            origin=origin_waypoint,
            departureTime=datetime.now(UTC),
            arrival=datetime.now(UTC) + timedelta(hours=1),
        )

        # Build nav
        nav = ShipNav(
            systemSymbol=SystemSymbol("X1-ABC"),
            waypointSymbol=WaypointSymbol("X1-ABC-1"),
            route=route,
            status=ShipNavStatus.IN_TRANSIT,
            flightMode=ShipNavFlightMode.CRUISE,
        )

        # Build crew
        crew = ShipCrew(
            current=1,
            required=1,
            capacity=5,
            rotation=Rotation.STRICT,
            morale=100,
            wages=0,
        )

        # Build requirements
        frame_requirements = ShipRequirements(power=1, crew=1, slots=None)
        reactor_requirements = ShipRequirements(power=None, crew=1, slots=None)
        engine_requirements = ShipRequirements(power=2, crew=1, slots=None)

        # Build frame
        frame = ShipFrame(
            symbol=FrameSymbol.FRAME_FRIGATE,
            name="Frigate",
            description="A sturdy frigate.",
            condition=ShipComponentCondition(1.0),
            integrity=ShipComponentIntegrity(1.0),
            quality=ShipComponentQuality(1.0),
            moduleSlots=5,
            mountingPoints=5,
            fuelCapacity=100,
            requirements=frame_requirements,
        )

        # Build reactor
        reactor = ShipReactor(
            symbol=ReactorSymbol.REACTOR_FISSION_I,
            name="Fission Reactor I",
            description="A basic fission reactor.",
            condition=ShipComponentCondition(1.0),
            integrity=ShipComponentIntegrity(1.0),
            quality=ShipComponentQuality(1.0),
            powerOutput=10,
            requirements=reactor_requirements,
        )

        # Build engine
        engine = ShipEngine(
            symbol=EngineSymbol.ENGINE_ION_DRIVE_I,
            name="Ion Drive I",
            description="A basic ion drive.",
            condition=ShipComponentCondition(1.0),
            integrity=ShipComponentIntegrity(1.0),
            quality=ShipComponentQuality(1.0),
            speed=10,
            requirements=engine_requirements,
        )

        # Build cooldown
        cooldown = Cooldown(
            shipSymbol="SHIP-1",
            totalSeconds=0,
            remainingSeconds=0,
            expiration=datetime.now(UTC),
        )

        # Build cargo
        cargo = ShipCargo(
            capacity=100,
            units=0,
            inventory=[],
        )

        # Build fuel
        fuel = ShipFuel(
            current=100,
            capacity=100,
            consumed=None,
        )

        # Build main ship
        ship = Ship(
            symbol="SHIP-1",
            registration=registration,
            nav=nav,
            crew=crew,
            frame=frame,
            reactor=reactor,
            engine=engine,
            cooldown=cooldown,
            modules=[],
            mounts=[],
            cargo=cargo,
            fuel=fuel,
        )
        return ship.model_dump(mode="json")  # type: ignore[return-value]


class WaypointFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Waypoint payload dict."""
        waypoint = Waypoint(
            symbol=WaypointSymbol("X1-ABC-1"),
            type=WaypointType.PLANET,
            systemSymbol=SystemSymbol("X1-ABC"),
            x=0,
            y=0,
            orbitals=[],
            orbits=None,
            traits=[],
            modifiers=None,
            isUnderConstruction=False,
        )
        return waypoint.model_dump(mode="json")  # type: ignore[return-value]


class CacheFactory:
    @staticmethod
    def build_valid_cache_data() -> dict[str, Any]:
        """Build valid cache data with ISO 8601 timestamp strings."""
        agent_data = AgentFactory.build_minimal()
        ship_data = ShipFactory.build_minimal()

        return {
            "agent": {
                "last_updated": "2025-10-26T18:00:00Z",
                "data": {
                    "symbol": agent_data["symbol"],
                    "credits": agent_data["credits"],
                },
            },
            "ships": {
                "SHIP-A": {
                    "last_updated": "2025-10-26T17:55:00Z",
                    "data": {
                        "symbol": ship_data["symbol"],
                        "fuel": ship_data["fuel"]["current"],
                    },
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
            "timestamp": datetime(2025, 10, 26, 18, 10, 0, tzinfo=UTC),
            "value": "some data",
        }
