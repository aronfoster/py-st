# Cache Schema Reference

This document describes all cache entry types used in py-st, including
their JSON structures, refresh policies, and associated service functions.

## Cache Location

All cache data is stored in `.cache/data.json` at the project root. The
cache file is a single JSON object where keys are cache entry identifiers
and values are cache entry objects.

## Cache Entry Types

### 1. Agent Info (`agent_info`)

**Purpose:** Caches the current agent's information (credits, HQ, etc.)

**JSON Structure:**
```json
{
  "last_updated": "2025-11-02T10:30:00.000000+00:00",
  "data": {
    "accountId": "...",
    "symbol": "...",
    "headquarters": "...",
    "credits": 150000,
    "startingFaction": "...",
    "shipCount": 5
  }
}
```

**Fields:**
- `last_updated` (string): ISO 8601 timestamp of last API fetch
- `data` (object): Agent model as JSON

**Refresh Policy:** TTL (Time To Live)
- Cache is considered fresh for 1 hour (`CACHE_STALENESS_THRESHOLD`)
- After 1 hour, a new API call is made to refresh the data

**Invalidation Triggers:**
- Time-based: automatic refresh after 1 hour
- Not explicitly invalidated by other operations

**Service Functions:**
- Read: `services/agent.py::get_agent_info()`
- Write: `services/agent.py::get_agent_info()` (on cache miss/stale)

---

### 2. Ship List (`ship_list`)

**Purpose:** Caches the list of all ships owned by the agent

**JSON Structure:**
```json
{
  "last_updated": "2025-11-02T10:30:00.000000+00:00",
  "is_dirty": false,
  "data": [
    {
      "symbol": "SHIP-1",
      "registration": {...},
      "nav": {...},
      "crew": {...},
      "frame": {...},
      "reactor": {...},
      "engine": {...},
      "modules": [...],
      "mounts": [...],
      "cargo": {...},
      "fuel": {...}
    }
  ]
}
```

**Fields:**
- `last_updated` (string): ISO 8601 timestamp of last API fetch
- `is_dirty` (boolean): Flag indicating if cache needs refresh
- `data` (array): List of Ship models as JSON

**Refresh Policy:** Dirty flag + Smart arrival check
- Cache marked dirty when any ship operation modifies state
- Even if not dirty, cache refreshes when any IN_TRANSIT ship has
  arrived (ship.nav.route.arrival <= now)
- `list_ships(need_clean=False)` returns cached data without checks

**Invalidation Triggers:**
- Marked dirty by: navigation, orbit, dock, refuel, cargo operations
  (jettison, sell, purchase, transfer), flight mode changes, refining,
  ship purchases
- Auto-detected: ship arrivals (IN_TRANSIT → arrival time passed)

**Service Functions:**
- Read: `services/ships.py::list_ships()`
- Write: `services/ships.py::_fetch_and_cache_ships()` (on refresh)
- Invalidate: `services/ships.py::_mark_ship_list_dirty()` (called by
  all ship-modifying operations)

---

### 3. Contract List (`contract_list`)

**Purpose:** Caches the list of all contracts available to the agent

**JSON Structure:**
```json
{
  "last_updated": "2025-11-02T10:30:00.000000+00:00",
  "is_dirty": false,
  "data": [
    {
      "id": "...",
      "factionSymbol": "...",
      "type": "...",
      "terms": {...},
      "accepted": true,
      "fulfilled": false,
      "expiration": "...",
      "deadlineToAccept": "..."
    }
  ]
}
```

**Fields:**
- `last_updated` (string): ISO 8601 timestamp of last API fetch
- `is_dirty` (boolean): Flag indicating if cache needs refresh
- `data` (array): List of Contract models as JSON

**Refresh Policy:** Dirty flag
- Cache returns immediately if `is_dirty` is false
- Otherwise, fetches fresh data from API

**Invalidation Triggers:**
- Marked dirty by: negotiate, deliver, accept, fulfill operations

**Service Functions:**
- Read: `services/contracts.py::list_contracts()`
- Write: `services/contracts.py::list_contracts()` (on dirty/miss)
- Invalidate: `services/contracts.py::_mark_contract_list_dirty()`
  (called by all contract-modifying operations)

---

### 4. Waypoints (`waypoints_{system_symbol}`)

**Purpose:** Caches all waypoints in a system (static game data)

**JSON Structure:**
```json
{
  "last_updated": "2025-11-02T10:30:00.000000+00:00",
  "data": [
    {
      "symbol": "X1-ABC-1",
      "type": "...",
      "systemSymbol": "X1-ABC",
      "x": 10,
      "y": 20,
      "orbitals": [...],
      "orbits": "...",
      "faction": {...},
      "traits": [...],
      "chart": {...},
      "isUnderConstruction": false
    }
  ]
}
```

**Fields:**
- `last_updated` (string): ISO 8601 timestamp of last API fetch
- `data` (array): List of Waypoint models as JSON

**Refresh Policy:** Static (no expiry)
- Waypoints are static game data that rarely changes
- Cache is valid indefinitely (until weekly server reset)
- Manual cache clear required to force refresh

**Invalidation Triggers:**
- None (static data)
- User can clear cache with `make clear-cache`

**Service Functions:**
- Read: `services/systems.py::list_waypoints()`
- Write: `services/systems.py::_fetch_and_cache_waypoints()` (on miss)

---

### 5. Market Data (`market_{waypoint_symbol}`)

