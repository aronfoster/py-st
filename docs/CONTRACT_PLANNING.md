# Offline Contract Portfolio Planning

## Purpose and Safety Boundary

`auto contract-model INPUT.json` evaluates every delivery obligation in a
procurement contract without loading a token, opening SQLite, or making a
network request. It supports multiple goods, multiple delivery terms, multiple
sources, trade-volume-limited purchase batches, and cargo-capacity-limited
trips. It is deliberately a **counterfactual model**, not an executor: every
result contains `execution_authorized: false`.

The existing live `auto contract` workflow remains limited to its separately
tested single-good paths. Do not manually translate model steps into mutations.
The nighttime agent should first add a journaled state machine with recovery
proof for the complete obligation portfolio.

## Input

Create a disposable JSON file outside `.state` containing an observed contract
and explicit route quotes:

```json
{
  "contract": {
    "id": "SYNTHETIC-CONTRACT",
    "accepted": false,
    "terms": {
      "deadline": "2099-01-01T00:00:00Z",
      "payment": {"onAccepted": 10000, "onFulfilled": 80000},
      "deliver": [
        {
          "tradeSymbol": "EQUIPMENT",
          "destinationSymbol": "X1-TEST-D",
          "unitsRequired": 55,
          "unitsFulfilled": 5
        },
        {
          "tradeSymbol": "MEDICINE",
          "destinationSymbol": "X1-TEST-D",
          "unitsRequired": 10,
          "unitsFulfilled": 0
        }
      ]
    }
  },
  "ship_capacity": 40,
  "credits": 150000,
  "credit_floor": 50000,
  "fuel_allowance": 1000,
  "price_margin": 0.2,
  "deadline_margin_seconds": 3600,
  "quotes": [
    {
      "trade_symbol": "EQUIPMENT",
      "source": "X1-TEST-S",
      "destination": "X1-TEST-D",
      "purchase_price": 400,
      "trade_volume": 20,
      "available_units": 50,
      "fuel_cost": 100,
      "travel_seconds": 600
    },
    {
      "trade_symbol": "MEDICINE",
      "source": "X1-TEST-M",
      "destination": "X1-TEST-D",
      "purchase_price": 500,
      "trade_volume": 5,
      "fuel_cost": 50,
      "travel_seconds": 200
    }
  ]
}
```

Run it with the project environment explicitly selected:

```sh
PYTHONPATH=src python -m py_st auto contract-model /tmp/contract.json
```

Each quote is a caller-provided snapshot. `fuel_cost` and `travel_seconds` are
the complete one-trip source-to-destination estimates; the model intentionally
does not invent undocumented fuel or time formulas. `available_units` is an
optional planning ceiling, not a claim that the API guarantees total inventory.
`trade_volume` controls purchase batches, while `ship_capacity` controls trips.

The result conservatively applies `price_margin` to goods, charges fuel for
every cargo trip, keeps the configured floor and allowance, excludes an already
received acceptance payment, and checks total modeled travel against the
contract deadline. Accepted contracts can remain feasible at a loss because
they are obligations; unaccepted offers require positive conservative net.

## Important Model Limits

- Source-to-source repositioning, return/refuel legs, cooldowns, docking/orbit
  actions, market staleness, ship condition, and opportunity cost are not yet
  automatically inferred. Include their costs in route inputs or treat the
  result as optimistic.
- Greedy source allocation ranks conservative landed cost per cargo chunk. It
  is deterministic and inspectable, but it is not a global vehicle-routing
  optimizer and does not combine compatible goods in one hold.
- A quote's `available_units` is synthetic planning evidence. The official API
  documents `tradeVolume` as the per-transaction purchase limit, not durable
  inventory availability. Every live batch must refresh its price and volume.
- A plan never authorizes acceptance, purchase, navigation, delivery, or
  fulfillment. Existing STOP, pending-action reconciliation, contract cargo,
  deadline, fuel, and reserve guards remain authoritative.

## Nighttime Implementation Sequence

1. Back up the authoritative live database with `auto backup`; do not copy WAL
   files or initialize a replacement ledger for the same agent.
2. Refresh agent, fleet, all contracts, pending actions, open positions,
   waypoints, and detailed markets with ships present. Stop on 401 or 4113.
3. Export a temporary model input from those fresh observations. Include every
   unfulfilled delivery and cost every source/destination leg independently.
4. Review `reasons`, trip counts, batches, deadlines, and the lowest-credit
   point. Reject any plan dependent on contract payout to fund obligations.
5. Before expanding execution, implement one persisted portfolio position with
   immutable original terms, source ceilings, ship assignments, and per-good
   progress. Recovery must derive from fresh contract/cargo state.
6. Add offline interruption tests after acceptance and after every purchase,
   departure, delivery, and fulfillment boundary. Unknown dispatched outcomes
   must remain pending until evidence-based reconciliation.
7. Live-test only a bounded dry run first. Begin with one ship and one contract;
   do not enable jump, warp, DRIFT, construction supply, or ship purchases.

## Official API Findings

Official SpaceTraders OpenAPI 2.3.0 was rechecked read-only on 2026-09-08 at
upstream commit `45fbb04130aca3fa0bd9a634ab77b35fa6c468ab`:

- acceptance is allowed only for an offered, unaccepted, unexpired contract;
- delivery requires the ship at the term's destination with the required good,
  and removes delivered units from cargo;
- fulfillment requires all delivery terms fulfilled;
- cargo purchases require a docked ship at a marketplace selling the good, and
  `tradeVolume` is the maximum units in each purchase transaction.

Sources: [official OpenAPI page](https://docs.spacetraders.io/openapi) and
[upstream specification](https://github.com/SpaceTradersAPI/api-docs/blob/45fbb04130aca3fa0bd9a634ab77b35fa6c468ab/reference/SpaceTraders.json).

## Exploration Preparation (No Execution Enablement)

The same official specification documents construction inspection/supply,
jump, warp, extraction, and surveyed extraction. This provides useful planning
work but does not relax FOS-63 guards:

- Construction supply removes specified cargo into a currently under-
  construction site. Model remaining material as `required - fulfilled`,
  refresh before each load, and assume no payout unless fresh evidence says so.
- Jump requires orbit at a connected gate and automatically purchases and
  consumes one variable-price antimatter unit. A controlled experiment still
  needs fresh connections, both gate states, cooldown, cost, and return plan.
- Warp requires orbit and an installed Warp Drive, consumes ship fuel, and
  blocks most actions until arrival. Do not reuse same-system fuel estimates.
- Extraction requires orbit at an extractable waypoint and matching mining
  equipment. Surveyed extraction requires the unchanged signed survey object.

The nighttime agent can build pure cost models and synthetic recovery tests for
these capabilities. It must not add them to the mutation allowlist or execute
them until the ticket's explicit prohibition is separately resolved.
