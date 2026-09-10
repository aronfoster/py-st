# Historical Route Replay

`auto backtest` evaluates one owner-chosen route using actual stored market
observations. It is entirely offline, opens an existing SQLite database read-only,
does not load credentials or create a Session, and works with STOP present.
It neither changes STOP nor writes plans, positions, observations or actions.

## Usage

From the isolated worktree, inspect `auto report --scope RESET:AGENT` for the
stored time range and markets, then choose a route and explicit assumptions:

```sh
PYTHONPATH=src ../../.venv/bin/python -m py_st auto backtest \
  X1-CY22-D48 X1-CY22-H58 SHIP_PLATING \
  --scope 2026-09-06:SOURCE_CODE \
  --start 2026-09-07T00:00:00Z --end 2026-09-09T00:00:00Z \
  --leg-seconds 60 --fuel-allowance 144 \
  --capacity 40 --initial-credits 175000 --credit-floor 50000 \
  --max-age 900 --slippage-bps 500
```

The time and fuel values above are illustrative assumptions, not calibrated ship
performance. `--fuel-allowance` is **credits per round trip**, not fuel units or
price per fuel pack. `--leg-seconds` includes the assumed one-way travel/handling
delay. Set both for the ship and route being studied; zero fuel cost is allowed
only as an explicit sensitivity scenario. `--database PATH` can select a backup.
The JSON output can be redirected to an ignored local file for comparison.

## Time and Economics Rules

- Only `live-api` market observations in the explicit reset/agent scope and two
  same-system markets are used. Synthetic strategy data and journal transactions
  are not quote substitutes. Times must include a timezone and are normalized to
  UTC. Observation time means when the client recorded the data, not exchange time.
- Each detailed source observation within the window is a potential entry.
  Sparse observations do not refresh the age of the last detailed good quote.
  Buyer selection at entry uses the latest timestamp no later than entry; ties
  use observation IDs, excluding records inserted after that source observation.
  No latest-state API, future quote, or subsequent best-route ranking is used.
- The entry buyer must be at most `max-age` seconds old. Buy price is rounded up
  after the slippage premium; sell price is rounded down after the haircut (500
  basis points = 5%). Units are capped by cargo, both entry volumes, and cash
  remaining above the floor after the entire round-trip fuel allowance.
- Only strictly positive entry estimates enter. Purchase plus full fuel allowance
  is deducted immediately. Trials never overlap: the next entry must be at least
  two legs later. A full round trip must fit within the chosen window.
- At modeled arrival, settlement uses the latest buyer quote observed **after
  entry and at or before arrival**, within the age limit. No interpolation, first
  quote after arrival, or reuse of the entry quote to manufacture a winning exit.
  Price crashes settle as losses; the entry profit estimate is not a sell floor.
- Missing/stale exit evidence or reduced volume below the entire held quantity
  leaves one unresolved position and blocks all further entries. No partial fills,
  invented liquidation or free capital recycling. Later evidence does not repair
  that trial automatically. The full fuel allowance remains charged.

## Reading the Report

`summary` counts candidates, entries, settlements, unresolved positions, and
skips by reason. `settled_scenario_net` sums only modeled closed positions;
`worst_settled_net` and `losses` retain adverse outcomes. No settlements gives
`worst_settled_net: null`, not proof of zero risk. `ending_cash` and `cash_change`
also include cash tied up in an unresolved purchase. Its inventory is explicitly
unvalued, so neither cash change nor settled net is total portfolio profit.
Each attempt includes source/entry/exit observation IDs, original timestamps,
quote ages, volumes, assumed execution prices, planned margin, and final status.

## Limits

This is a counterfactual quote replay, **not realized or guaranteed profit**.
Quotes do not prove executable liquidity. Trade volume is only a conservative
batch cap, not guaranteed stock or demand. Slippage is a stress assumption, not
a worst-case bound. The replay does not model own market impact, unobserved
changes, partial fills, ship condition, actual fuel availability/capacity,
cooldowns, repairs, contract obligations, or alternative uses of ship time.
It assumes an empty ship at the source, symmetric travel time, and a feasible
return/refuel path. Synthetic credits may compound only after modeled settlement;
they are never actual account balances or instructions to live automation.

Sampling is irregular and gameplay-driven: past trades changed the market and
scouts determined which prices were recorded. Many windows may have no eligible
entries or end unresolved. Missing evidence is not a loss-free trade. Choosing
the route, window, or assumptions after seeing results creates selection bias;
no-lookahead joins do not remove that bias. Fix assumptions before a held-out
window and compare multiple travel, age and slippage settings. Do not interpret
this as an unbiased strategy backtest, annualize sparse results, or compare only
the settled subset while ignoring unresolved exposure.

The evaluator loads the selected route's quote history into memory. It supports
schema version 1 only, rejects malformed relevant quotes, and intentionally
does not migrate, repair, or update the database.

## Stored-Data Verification

The example above was run against the existing local FOS-63 ledger without any
game requests. Its 94 market observations span September 7, 2026 at 23:32 UTC
through September 8 at 00:46 UTC. Holding the other example inputs constant:

| Assumed Leg Seconds | Entries / Settled | Modeled Net | Worst Trade | Losses |
| ---: | ---: | ---: | ---: | ---: |
| 30 | 9 / 9 | 102,744 | -6,114 | 1 |
| 60 | 5 / 5 | 66,822 | 798 | 0 |
| 120 | 4 / 4 | 43,362 | -5,742 | 1 |

All three runs saw 32 source candidates and no unresolved positions. The
60-second run skipped 14 in-transit, nine missing/stale-buyer, and four
nonpositive-margin candidates. Its last entry estimate of 6,102 fell to a
modeled 798 at arrival. The other assumptions exposed actual recorded price
declines as scenario losses. These are sensitivity checks, **not additional
in-game earnings**, proof of executable trades, or a recommendation to choose
the most profitable timing. Changed sampling times change eligible entries as
well as exit prices, so the scenarios do not describe identical sets of trades.

The fixture suite separately verifies unresolved exposure, missing/stale quotes,
shrinking exit volumes, future-price exclusion, tied timestamps, timezone
ordering, cash/volume caps, non-overlap, and offline CLI behavior with STOP set.
