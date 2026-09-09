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

## Offline Source Shortlist

```sh
PYTHONPATH=src python -m py_st auto sources CONTRACT_ID \
  --scope RESET:AGENT --database /path/to/existing-ledger.sqlite3 \
  --max-age 900
```

`auto sources` is **OFFLINE ONLY**, unlike live automation dry runs. It opens
an existing ledger read-only, requires an explicit known reset/agent scope,
and never loads credentials, creates a Session, calls the API, or records a
plan. A fresh cloud checkout without a ledger receives an error; it does not
initialize one or obtain live data. The shared `contract_sources` service
reads a consistent SQLite snapshot without a schema change or migration.
Read-only means **no ledger record writes**, not zero filesystem writes:
SQLite may create WAL/shared-memory sidecars (`-wal`/`-shm`) or update shared
memory while reading a WAL-mode database. The connection uses `mode=ro`, not
`immutable=1`, so committed records still in the WAL remain visible. Do not
use immutable mode on an active ledger to avoid sidecars; it ignores the WAL
and can return stale data.

The JSON shortlist uses the latest stored contract and market adverts for every
remaining delivery good/destination. Repeated delivery terms are consolidated;
each advertised market appears once per good/destination, not as additive supply.
Exporters and exchanges rank before importers, then by straight-line Euclidean
source-to-delivery distance and source symbol. Same-system symbols constrain
discovery; absent waypoint coordinates produce a null distance, not invented
geometry. No optimizer, cross-system search or ship assignment is performed.

`quote_observed_at` and `quote_age_seconds` belong to the latest detailed market
snapshot when it contains that good, not the newer sparse advert. Only the latest
detailed market snapshot is inspected: missing/invalid goods do not fall back
to older per-good prices. Price and trade volume are null unless both are
positive integers and the original quote age is within `--max-age` (900 seconds
by default). Stale, missing, invalid and future-dated evidence is explicit.
A newer sparse advert leaves a fresh retained quote labeled `fresh_historical`
and **not actionable**; it does not restore current price visibility.

`actionable_quote` means only that the latest stored market observation contains
fresh valid detailed evidence. It is not execution permission. Contract status,
acceptance/delivery deadlines and expired/fulfilled sourcing blockers are
reported separately; adverts may still be inspected for blocked contracts.
Unknown deadlines are labeled unknown rather than assumed safe. There is no
`execution_authorized` field, acceptance recommendation, inventory estimate,
goods budget, fuel/travel estimate or profit claim. Use `auto contract-model`
with explicit inputs for the **whole obligation**, including all goods and
route costs. Every live action still requires fresh observations and existing
execution/recovery guards.

## Input

Create a disposable JSON file outside `.state` containing an observed contract
and explicit route quotes:

```json
{
  "contract": {
     "id": "SYNTHETIC-CONTRACT",
     "accepted": false,
     "fulfilled": false,
     "deadlineToAccept": "2098-12-31T00:00:00Z",
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
optional shared ceiling for a `(source, trade_symbol)` pair, consumed across all
delivery terms and destinations, not a separate allocation per route. Every
quote for that pair must specify the same ceiling, or all must omit it (no
modeled supply limit). Zero is allowed. Inconsistent ceilings, including mixing
omitted and specified values, are rejected. Duplicate
`(source, trade_symbol, destination)` route quotes are rejected rather than
counted as extra supply. These ceilings do not guarantee API inventory.

`trade_volume` limits each purchase and `ship_capacity` limits each cargo load.
Purchase batches are counted separately for every load, not by dividing total
units by volume: 80 units with capacity 40 and volume 30 need two trips and
four purchases (30 + 10 for each load), not three purchases.

Credits, credit floor, fuel allowance and deadline margin must be non-negative
integers; booleans are rejected. `price_margin` must be a finite, non-negative
number, not a boolean, NaN or infinity. Capacity, required units, matching quote
prices and trade volumes must be positive integers; fulfilled units must lie
between zero and required units. Matching route fuel/time costs and explicit
availability ceilings must be non-negative integers.

The result conservatively applies `price_margin` to goods, charges fuel for
every cargo trip, keeps the configured floor and allowance, excludes an already
received acceptance payment, and checks total modeled travel against the
contract deadline. Accepted contracts can remain feasible at a loss because
they are obligations; unaccepted offers require positive conservative net.
An already fulfilled contract is rejected as invalid model input. An expired
unaccepted offer is infeasible using `deadlineToAccept`, with legacy `expiration`
used only when that key is absent. Acceptance expiry is distinct from the
delivery deadline and is not applied to already accepted obligations. Supplied
deadlines must include a timezone; missing deadlines are not inferred.

The full funding requirement is `credit_floor + fuel_allowance +
conservative_goods_cost + fuel_cost`, paid from current credits without relying
on either future award. An infeasible allocation can contain partial steps and
costs; those totals are not a funded complete portfolio.

## Important Model Limits

- Source-to-source repositioning, return/refuel legs, cooldowns, docking/orbit
  actions, market staleness, ship condition, and opportunity cost are not yet
  automatically inferred. Include their costs in route inputs or treat the
  result as optimistic.
- Greedy source allocation ranks conservative landed cost per cargo chunk. It
  processes delivery terms in input order and consumes shared source capacity.
  An earlier term can exhaust a scarce source needed by a later term even when
  assigning the earlier term elsewhere would satisfy both. Thus an infeasible
  result can be a greedy false negative, not proof that no feasible allocation
  exists. It is not globally optimal and does not combine goods in one hold.
- A quote's `available_units` is synthetic planning evidence. The official API
  documents `tradeVolume` as the per-transaction purchase limit, not durable
  inventory availability. Every live batch must refresh its price and volume.
- A plan never authorizes acceptance, purchase, navigation, delivery, or
  fulfillment. Existing STOP, pending-action reconciliation, contract cargo,
  deadline, fuel, and reserve guards remain authoritative.

## Verification

Reported full offline verification for the current planner and funded local
refuel increment: **560 passed, 1 skipped**. This documentation-only pass did not
rerun checks or make live requests. The portfolio model remains analysis-only;
the new earning-controller refuel selection has no live proof yet.

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
