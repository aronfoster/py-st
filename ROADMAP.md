# Roadmap

The immediate goal is to improve the "playability" of the CLI by implementing a comprehensive cache. This will reduce the need to copy-paste IDs, remember waypoint symbols, and manually look up market data.

---

## Bugs

**HIGH PRIORITY**

* I forgot to have ship status marked stale in cache during change events like orbit, dock, transit. Should always be stale during transit. Should update prety-print ship status to show current fuel / max fuel.

**Low Priority**

* ShipsEndpoint.get_ships and ContractsEndpoint.get_contracts could use pagination. Can we just make pagination it default for all requests? Or do we need to define which ones should be paginated explicitly?
* SystemsEndpoint.list_waypoints_all accepts a traits filter but should no longer do so. It is not currently used.

---

## Sprint 3: Cargo & Contracts

The goal of this sprint is to add the core gameplay loop of buying and delivering cargo for contracts. We will refactor all index lookups to use unambiguous prefixes (e.g., `s-0`, `w-0`).

* **Refactor Index Helpers to Use Prefixes:**
    * Modify `cli/_helpers.py` to change `resolve_ship_id` to look for a prefix (e.g., `s-0`) instead of just digits.
    * Modify `cli/_helpers.py` to change `resolve_waypoint_id` to look for a prefix (e.g., `w-0`).
    * Update help text in `cli/options.py` to reflect the new `s-0` and `w-0` format.
    * Update tests in `test_cli_helpers.py` to verify the new prefix logic.

* **Implement Ship Index Lookup for `contracts` Commands:**
    * Update `contracts_cmd.py` (for `negotiate`, `deliver`) to use the (now prefixed) `resolve_ship_id` helper.

* **Write Unit Tests for `contracts.py`:**
    * Add a new test file (`tests/test_services_contracts.py`).
    * Write tests for all public functions in `services/contracts.py`, mocking the `SpaceTradersClient`.

* **Implement `contracts` Caching & Indexing:**
    * Implement time-based caching for `services/contracts.list_contracts`.
    * Implement "pretty-print" for the `contracts list` command, showing an index (e.g., `[c-0]`).
    * Create a `resolve_contract_id` helper that looks for a prefix (e.g., `c-0`).
    * Update contract commands (`accept`, `deliver`, `fulfill`) to use the new `resolve_contract_id` helper.

---

## Sprint 4: Market Queries & Ergonomics

* **Add CLI Commands to Query Cache:**
    * Create new CLI commands to query cached system data. Examples:
        * `py-st systems markets --buys IRON_ORE`
        * `py-st systems markets --sells FUEL`

* **Improve CLI Argument Ergonomics:**
    * Update CLI commands to use `Enum` types for arguments where possible (e.g., `ShipNavFlightMode` for the `ships flight-mode` command) so `typer` can provide automatic validation and help text.

---

## 🧹 Refactoring & Tech Debt

These items improve code quality and performance but are not tied to a specific feature sprint.

* **Refactor "Smart Merge" Caching Logic:**
    * The `get_market` and `get_shipyard` functions in `services/systems.py` share nearly identical "smart merge" caching logic.
    * Refactor this duplicated code into a single, generic helper function to keep the services module clean.

* **Update `list_system_goods`:**
    * Modify `list_system_goods` to use the cached `get_market` function. This will make it much faster as it will no longer make N-1 API calls.

---

## 🔭 Long-Term Goals

(These items are carried over from the previous roadmap)

* Develop a script to run a basic ship automation loop.
* Investigate `openapi-python-client` or rolling my own method to turn `SpaceTraders.json` spec automatically into client prototypes.
* Currently using agent tokens, which expire every week. Explore Register by API with an account token, then automatically create a new agent if none exist.
* Improve web requests (rate limiting, async, etc.).
* GUI
    * Research and select a GUI framework (e.g., PySide6, Tkinter).
    * Design a basic UI to display universe/fleet data and trigger actions.
    * Implement the GUI, ensuring it runs in a separate thread from the automation logic.
 
---

## ✅ Done

* **Sprint 3: Cargo & Contracts**
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
