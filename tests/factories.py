from datetime import UTC, datetime, timedelta
from typing import Any

from py_st._generated.models import (
    Agent,
    Contract,
    ContractPayment,
    ContractTerms,
    Cooldown,
    ExtractionYield,
    Market,
    MarketTransaction,
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
    Shipyard,
    ShipyardTransaction,
    Survey,
    SurveyDeposit,
    SystemSymbol,
    TradeGood,
    TradeSymbol,
    Waypoint,
    WaypointSymbol,
    WaypointTrait,
    WaypointTraitSymbol,
    WaypointType,
)
from py_st._generated.models.Contract import Type as ContractType
from py_st._generated.models.MarketTradeGood import MarketTradeGood
from py_st._generated.models.MarketTradeGood import (
    Type as MarketTradeGoodType,
)
from py_st._generated.models.MarketTransaction import Type as TransactionType
from py_st._generated.models.ShipCrew import Rotation
from py_st._generated.models.ShipEngine import Symbol as EngineSymbol
from py_st._generated.models.ShipFrame import Symbol as FrameSymbol
from py_st._generated.models.ShipReactor import Symbol as ReactorSymbol
from py_st._generated.models.ShipType import ShipType as ShipTypeEnum
from py_st._generated.models.Shipyard import ShipType
from py_st._generated.models.ShipyardShip import Crew, ShipyardShip
from py_st._generated.models.SupplyLevel import SupplyLevel
from py_st._generated.models.Survey import Size as SurveySize
from py_st._manual_models import RefineItem, RefineResult


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
        return agent.model_dump(mode="json")


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
        return contract.model_dump(mode="json")


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
        return ship.model_dump(mode="json")


class WaypointFactory:
    @staticmethod
    def build_minimal(
        symbol: str = "X1-ABC-1",
        system_symbol: str = "X1-ABC",
        waypoint_type: WaypointType = WaypointType.PLANET,
        traits: list[WaypointTraitSymbol] | None = None,
        x: int = 0,
        y: int = 0,
    ) -> dict[str, Any]:
        """Build a minimal valid Waypoint payload dict.

        Args:
            symbol: The waypoint symbol (e.g., "X1-ABC-1")
            system_symbol: The system symbol (e.g., "X1-ABC")
            waypoint_type: The type of waypoint
            traits: List of trait symbols to add to the waypoint
            x: X coordinate
            y: Y coordinate
        """
        trait_list = []
        if traits:
            for trait_symbol in traits:
                trait_list.append(
                    WaypointTrait(
                        symbol=trait_symbol,
                        name=trait_symbol.value,
                        description=f"A waypoint with {trait_symbol.value}",
                    )
                )

        waypoint = Waypoint(
            symbol=WaypointSymbol(symbol),
            type=waypoint_type,
            systemSymbol=SystemSymbol(system_symbol),
            x=x,
            y=y,
            orbitals=[],
            orbits=None,
            traits=trait_list,
            modifiers=None,
            isUnderConstruction=False,
        )
        return waypoint.model_dump(mode="json")


class TradeGoodFactory:
    @staticmethod
    def build_minimal(
        symbol: TradeSymbol = TradeSymbol.IRON_ORE,
    ) -> dict[str, Any]:
        """Build a minimal valid TradeGood payload dict.

        Args:
            symbol: The trade symbol for this good
        """
        trade_good = TradeGood(
            symbol=symbol,
            name=symbol.value,
            description=f"A trade good: {symbol.value}",
        )
        return trade_good.model_dump(mode="json")


class MarketTradeGoodFactory:
    @staticmethod
    def build_minimal(
        symbol: TradeSymbol = TradeSymbol.IRON_ORE,
        trade_type: MarketTradeGoodType = MarketTradeGoodType.EXPORT,
        trade_volume: int = 10,
        supply: SupplyLevel = SupplyLevel.MODERATE,
        purchase_price: int = 100,
        sell_price: int = 90,
    ) -> dict[str, Any]:
        """Build a minimal valid MarketTradeGood payload dict.

        Args:
            symbol: The trade symbol
            trade_type: The type of trade (EXPORT, IMPORT, EXCHANGE)
            trade_volume: The trading volume
            supply: The supply level
            purchase_price: The purchase price
            sell_price: The sell price
        """
        trade_good = MarketTradeGood(
            symbol=symbol,
            type=trade_type,
            tradeVolume=trade_volume,
            supply=supply,
            purchasePrice=purchase_price,
            sellPrice=sell_price,
        )
        return trade_good.model_dump(mode="json")


