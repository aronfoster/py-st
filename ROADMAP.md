# Roadmap

The immediate goal is to improve the "playability" of the CLI. Much work has already been done but some improvements and refactoring remain.

---

## Bugs

**HIGH PRIOTIRY**

* Cache calls should use a "need clean" boolean, default true. All acche objects will have a dirty flag and all calls to the cache will have a "need clean" if they reference fields that are dynamic (per serve reset; e.g. money, fuel, prices)
* `systems market w-41` doesn't get market prices or values if it finds it in the cache (without market prices)
* In Transit ship cache dirty is broken somehow:

    ```
    py_st ships list
    [0] SOURCE_CODE-1        COMMAND      (Fuel: 283/400) IN_TRANSIT to X1-VF50-E42 (Arrived)
    [1] SOURCE_CODE-2        SATELLITE    (Fuel: 0/0) DOCKED at X1-VF50-H50
    ```
    This should have triggered another API call (every `ships list` with an IN_TRANSIT ship is dirty? Or maybe once the lowest transit time has expired!).
* Why did this hit the `my/ships` API? Ship cache dirty from transit, not cleaned by `ships list`? But doesn't matter for getting the ship id/name.
    ```
    py_st contracts deliver c-1 s-0 POLYNUCLEOTIDES 14
    INFO root: Resolved contract index 1 to ID: cmhfj5rc2dqvgui6xzct6tmrs
    INFO httpx: HTTP Request: GET https://api.spacetraders.io/v2/my/ships "HTTP/1.1 200 OK"
    INFO root: Resolved ship index 0 to symbol: SOURCE_CODE-1
    ```

**Low Priority**

* ShipsEndpoint.get_ships and ContractsEndpoint.get_contracts could use pagination. Can we just make pagination it default for all requests? Or do we need to define which ones should be paginated explicitly?
* SystemsEndpoint.list_waypoints_all accepts a traits filter but should no longer do so. It is not currently used.
* pretty-print contracts headers don't always line up with rows. Figure out the right number of spaces programatically
* `systems waypoints` has some display quirks:

    ```
    [9] X1-VF50-B15  (ASTEROID          ) Traits: COMMON_METAL_DEPOSITS
    [10] X1-VF50-B16  (ASTEROID          ) Traits: MINERAL_DEPOSITS, MICRO_GRAVITY_ANOMALIES, RADIOACTIVE
    ```
    The vertical alignment breaks for ones-tens-hundreds index changes. The spaces are inside parenthesis instead of outside. Can we shorten the trait names? That might require manual conversion.
* contract-id help is incorrect. Not just "accept", and should mention shortcut :
    ```
    Deliver cargo to a contract.

╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────╮
│ *    contract_id       TEXT                                The ID of the contract to accept.   │
│                                                            [required]                          │
    ```

---

## Sprint 5: Ergonomics and Tech Debt

* Formatting/UX: unify CLI formatting (columns, relative time, short money, id6, 2-char faction), consistent flags, stable sort.

* Resolvers: centralize s-, w-, c- logic to one helper so every command benefits.

* Errors & msgs: friendlier exceptions + concise failure summaries.

* Systems/markets polish: reuse cached waypoints/markets; fast filters.

* Small refactors: split oversized service files by concern (navigation, cargo, market), keep functions short.

* **Refactor "Smart Merge" Caching Logic:**
    * The `get_market` and `get_shipyard` functions in `services/systems.py` share nearly identical "smart merge" caching logic.
    * Refactor this duplicated code into a single, generic helper function to keep the services module clean.

* **Document Cache Structure:**
    * Update `cache/SCHEMA.md` with schema info. Normalize keys and naming (need to explore options and pick one). Should we add a helper function to get the key name for a given function?

---

## 🔭 Long-Term Goals (not ordered)

* Survey caching
* Develop a script to run a basic ship automation loop.
  * first loop: get contract. accept contract. find marketplace that sells product. orbit. navigate. dock. refuel. buy product. orbit. navigate to delivery point. dock. refuel. deliver. complete.
* Investigate `openapi-python-client` or rolling my own method to turn `SpaceTraders.json` spec automatically into client prototypes.
* Currently using agent tokens, which expire every week. Explore Register by API with an account token, then automatically create a new agent if none exist.
* Improve web requests (rate limiting, async, etc.).
* GUI
    * Research and select a GUI framework (e.g., PySide6, Tkinter).
    * Design a basic UI to display universe/fleet data and trigger actions.
    * Implement the GUI, ensuring it runs in a separate thread from the automation logic.

---

## To Explore

* General clean code and refactoring ideas
*

---

## ✅ Done