**Purpose:** Caches market information for a specific waypoint

**JSON Structure:**
```json
{
  "prices_updated": "2025-11-02T10:30:00.000000+00:00",
  "data": {
    "symbol": "X1-ABC-1",
    "exports": [...],
    "imports": [...],
    "exchange": [...],
    "transactions": [...],
    "tradeGoods": [
      {
        "symbol": "IRON_ORE",
        "type": "EXPORT",
        "tradeVolume": 100,
        "supply": "ABUNDANT",
        "activity": "GROWING",
        "purchasePrice": 10,
        "sellPrice": 8
      }
    ]
  }
}
```

**Fields:**
- `prices_updated` (string|null): ISO 8601 timestamp when tradeGoods
  was last populated
- `data` (object): Market model as JSON

**Refresh Policy:** Smart-merge
- Cache preserves `tradeGoods` field even when API returns null
  (happens when querying from a distance)
- Always stores the "best" version (one with tradeGoods populated)
- Static fields like `exports`, `imports`, `exchange` are updated
  from fresh API responses
- `force_refresh=True` bypasses cache for guaranteed fresh data

**Invalidation Triggers:**
- Smart merge: tradeGoods preserved when API returns incomplete data
- Full refresh: when agent is at the market location

**Service Functions:**
- Read: `services/systems.py::get_market()`
- Write: `services/systems.py::get_market()` (on miss/refresh)
- Merge: `services/cache_merge.py::smart_merge_cache()` (handles
  preservation logic)

---

### 6. Shipyard Data (`shipyard_{waypoint_symbol}`)

**Purpose:** Caches shipyard information for a specific waypoint

**JSON Structure:**
```json
{
  "ships_updated": "2025-11-02T10:30:00.000000+00:00",
  "data": {
    "symbol": "X1-ABC-1",
    "shipTypes": [
      {"type": "SHIP_MINING_DRONE"},
      {"type": "SHIP_INTERCEPTOR"}
    ],
    "transactions": [...],
    "ships": [
      {
        "type": "SHIP_MINING_DRONE",
        "name": "...",
        "description": "...",
        "supply": "ABUNDANT",
        "activity": "GROWING",
        "purchasePrice": 50000,
        "frame": {...},
        "reactor": {...},
        "engine": {...},
        "modules": [...],
        "mounts": [...]
      }
    ]
  }
}
```

**Fields:**
- `ships_updated` (string|null): ISO 8601 timestamp when ships field
  was last populated
- `data` (object): Shipyard model as JSON

**Refresh Policy:** Smart-merge
- Cache preserves `ships` field even when API returns null (happens
  when querying from a distance)
- Always stores the "best" version (one with ships populated)
- Static fields like `shipTypes` are updated from fresh API responses
- `force_refresh=True` bypasses cache for guaranteed fresh data

**Invalidation Triggers:**
- Smart merge: ships preserved when API returns incomplete data
- Full refresh: when agent is at the shipyard location

**Service Functions:**
- Read: `services/systems.py::get_shipyard()`
- Write: `services/systems.py::get_shipyard()` (on miss/refresh)
- Merge: `services/cache_merge.py::smart_merge_cache()` (handles
  preservation logic)

---

## Cache Key Naming Conventions

| Cache Type | Key Format | Example |
|------------|------------|---------|
| Agent | `agent_info` | `agent_info` |
| Ships | `ship_list` | `ship_list` |
| Contracts | `contract_list` | `contract_list` |
| Waypoints | `waypoints_{system_symbol}` | `waypoints_X1-ABC` |
| Markets | `market_{waypoint_symbol}` | `market_X1-ABC-1` |
| Shipyards | `shipyard_{waypoint_symbol}` | `shipyard_X1-ABC-1` |

## Refresh Policy Summary

| Cache Type | Policy | Details |
|------------|--------|---------|
| Agent | TTL | 1 hour threshold |
| Ships | Dirty + Smart | Manual invalidation + arrival check |
| Contracts | Dirty | Manual invalidation only |
| Waypoints | Static | No expiry (static game data) |
| Markets | Smart-merge | Preserves tradeGoods when incomplete |
| Shipyards | Smart-merge | Preserves ships when incomplete |

## Implementation Notes

### Smart-Merge Algorithm

The smart-merge pattern is used for Markets and Shipyards to handle
API responses that may be incomplete when queried remotely:

1. Fresh API call is made (cache miss or force_refresh=True)
2. Check if fresh data has the key field (tradeGoods/ships)
3. If yes: use fresh data entirely, update timestamp
4. If no: merge fresh data with cached key field (if available)
5. Save merged result back to cache

This ensures that once complete data is cached, it's never replaced by
incomplete data from remote queries.

### Dirty Flag Pattern

Used by Ships and Contracts to track when cached data is invalidated:

1. Operations that modify state call `_mark_*_dirty()`
2. Next read checks `is_dirty` flag
3. If dirty: fetch fresh data and set `is_dirty = false`
4. If clean: return cached data immediately

This minimizes unnecessary API calls while ensuring consistency.

### Cache Keys Helper

To prevent typos and maintain consistency, all cache keys should be
generated using helper functions in `services/cache_keys.py`:

```python
from py_st.services.cache_keys import (
    key_for_agent,
    key_for_ship_list,
    key_for_contract_list,
    key_for_waypoints,
    key_for_market,
    key_for_shipyard,
)
```