class MarketFactory:
    @staticmethod
    def build_minimal(
        waypoint_symbol: str = "X1-ABC-1",
        exports: list[TradeSymbol] | None = None,
        imports: list[TradeSymbol] | None = None,
        exchange: list[TradeSymbol] | None = None,
        trade_goods: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a minimal valid Market payload dict.

        Args:
            waypoint_symbol: The waypoint symbol for this market
            exports: List of trade symbols that are exported
            imports: List of trade symbols that are imported
            exchange: List of trade symbols that are exchanged
            trade_goods: Optional list of MarketTradeGood dicts (prices)
        """
        export_goods = [
            TradeGood(
                symbol=sym,
                name=sym.value,
                description=f"A trade good: {sym.value}",
            )
            for sym in (exports or [])
        ]
        import_goods = [
            TradeGood(
                symbol=sym,
                name=sym.value,
                description=f"A trade good: {sym.value}",
            )
            for sym in (imports or [])
        ]
        exchange_goods = [
            TradeGood(
                symbol=sym,
                name=sym.value,
                description=f"A trade good: {sym.value}",
            )
            for sym in (exchange or [])
        ]

        market = Market(
            symbol=waypoint_symbol,
            exports=export_goods,
            imports=import_goods,
            exchange=exchange_goods,
            transactions=None,
            tradeGoods=(
                [MarketTradeGood.model_validate(tg) for tg in trade_goods]
                if trade_goods
                else None
            ),
        )
        return market.model_dump(mode="json")


class ShipyardShipFactory:
    @staticmethod
    def build_minimal(
        ship_type: ShipTypeEnum = ShipTypeEnum.SHIP_MINING_DRONE,
        name: str = "Mining Drone",
        description: str = "A mining drone",
        supply: SupplyLevel = SupplyLevel.MODERATE,
        purchase_price: int = 50000,
    ) -> dict[str, Any]:
        """Build a minimal valid ShipyardShip payload dict.

        Args:
            ship_type: The type of ship
            name: The name of the ship
            description: The description of the ship
            supply: The supply level
            purchase_price: The purchase price
        """
        ship = ShipyardShip(
            type=ship_type,
            name=name,
            description=description,
            supply=supply,
            purchasePrice=purchase_price,
            frame=ShipFrame(
                symbol=FrameSymbol.FRAME_DRONE,
                name="Frame Drone",
                description="A basic frame",
                condition=ShipComponentCondition(1.0),
                integrity=ShipComponentIntegrity(1.0),
                quality=ShipComponentQuality(1),
                moduleSlots=1,
                mountingPoints=1,
                fuelCapacity=100,
                requirements=ShipRequirements(power=1, crew=0, slots=0),
            ),
            reactor=ShipReactor(
                symbol=ReactorSymbol.REACTOR_SOLAR_I,
                name="Solar Reactor I",
                description="A basic reactor",
                condition=ShipComponentCondition(1.0),
                integrity=ShipComponentIntegrity(1.0),
                quality=ShipComponentQuality(1),
                powerOutput=3,
                requirements=ShipRequirements(power=0, crew=0, slots=0),
            ),
            engine=ShipEngine(
                symbol=EngineSymbol.ENGINE_IMPULSE_DRIVE_I,
                name="Impulse Drive I",
                description="A basic engine",
                condition=ShipComponentCondition(1.0),
                integrity=ShipComponentIntegrity(1.0),
                quality=ShipComponentQuality(1),
                speed=2,
                requirements=ShipRequirements(power=1, crew=0, slots=0),
            ),
            modules=[],
            mounts=[],
            crew=Crew(required=0, capacity=0),
        )
        return ship.model_dump(mode="json")


class ShipyardFactory:
    @staticmethod
    def build_minimal(
        waypoint_symbol: str = "X1-ABC-1",
        ship_types: list[ShipTypeEnum] | None = None,
        modifications_fee: int = 1000,
        ships: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a minimal valid Shipyard payload dict.

        Args:
            waypoint_symbol: The waypoint symbol for this shipyard
            ship_types: List of ship type enums available for purchase
            modifications_fee: The fee for modifications
            ships: Optional list of ShipyardShip dicts (available ships)
        """
        if ship_types is None:
            ship_types = [
                ShipTypeEnum.SHIP_PROBE,
                ShipTypeEnum.SHIP_MINING_DRONE,
            ]

        ship_type_list = [ShipType(type=ship_type) for ship_type in ship_types]

        shipyard = Shipyard(
            symbol=waypoint_symbol,
            shipTypes=ship_type_list,
            transactions=None,
            ships=(
                [ShipyardShip.model_validate(s) for s in ships]
                if ships
                else None
            ),
            modificationsFee=modifications_fee,
        )
        return shipyard.model_dump(mode="json")


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


class ExtractionFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Extraction payload dict."""
        extraction_yield_data = ExtractionYield(
            symbol=TradeSymbol.IRON_ORE,
            units=10,
        ).model_dump(mode="json")

        return {
            "shipSymbol": "SHIP-1",
            "yield": extraction_yield_data,
        }


class SurveyFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Survey payload dict."""
        deposit = SurveyDeposit(symbol="IRON_ORE")
        survey = Survey(
            signature="survey-signature-12345",
            symbol="X1-ABC-1",
            deposits=[deposit],
            expiration=datetime.now(UTC) + timedelta(days=1),
            size=SurveySize.SMALL,
        )
        return survey.model_dump(mode="json")


class MarketTransactionFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid MarketTransaction payload dict."""
        transaction = MarketTransaction(
            waypointSymbol=WaypointSymbol("X1-ABC-1"),
            shipSymbol="SHIP-1",
            tradeSymbol="IRON_ORE",
            type=TransactionType.PURCHASE,
            units=10,
            pricePerUnit=100,
            totalPrice=1000,
            timestamp=datetime.now(UTC),
        )
        return transaction.model_dump(mode="json")


class ShipyardTransactionFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid ShipyardTransaction payload dict."""
        transaction = ShipyardTransaction(
            waypointSymbol=WaypointSymbol("X1-ABC-1"),
            shipSymbol="SHIP-MINING-DRONE-1",
            shipType="SHIP_MINING_DRONE",
            price=50000,
            agentSymbol="AGENT-1",
            timestamp=datetime.now(UTC),
        )
        return transaction.model_dump(mode="json")


class RefineResultFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid RefineResult payload dict."""
        # Get a minimal ship cargo from ShipFactory
        ship_data = ShipFactory.build_minimal()
        cargo_data = ship_data["cargo"]

        # Get a minimal cooldown from ShipFactory
        cooldown_data = ship_data["cooldown"]

        # Create produced and consumed items
        produced = [RefineItem(tradeSymbol="FUEL", units=10)]
        consumed = [RefineItem(tradeSymbol="HYDROCARBON", units=100)]

        # Build RefineResult
        refine_result = RefineResult(
            cargo=ShipCargo.model_validate(cargo_data),
            cooldown=Cooldown.model_validate(cooldown_data),
            produced=produced,
            consumed=consumed,
        )
        return refine_result.model_dump(mode="json")


class FactionFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid Faction payload dict."""
        from py_st._generated.models import Faction, FactionSymbol

        faction = Faction(
            symbol=FactionSymbol.COSMIC,
            name="Cosmic Engineers",
            description="A faction of explorers",
            headquarters="X1-ABC-1",
            traits=[],
            isRecruiting=True,
        )
        return faction.model_dump(mode="json")


class RegisterAgentResponseDataFactory:
    @staticmethod
    def build_minimal() -> dict[str, Any]:
        """Build a minimal valid RegisterAgentResponseData payload dict."""
        from py_st._generated.models import Agent, Contract, Faction, Ship
        from py_st._manual_models import RegisterAgentResponseData

        agent = Agent.model_validate(AgentFactory.build_minimal())
        contract = Contract.model_validate(ContractFactory.build_minimal())
        faction = Faction.model_validate(FactionFactory.build_minimal())
        ship = Ship.model_validate(ShipFactory.build_minimal())

        response_data = RegisterAgentResponseData(
            agent=agent,
            contract=contract,
            faction=faction,
            ships=[ship],
            token="test-agent-token-123",
        )
        return response_data.model_dump(mode="json")