* **Sprint 5: Ergonomics and Tech Debt**
    * ✅ **Improve CLI Argument Ergonomics:**
        * ✅ Updated CLI commands to use `Enum` types for arguments across ships, contracts, and systems commands
        * ✅ `ships flight-mode` now accepts `ShipNavFlightMode` enum (CRUISE, BURN, DRIFT, STEALTH)
        * ✅ `ships refine` produce argument now uses `TradeSymbol` enum
        * ✅ `ships purchase` ship_type argument now uses `ShipType` enum
        * ✅ `contracts deliver` trade_symbol argument now uses `TradeSymbol` enum
        * ✅ `ships sell/purchase-cargo/jettison` trade_symbol arguments now use `TradeSymbol` enum
        * ✅ `systems waypoints --trait` filter now uses `WaypointTraitSymbol` enum
        * ✅ Typer now provides automatic validation and displays enum choices in help text
        * ✅ Added comprehensive CLI parsing tests for enum validation

* **Sprint 4: Market Queries & Ergonomics**
    * ✅ **Add CLI Commands to Query Cache:**
        * ✅ Added `py-st systems markets` command with `--buys` and `--sells` filtering
        * ✅ Supports case-insensitive trade symbol matching
        * ✅ Supports `--json` output and human-readable indexed display
        * ✅ Uses cached data via refactored `list_system_goods`
    * ✅ **Update `list_system_goods`:**
        * ✅ Modified `list_system_goods` to use the cached `get_market` and `_fetch_and_cache_waypoints` functions
        * ✅ Now leverages "smart merge" caching strategy for markets
        * ✅ Updated all service tests to mock caching functions

* **Bugs**
    * ✅ Refactored ship list cache to use "dirty" flag instead of time-based staleness. Updated ships list command to display fuel (current/max).

* **Sprint 3: Cargo & Contracts**
    * ✅ **Compact Contracts List Enhancement:**
        * ✅ Enhanced `contracts list` command with compact, informative default output
        * ✅ Added relative due date display (e.g., "in 6d 3h", "overdue by 1h 12m")
        * ✅ Added short-form payment display (e.g., "32k", "1.25M")
        * ✅ Added 2-character faction abbreviation
        * ✅ Added waypoint index display for deliverable destinations (e.g., "[w-12]")
        * ✅ Implemented `--stacked` flag for two-line detailed format
        * ✅ Added comprehensive tests for all formatting helpers
    * ✅ **Refactor Index Helpers to Use Prefixes:**
        * ✅ Modified `cli/_helpers.py` to change `resolve_ship_id` to look for a prefix (e.g., `s-0`) instead of just digits.
        * ✅ Modified `cli/_helpers.py` to change `resolve_waypoint_id` to look for a prefix (e.g., `w-0`).
        * ✅ Updated help text in `cli/options.py` to reflect the new `s-0` and `w-0` format.
        * ✅ Updated tests in `test_cli_helpers.py` to verify the new prefix logic.
    * ✅ **Implement `purchase-cargo` Command:**
        * ✅ Added `purchase_cargo` to `client/endpoints/ships.py` (POST /my/ships/{shipSymbol}/purchase).
        * ✅ Added `purchase_cargo` function to `services/ships.py`.
        * ✅ Added unit tests for the new service function to `tests/test_services_ships.py`.
        * ✅ Added new `purchase-cargo` command to `cli/ships_cmd.py`.

* **Sprint 2: QOL & Waypoint Playability**
    * ✅ **Implement "Default to HQ System" Feature:**
        * ✅ Created `get_default_system` helper to parse HQ system from cached agent info.
        * ✅ Changed `SYSTEM_SYMBOL_ARG` to `SYSTEM_SYMBOL_OPTION` in `options.py`.
        * ✅ Updated all commands in `systems_cmd.py` to use the optional `--system` flag.
        * ✅ Updated `ships navigate` and `ships purchase` to accept the optional `--system` flag for waypoint resolution.
    * ✅ **Improve `systems waypoints` command:** `waypoints` now defaults to an indexed "pretty-print" list and uses `--json` for raw output.
    * ✅ **Implement Waypoint Index Lookup:** Added `resolve_waypoint_id` to `cli/_helpers.py` and updated `systems market/shipyard` commands to accept 0-based indexes.

* **Sprint 1: Ships Playability**
    * ✅ **Testing:** Added `tests/test_services_ships.py` with full unit test coverage for `services/ships.py`.
    * ✅ **Caching:** Added time-based caching to `services/ships.list_ships`.
    * ✅ **CLI Indexing:** Implemented `cli/_helpers.py` with `resolve_ship_id` and updated all `ships_cmd.py` commands to accept a 0-based index.
    * ✅ **CLI Listing:** `py-st ships list` now defaults to a "pretty-print" format and retains JSON output via `--json`.

* **Infrastructure:**
    * ✅ Added `make clear-cache` to the `Makefile` to delete `.cache/data.json`.
