# Refueling-Aware Navigation

## Remote Procurement Live Proof

On `1bb3a78` (2026-09-08), guarded hauler A4->E52->C45 consumed **63+150 = 213**
fuel versus conservative ceil-distance estimate 63+151. Both departures passed
the existing carried delivery-leg guard; the destination-refuel exception was
not needed or bypassed. A probe at C45 supplied fresh FUEL 72/pack before remote
acceptance and acquisition. Procurement protected a full-tank reserve of
`4 * ceil(72 * 1.2) = 348`, separately from goods/floor/1,000 allowance.
After fulfillment, existing guarded `auto refuel` dry run reserved 261 for the
actual missing 213 units; execution spent **216** for 3 packs and restored 400.
Final hauler is docked C45 with empty cargo. Each future leg needs its own fresh
plan; no return to A4 was performed. See MINING_CONTRACTS for complete economics.

## Verified Sources

Reviewed the current public documentation and upstream OpenAPI without using
an API token or making gameplay requests. STOP remains in place.

- [Ship navigation](https://docs.spacetraders.io/game-concepts/ship-navigation),
  including its embedded page content: CRUISE uses normal fuel and speed; BURN
  uses more fuel and is faster; STEALTH uses **normal fuel** at reduced speed;
  DRIFT uses the least fuel and is much slower. Slowing BURN to CRUISE can save
  fuel. Slowing CRUISE to STEALTH has no documented fuel benefit.
- [OpenAPI 2.3.0](https://github.com/SpaceTradersAPI/api-docs/blob/45fbb04130aca3fa0bd9a634ab77b35fa6c468ab/reference/SpaceTraders.json),
  current upstream main `45fbb04130aca3fa0bd9a634ab77b35fa6c468ab`:
  `refuel` requires docking at a MARKETPLACE selling fuel; one market unit
  replenishes 100 tank units. Omitting `units` fills the tank. `fromCargo` is
  supported by the API but is not used by this planner.
- `get-market` says detailed prices require a ship present. Advertised exports
  or exchange goods alone do not provide a usable fuel price. A positive FUEL
  tradeGood quote is accepted even at an exchange; exchange-only data is not.
- Upstream `ShipNavFlightMode` lists all four modes but provides no numerical
  multipliers. `ShipFuel.consumed.amount` reports actual consumption after an
  action, not a preflight estimate.

These sources do **not** specify exact distance rounding, numerical mode fuel
multipliers or travel-time formulas. The existing CRUISE estimate remains
`d = max(1, ceil(hypot(dx, dy)))`; this is a planning assumption, not a newly
verified server formula. We do not invent STEALTH savings or enable mode
switching. Actual fuel/arrival responses remain authoritative. BURN, STEALTH,
DRIFT, jump and warp remain blocked in automation navigation.

## Inspectable Rules

`auto move SHIP DESTINATION` now returns a GET-only fuel plan rather than
stopping at the first would-be mutation. It is not an offline command: it needs
fresh observations and obeys STOP. Execution recomputes the plan and stores it
under `move:SHIP` in scoped observations before any orbit/navigation mutation.
No new configuration switch is necessary.

1. Preserve the existing same-system CRUISE rule, fuel-free probes and carried
   reserve of `2*d + 10`. Sufficient carried reserve needs no destination quote.
2. Otherwise require current fuel of at least `d + max(10, ceil(d*0.10))`.
   This keeps a route-specific margin rather than permitting an empty arrival.
3. Require the destination's fresh MARKETPLACE trait and a direct market GET
   with matching symbol and positive FUEL purchase price and trade volume.
   Stored prices, even recently stored ones, never substitute for that GET.
   Missing/sparse/stale evidence preserves the conservative refusal.
4. Refresh agent/fleet/contracts. Accepted unfulfilled contracts, open positions
   and pending actions block the exception: their obligations are not safely
   costed here. No anticipated payout or cargo sale finances recovery.
5. Protect
   `50,000 + 1,000 + ceil(tank_capacity/100)*ceil(ceil(fuel_price*1.20)*1.20)`
   credits. The first margin allows a 20% destination quote rise; the second
   funds the existing refuel guard's own 20% headroom at that higher quote.
   Reserving a full tank also covers underestimated consumption and leaves the
   existing fuel allowance untouched. This is a preflight budget, not an escrow
   or a server-enforced price limit. Other spending requires fresh guards.
6. Expire the quote after 60 seconds during planning and check it again after
   orbit, before handing navigation to the transport. Existing STOP, budgets,
   allowlist and uncertain-action journal apply unchanged.

Example: a 300-unit leg with a 400-unit full tank used to require 610 units.
With verified destination fuel at 100 credits per market unit, the exception
requires 330 tank units and at least 51,576 credits. It does not need the return
fuel aboard because a full destination refill is funded.

## Recovery And Limits

After confirmed arrival, deliberately run `auto refuel SHIP` to inspect the
fresh refill plan, then its `--execute` form when authorized. That existing
workflow rechecks credits/obligations and current fuel price, docks, journals
refueling, and refreshes the ship. Navigation itself does not spend the reserved
credits or automatically refuel. If interrupted, observe the ship at its actual
waypoint and use this same refill workflow; reconcile pending actions first.

This is a credible **destination-refueling** recovery, not a guarantee against
market changes. Prices can rise beyond 20%, fuel service can become unavailable,
and STOP or a transport wait can outlast the quote check. Stop at the destination
and review if refueling cannot pass its guards; do not silently DRIFT, spend the
floor, use protected cargo, or replay an uncertain refuel. There is no independent
rescue ship or alternative fuel-source guarantee in this increment.

Each onward/return leg must pass its own guard. A remote return may need a scout
to expose a fresh origin fuel quote; this is not unrestricted round-trip travel.
Trading/fleet selection retains its three-leg entry reserve and open-position
recovery rules. Remote single-load procurement now separately budgets all goods
and a full verified destination refill. It requires carried fuel sufficient for
the existing delivery-leg round-trip guard before acceptance/purchase; it does
not bypass the active-contract restriction on the one-way exception. This is a
single delivery followed by a funded refill, not an unbounded sequence of strict
round trips. Acquisition begins only at the source with a destination probe.
Repositioning and post-fulfillment refill use their existing guarded commands.
No flight-mode optimization or active-contract refuel is enabled.

Offline tests cover a long one-way leg followed by the existing guarded refill
with real Session journaling; reserve boundaries; missing, sparse, stale and
expired quotes; exchange-only versus priced exchange fuel; zero prices/volume;
contracts/positions/pending actions; route margin; CLI dry-run output; quote
expiry after orbit; and existing no-cross-system/no-DRIFT/mode guards. No live
travel, refuel or flight-mode mutation was performed.

Offline recovery regressions also cover destination prices rising by 10% and
20%, integer price rounding and an unexpectedly empty arrival tank. The funded
refill passes its unchanged guard without relying on new income. This does not
guarantee arrival if actual consumption exceeds carried fuel, fuel availability,
or recovery after prices exceed the planned ceiling. Remote procurement's
separate goods/refill budget is unchanged; its refill follows fulfillment.
