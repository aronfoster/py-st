# Mining and Contract Assessment

## Remote Live Completion

**2026-09-08, implementation `1bb3a78`, committed before live trial.** The
EQUIPMENT offer `cmts1w1oni5liuo6x08fsx690` is now **accepted and fulfilled,
26/26 delivered to C45**. This supersedes the unaccepted scouting checkpoints.

Fresh locked observation at 03:21:01 UTC confirmed the reported 397,940 balance,
empty cargo, 111 prior successes and no pending/open exposure. Coordinates:
A4 (-2,24), E52 (56,0), C45 (38,-149). Both repositionings had explicit GET-only
dry runs before guarded execution. Hauler A4->E52 used 63 fuel and 59 seconds;
probe E52->C45 used zero fuel and 432 seconds. Hauler retained 337 fuel at E52.

At the fresh contract dry run, E52 EQUIPMENT was 2,076, volume 20, and C45 FUEL
72, volume 180. Complete plan: 20+6 acquisition, 26/40 cargo, delivery leg 151
estimated fuel with 312 carried reserve, 186 estimated travel seconds, one-hour
acquisition contingency and valid acceptance/delivery deadlines. Goods ceiling
2,492; fuel ceiling 87; full-tank reserve 348; floor 50,000 + allowance 1,000 +
goods 64,792 + refill 348 = **116,140 protected credits**. Conservative net
**87,598** after goods ceiling, refill and allowance. No future payout funds
the reserve. C45 local sourcing remained unprofitable at 6,664/unit.

| Journal | Confirmed Effect |
| --- | --- |
| 112-113 | Hauler orbit and A4->E52; 400->337 fuel |
| 114 | Fuel-free probe E52->C45 |
| 115 | Accept at 03:30:49 UTC; +39,972 |
| 116 | Dock at E52 |
| 117 | Buy 20 EQUIPMENT at 2,076 = 41,520 |
| 118 | Fresh repriced batch: buy 6 at 2,195 = 13,170 |
| 119-120 | Orbit and delivery flight; 337->187 fuel, 120 seconds |
| 121-122 | Dock at C45 and deliver all 26 at 03:33:24 UTC |
| 123 | Fulfill at 03:33:28 UTC; +113,766 |
| 124 | Guarded full refill after its dry run; 3 packs at 72 = 216 |

The contract service used **9 of 12 permitted actions** within its 600-second
bound. No interruption/replay was needed live; recovery proof is offline.
Actual second-batch price stayed below the persisted ceiling. Lowest observed
balance after acquisition was 383,222, comfortably above all protected reserves.
The delivery leg consumed 150, one less than the conservative distance estimate.
Full refill restored all 213 fuel consumed by both hauler legs; no cargo remains.

**153,738 - 54,690 - 216 = 98,832 realized credits gained**, including approach
and delivery fuel restoration. Final fresh 03:34:08 observation: **496,772**,
both ships at C45, hauler DOCKED CRUISE fuel 400/400 cargo 0/40; probe IN_ORBIT
CRUISE fuel/cargo 0/0. Both contracts fulfilled, position closed, 124 succeeded
actions, no pending/open exposure, zero unexplained cash. Cumulative cash gain
**321,772**; this is cash profit, not a valuation of wear or opportunity cost.

STOP restored exactly. Unique `.state/remote-contract-124-1bb3a78.sqlite3`
backup integrity `ok`, 124 successes and identical reconciliation. Prior backups
preserved. Pre/post-live full offline CI: **470 passed, 1 skipped**, clean
Black/Ruff/mypy. No live pytest, new offer, extraction, prohibited travel,
registration, ship purchase, paid/system changes or push.

## Remote Single-Load Implementation

The former blanket remote-source refusal below is superseded by a tested
`auto contract SHIP CONTRACT --source SOURCE` workflow. Before acceptance the
hauler must be at the source, a stationary fuel-free probe must independently
expose destination prices, the complete remaining load must fit, and carried
fuel must pass the unchanged delivery-leg guard. Every acquisition iteration
refreshes obligations, cargo, goods price/volume and destination fuel. The
original goods and fuel price ceilings survive restarts in a scoped position.
The 50,000 floor, 1,000 allowance, remaining goods and a full destination tank
are separately budgeted. No future payout finances that reserve.

Execution aggregates source batches before departing, delivers, then fulfills.
Observed cargo/progress, not a replayed stage flag, drives recovery. Completed
acquisition needs no source quote; completed deliveries need no market quote.
Uncertain actions remain blocked. Post-fulfillment refill is deliberately a
separate guarded `auto refuel` dry run/execution; no automatic return is claimed.
Same-market procurement remains unchanged. See OPERATIONS and FUEL_NAVIGATION.

Pre-live offline verification: **470 passed, 1 skipped**, Black/Ruff/mypy clean
(152 checked files). Includes real Session/journal fake-API recovery tests.
No live result is implied by these tests; dated scouting below remains evidence.

## C45 and E52 Live Scouting

**Historical scouting checkpoint: 2026-09-08 03:04:53 UTC, source `c5b357e`.**
The completed contract above supersedes this then-unaccepted offer state. This
checkpoint superseded the earlier unpriced-market assessment and scouting plan.
Read the updated `Session.navigation_plan` and
[Refueling-Aware Navigation](FUEL_NAVIGATION.md) before planning travel; the
earlier blanket round-trip-only analysis is historical, not the current rule.

Fresh 02:48:13 reads confirmed 397,940 credits, 109 succeeded actions, no pending
actions/open trade positions, command ship docked A4 with 400/400 fuel, probe in
orbit D47 and the unaccepted 26-EQUIPMENT offer unchanged. With STOP deliberately
cleared, each probe leg had its own GET-only `auto move` dry run followed by
guarded execution with `--seconds 600 --actions 2`. Both plans were feasible,
fuel-free CRUISE. Each used one navigation mutation, no orbit or spending:

| Action | Probe Leg | Departure UTC | Arrival UTC | Travel |
| --- | --- | --- | --- | --- |
| 110 | D47 -> C45 | 02:48:39.731 | 02:55:42.731 | 423 seconds |
| 111 | C45 -> E52 | 02:56:36.088 | 03:03:48.088 | 432 seconds |

Arrival was confirmed by GET before observing each market. These were explicit
`auto move` visits, not additional `auto scout` visit records. Detailed-price
history now covers 13 markets, up from 11; old observations are not fresh quotes.

### Prices and Decision

| Market | EQUIPMENT Buy / Sell | Volume | FUEL Buy / Sell | Fuel Volume |
| --- | --- | ---: | --- | ---: |
| C45, delivery/import | 6,664 / 3,231 | 20 | 72 / 68 | 180 |
| E52, exporter | 2,076 / 990 | 20 | 72 / 68 | 180 |

Fuel is a priced EXCHANGE good at both, not merely an advertisement, and one
market fuel unit represents 100 tank units. C45 goods/fuel were observed after
02:55 arrival. E52 prices were observed after 03:03 arrival and rechecked in the
final GET session. **A final C45 GET after the probe left returned no detailed
prices**: its recorded 72-credit fuel quote is now historical and cannot authorize
the new destination-refuel exception. Refresh it with a ship present when needed.

The existing same-market procurement dry run at C45 returned:

- Goods cost: `26 * 6,664 = 173,264`; payout 153,738; **loss 19,526 before fuel**.
- 20% price ceiling: 7,997/unit; conservative goods budget 207,922.
- With the 1,000 fuel allowance: **conservative net -55,184**, reserve after
  acquisition 189,018, **feasible false**. Do not execute this acquisition route.

The E52 goods-only assessment using the existing `contract_plan` and a fresh
GET quote returned:

- Goods cost: `26 * 2,076 = 53,976`; **potential net 99,762 before fuel**.
- 20% price ceiling: 2,492/unit; conservative goods budget 64,792.
- With the 1,000 fuel allowance: **potential conservative net 87,946** and
  reserve after acquisition 332,148. These are estimates, not earnings.
- At volume 20, acquiring all 26 needs at least two purchases, 20 + 6, with
  fresh repricing and cargo/obligation checks between them. The full load fits
  the command ship's 40-unit hold; unchanged second-batch prices are not assured.

**The remote execution workflow is still unsupported.** The explicit existing
`auto contract SOURCE_CODE-1 cmts1w1oni5liuo6x08fsx690 --source X1-CY22-E52
--seconds 120` dry run stopped with **"Remote procurement needs a full multi-leg
fuel plan"**, before acceptance or spending. A goods-only `feasible: true` does
not override this route guard. No contract was accepted, no goods bought, and
the hauler did not move. The new navigation exception does not implement remote
contract procurement or cost its accepted obligations.

### Fuel and Next Work

Under the existing ceil-distance planning assumption, A4 -> E52 is 63 fuel,
leaving 337, and E52 -> C45 is 151, leaving 186. The respective carried-return
guards are 136 and 312, so these outward legs fit without using the new exception.
Actual game fuel consumption must still be observed and rechecked at each leg.

A direct C45 -> A4 return needs 178 + 18 margin = 196 under the new one-way
policy, so the projected 186 is insufficient even with visible destination fuel.
Plan a C45 refill after delivery/fulfillment instead of bypassing the guard.
At the observed 72 price, reserving a full 400-unit tank with 20% price allowance
is `4 * ceil(72 * 1.2) = 348` credits, within the 1,000 fuel budget. This is a
cost estimate based on a dated quote, not a future price guarantee. Existing
`auto refuel` refuses uncosted active contracts; complete delivery/fulfillment
first, then refresh C45 fuel and use its guarded dry-run/execution when allowed.
No one-way hauler navigation or live refill was tested in this pass.

Next implement and test **remote single-good procurement with aggregated cargo**:
fresh source/destination prices, source 20+6 purchase batches, full-trip fuel
and destination-refill reserve, deadlines, protected obligations and restart
recovery after accept/buy/travel/deliver/fulfill. Never reinterpret the current
same-market loop or manually string together actions to evade its guard.
The probe is already at E52 for fresh source-price visibility. Re-observe both
ends and rerun a supported full plan before accepting; the deadline remains
**2026-09-09 02:28:45.572 UTC**, with delivery by Sep 15 at that time.

### State and Accounting

At 03:04:53 UTC: **397,940 credits**, **111 succeeded actions**, no pending
actions or open trade positions, zero unexplained cash changes. Command ship
SOURCE_CODE-1: A4, DOCKED, CRUISE, fuel 400/400, cargo 0/40. Probe SOURCE_CODE-2:
E52, IN_ORBIT, CRUISE, fuel 0/0, cargo 0/0. EQUIPMENT contract remains unaccepted,
unfulfilled, delivered 0/26. This pass earned/spent **zero credits** and consumed
zero fuel. STOP is restored with its original text. New consistent backup
`.state/contract-scout-111.sqlite3` passes integrity `ok`; prior backups preserved.

Rechecked original contract accounting against journal actions 5 (accept), 11
(fulfill), the ore purchases and 12 (first refill):
**1,678 + 11,236 - 8,812 = 4,102** credits, then **4,102 - 72 = 4,030** after
restoring fuel. Do not omit the acceptance payment. Cumulative realized net
cash remains **+222,940**, not the new offer's projected profit.

Full offline checks on `c5b357e`: **437 passed, 1 skipped**, Black/Ruff/mypy clean
(150 source files). No source code, allowlist or guard changes in this live pass.
No registration, mode change, ship purchase, extraction, jump/warp/DRIFT, paid
services, security changes or push. Active investigation, not completed contract.

## Guarded Negotiation

Existing FOS-63 authority covers legal guarded negotiation. No additional owner
authorization is required to request one offer in this task. The earlier
assessment's request for separate authorization was overly restrictive; the
actual safety concern is duplicate offers or uncertain mutation outcomes.
Acceptance, purchasing, travel and extraction are outside this task's live scope.

`auto negotiate SHIP` is now the guarded alternative to the manual command:

```sh
export PATH="$PWD/../../.venv/bin:$PATH"
export PYTHONPATH=src
# Deliberately clear the known handoff STOP before live reads.
python -m py_st auto negotiate SOURCE_CODE-1 --seconds 120
# After inspecting the fresh dry-run plan, request ONE offer:
python -m py_st auto negotiate SOURCE_CODE-1 --execute --seconds 120
```

The dry run uses GETs and writes local observations/plan, not a game mutation.
Both modes acquire the shared lock and refresh agent, fleet, all contracts and
the ship's current waypoint. Full ship symbols are required. Faction presence
and room under the documented one-offered/ongoing-contract limit are checked.
DOCKED and IN_ORBIT are both permitted; IN_TRANSIT is conservatively refused,
with no automatic arrival wait or navigation. Cooldown is shown but not treated
as a documented negotiation prerequisite. Server-side rejection is authoritative.
All unfulfilled contracts, including expired offers, conservatively block a new
request until reviewed; this is a client policy, not an asserted server expiry
rule. No funds, cargo or fuel are spent, and the command never accepts the offer.

Execution has a fixed one-action budget and sends at most one negotiation POST.
Only `/my/ships/SHIP/negotiate/contract` was added to the narrow Session allowlist.
Unlike other endpoints, negotiation does not retry even cooldown/429 rejection.
Normal 4xx rejections are journaled as rejected; timeouts, 5xx, malformed success
responses and uncertain interruptions stay pending. Restart observes fresh state
but will not POST with any pending action, even if an offer becomes visible.
Use the existing evidence-based `auto reconcile` flow; never blindly replay.

A valid offer is recorded both in the action receipt and scoped contract
observations, then refreshed with the account/fleet/contracts for consistency.
A successful receipt missing from the fresh contract list blocks a new request,
including interruption before the contract observation was persisted. Existing
unfulfilled offers block duplicate negotiation on restart; a confirmed fulfilled
contract permits a later deliberate invocation. No claims of exactly-once
delivery across network failures or parallel external/manual gameplay are made.

Implementation commit **`fee75e9`** passed full offline checks before any live
negotiation: **418 passed, 1 skipped**, Black/Ruff/mypy clean (149 source files).
Measured live results below are separate from that offline verification.

## Live Offer

On **2026-09-08 at 02:28:45 UTC**, after a fresh eligible dry run, exactly one
bounded execution on SOURCE_CODE-1 at A4 succeeded. Journal action **109**:
`/my/ships/SOURCE_CODE-1/negotiate/contract`, started 02:28:44.910351 UTC,
finished 02:28:45.659950 UTC. The validated offer response was persisted and
confirmed by fresh contract reads. No acceptance occurred.

Raw nonsecret offer terms:

```json
{
  "id": "cmts1w1oni5liuo6x08fsx690",
  "factionSymbol": "DOMINION",
  "type": "PROCUREMENT",
  "terms": {
    "deadline": "2026-09-15T02:28:45.572Z",
    "payment": {"onAccepted": 39972, "onFulfilled": 113766},
    "deliver": [{
      "tradeSymbol": "EQUIPMENT",
      "destinationSymbol": "X1-CY22-C45",
      "unitsRequired": 26,
      "unitsFulfilled": 0
    }]
  },
  "accepted": false,
  "fulfilled": false,
  "expiration": "2026-09-09T02:28:45.572Z",
  "deadlineToAccept": "2026-09-09T02:28:45.572Z"
}
```

Total potential receipts are **153,738 credits**, none received yet. All 26
units fit in the command ship's empty 40-unit hold. EQUIPMENT is the delivery
good, not an ore target for direct mining. The acceptance deadline is the next
day; inspect fresh terms again before any later decision.

### Economic Assessment

A separate locked 240-second GET-only Session, additionally protected by a
non-GET-rejecting HTTP hook, refreshed all 94 local waypoints and 26 advertised
markets, completing at **02:30:18 UTC**. Only occupied markets supplied detailed
current quotes. Historical detailed quotes were not substituted for missing
current prices.

| Acquisition | Fresh EQUIPMENT Price | Route / Decision |
| --- | ---: | --- |
| D47, import | 6,758 purchase, volume 20 | Reject: 175,708 goods cost exceeds payout by 21,970 before fuel |
| C45, import/delivery | Not visible | Best first price-scout target; supported same-market procurement if profitable |
| A1, import | Not visible | Near A4, but remote procurement would need a costed multi-leg workflow |
| E52, export | Not visible | Promising source advertisement, not a priced profitable route |
| K93, export | Not visible | Direct delivery leg fails full-tank round-trip guard |
| J64, import | Not visible | Outside safe direct approach range |

D47 would need at least two purchases (20 + 6 at the observed volume), so even
the 175,708 figure assumes an unchanged second-batch quote. The existing goods
planner's 20% price ceiling is 8,110/unit; with its 1,000 fuel allowance the
conservative net is **-58,122** and feasibility is false. Credit liquidity is
adequate, but that does not turn a loss into a good contract. This was an offline
evaluation of fresh quotes, not execution or support for remote procurement.

Without fuel, break-even is exactly 5,913/unit. With the existing 1,000-credit
fuel allowance, strictly positive nominal net needs less than 5,874.54/unit.
The existing procurement planner additionally budgets 20% acquisition slippage:
the highest integer observed quote passing its strict positive-net test is
**4,895/unit** (ceiling 5,874, conservative net only 14). Prefer a meaningful
margin rather than accepting at this theoretical limit. Preserve at least
50,000 credits plus remaining goods and fuel obligations.

Distances below use the existing conservative ceil-distance CRUISE planner,
not new measured navigation or fuel consumption:

- **Direct A4 -> C45:** 178 fuel; outbound `2 * 178 + 10 = 366` guard passes
  with 400. Source equals destination, so no extra navigation is needed for
  delivery. Physical return plus 10 margin also totals 366, but the existing
  Session rechecks *round-trip* fuel at every departure: returning from C45
  after arrival with 222 requires topping up to at least 366 (144 extra fuel).
  C45 advertises FUEL, but its price is not visible. Cost that refill explicitly
  if a return is part of the chosen plan; do not force a guard bypass.
- **A4 -> E52 -> C45:** 63 + 151. Arrival at E52 leaves 337, enough for the
  312 delivery-leg round-trip guard; arrival at C45 would leave 186. Physical
  return to A4 adds 178, leaving only 8 without refueling. The guarded return
  requires at least 180 extra fuel at C45 (to reach 366). Both E52 and C45
  advertise FUEL, but neither has a current visible fuel price. Remote source
  procurement is not yet supported by `auto contract`.
- **Via D47:** 100 + 148 + 178 = 426 fuel before margin; refueling is needed.
  Even arriving at D47 with 300 fails the 306 guard for the delivery departure.
  D47 fuel is currently 72 credits per 100-unit pack, but its goods price already
  disqualifies the route. A4 also has a current fuel quote of 72 per pack.
- **K93 -> C45:** 227, requiring 464 fuel under the direct round-trip guard,
  exceeding full capacity. A staged route would need separate planning.

No goods price can be claimed for C45/E52/K93 from the read-only scan. A fresh
`auto contract SOURCE_CODE-1 cmts1w1oni5liuo6x08fsx690 --seconds 120` dry run
correctly stopped with **"No live acquisition price; scout source first"**.
Another negotiation dry run saw the new offer and returned `eligible: false`;
no second execution was attempted.

### Initial Next Steps (Superseded)

1. Leave the offer unaccepted. In the next guarded gameplay increment, refresh
   state and deliberately clear STOP, then price-scout **C45 with the probe**.
   For example, `auto move SOURCE_CODE-2 X1-CY22-C45 --execute --seconds 600 --actions 2`
   uses the existing fuel-free probe and fetches the arrival market. This move
   was **not run** in this task.
2. Rerun the procurement dry run for the exact offer ID. If C45 provides a
   meaningful conservative margin, current fuel pricing and sufficient volume,
   a reviewed same-market procurement can fit all goods in one cargo load.
   Before execution, budget any intended return refill as described above.
3. If C45 is uneconomic, scout E52 next and evaluate its fresh quote and staged
   fuel costs. Do not accept a remote-source contract until an appropriate
   tested multi-leg workflow exists. K93 needs additional route staging.
4. If no positive, fuel-safe plan is available before the acceptance deadline,
   leave the offer unaccepted. Never negotiate blindly to replace it or count
   the displayed payout as earned credits.

Final observed balance remains **397,940**, with **109 successful journal
actions**, no pending actions or open trade positions, and zero unexplained
credit change. Original net cash gain remains +222,940. Ships stayed at A4/D47,
with unchanged fuel and empty cargo. STOP is restored exactly. New consistent
backup **`.state/negotiation-109.sqlite3`** has integrity `ok`, 109 successful
actions and the unaccepted offer; neither prior handoff backup was overwritten.
No acceptance, purchases, movement, extraction, registration, paid services,
security changes or pushes occurred. This remains an active overnight checkpoint.

## Initial Evidence

Read-only inspection on **2026-09-08, 02:15:38-02:15:47 UTC**, starting from
`524a9d7`, under FOS-63. This is an active overnight investigation checkpoint,
not a new final handoff or a claim of extraction execution.

The session acquired the existing automation lock, used a 180-second deadline,
`execute=False`, and an HTTP request hook rejecting every non-GET method.
It fetched status, agent, all ships/contracts, all local waypoints and the two
occupied markets. Observations went to a separate temporary database, not the
authoritative ledger or either backup. STOP was deliberately cleared for these
reads and restored with its original text immediately afterward. No negotiation,
acceptance, navigation, survey, extraction, purchases or other mutations occurred.

| Observation | Current Value |
| --- | --- |
| Scope | `2026-09-06:SOURCE_CODE` |
| Credits | 397,940, unchanged |
| Command ship | `SOURCE_CODE-1`, `FRAME_FRIGATE`, `X1-CY22-A4` |
| Navigation | DOCKED, CRUISE; A4 is an ORBITAL_STATION |
| Cargo / fuel | 0/40 cargo; 400/400 fuel |
| Cooldown | 0 seconds remaining |
| Mounts | Sensor Array II, Gas Siphon II, Mining Laser II, Surveyor II |
| Mining laser | `MOUNT_MINING_LASER_II`, strength 5 |
| Crew / power | 57/57 required crew; 29 listed power requirements / 31 output |
| Probe | `SOURCE_CODE-2`, in orbit at D47 (PLANET), no mounts, cargo capacity 0 |
| Contracts | Exactly one returned, accepted and fulfilled |

The contract is `cmtrut8bshndysl6zz0r37gy0`: 57/57 ALUMINUM_ORE delivered
to H57, payment 1,678 on acceptance plus 11,236 on fulfillment. At this initial
02:15 inspection there was no offered or outstanding contract. The 02:28 offer
above supersedes that contract-list snapshot.

## Mining Diagnosis

### Read-Only Diagnostic Command

`PYTHONPATH=src python -m py_st auto mining SHIP --seconds 120` uses a full
ship symbol and a non-executing Session (the required minimum action budget
is one, unused). It honors the existing
lock, STOP and deadline; do not clear STOP or interrupt another Session just
to inspect mining. There is no `--execute` option. It refreshes account/fleet/
contracts, then GETs the individual ship and its current waypoint, without
arrival waiting, orbiting, surveying or extraction. Session observations can
write local SQLite; GET-only refers to gameplay, not filesystem read-only.
The mutation allowlist is unchanged. This command was tested offline only.

The pure `services/mining.py:diagnose_mining` accepts supplied ship/waypoint
snapshots and an explicit clock. It reports orbit, location, missing ore laser,
storage capacity and reported cooldown blockers separately from unknowns.
Positive remaining cooldown is not silently cleared by a stale expiration;
conflicting times and invalid/naive timezone dates produce unknowns.

Evidence is the checked-in generated `reference/SpaceTraders.json` extraction
description (line 1972), cooldown GET description (1821), and `models/ShipMount`,
`ShipCargo`, `Cooldown`, `WaypointType`, and `ShipRequirements` schemas. The
client's `ShipsEndpoint.extract_resources` already distinguishes unsurveyed
`/extract` from the full signed-survey `/extract/survey` POST. Neither is called.

Unlike the stronger historical location diagnosis below, this deliberately
spec-limited report does **not** assert an exhaustive non-extractable type list:
the spec names asteroid fields as an extractable example but supplies no
complete type/trait eligibility matrix. Stations, ordinary/engineered asteroids
and asteroid bases therefore retain unknown extractability, not automatic
permission. STRIPPED in traits or modifiers is reported separately as a depletion
warning, never converted into non-extractability, zero yield or an error code.
All resource traits/descriptions are preserved without inventing yield rules.
Full cargo proves no storage space, not a documented rejection code. Crew/power
allocation, actual acceptance, yield, economics and the owner's original failure
remain unestablished. Every report has `execution_authorized: false`.

**Mining is supported by the current published game API and by this client.**
Fresh upstream OpenAPI 2.3.0 documents POST `/my/ships/{shipSymbol}/extract`
and `/extract/survey`. The former requires an extractable waypoint, orbit and
appropriate mining equipment. The latter accepts the complete signed survey
object, not a nested `survey` property. The existing endpoint implementation
uses these two paths and payload shapes correctly. No live extraction was sent,
so server acceptance, yields, timing and profitability are not experimentally
verified in this task.

The command ship's **current blockers are location and docking**, not a missing
mining laser. Orbiting at A4 alone will not make an orbital station extractable.
The probe cannot mine with its current configuration. We do not have the owner's
original failed request or error payload, so cannot assign an exact historical
failure code or say which prerequisite their earlier attempt violated.

For ore extraction:

1. Use a ship with an installed Mining Laser and sufficient crew/power.
2. Navigate to an extractable asteroid, confirm arrival and IN_ORBIT. Inspect
   resource traits and modifiers; do not infer mineability from a market or the
   word "asteroid" alone (an ASTEROID_BASE is not automatically a mining site).
3. Have free cargo capacity and no active extraction/survey cooldown. Inspect
   fresh ship state rather than relying on the legacy cached ship listing.
4. Basic `ships extract SHIP` needs no survey and does not create/use one,
   navigate or orbit automatically. Creating surveys requires a Surveyor mount
   and incurs cooldown. This ship already has one. The service/client support a
   supplied survey, but the manual CLI currently exposes no survey-input option.
5. Preserve the server error payload on rejection. Do not blindly repeat an
   ambiguous failure or discard contract cargo. Extraction is stochastic; a
   survey narrows deposits but is not a guarantee of a specific requested ore.

The closest candidate is **X1-CY22-XC5Z**, ENGINEERED_ASTEROID at (-26, -8),
40 units from A4 (-2, 24). It advertises COMMON_METAL_DEPOSITS, MARKETPLACE
and **STRIPPED**, with no modifiers. The returned STRIPPED description says
resources are depleted from over-mining. This is an observed warning, not proof
that a request returns zero yield or a particular error. It needs a deliberately
bounded experiment, not an assumed profitable mining loop.

The nearest ordinary ASTEROID in the returned local list is **B38**, 291 units
away, with COMMON_METAL_DEPOSITS and RADIOACTIVE. Direct round-trip reserve is
`2 * 291 + 10 = 592`, beyond the command ship's 400 fuel capacity. Do not send
it there on a one-way mining experiment. A refueling/staging route needs separate
costing and review. XC5Z's direct round-trip guard is only 90 fuel.

The original service caught `APIError`, printed a reduced message and returned
None; the CLI then exited normally with "Extraction failed or aborted." Commit
`bc94538` already removed that catch and invalidated ship cache on success or
uncertainty. Current `handle_errors` prints the exception and server payload and
exits 1. This increment retains that fix, adds CLI-level regression coverage,
and replaces uninformative extraction help with prerequisites and the manual
safety boundary. It does not add speculative error-code mappings or mining loops.

## Contract Opportunities

Fresh upstream documentation for POST
`/my/ships/{shipSymbol}/negotiate/contract` says there may currently be at most
one offered/ongoing contract, and the ship must be at a waypoint with a faction.
Negotiation creates an **offer**, not acceptance. There is no GET negotiation
preview in this spec. At 02:15, both A4 and D47 reported DOMINION and the sole
contract was fulfilled, making either ship apparently eligible without moving.
The 02:28 success above now verifies negotiation at A4; the new unfulfilled
offer blocks another request.

The client, service and `contracts negotiate SHIP` command already implement
negotiation. **That manual command sends a live POST and bypasses the automation
STOP/journal.** Do not run it as a read-only inspection. At the initial `a1778db`
assessment neither negotiation nor extraction was allowlisted. The new guarded
workflow above adds negotiation only; extraction remains excluded. CLI help
makes the offer/acceptance distinction explicit.

Contracts can make money, but payout alone is not profit. The completed contract
previously produced 12,914 payout minus 8,812 goods purchases = 4,102 cash gain,
or **4,030 after its 72-credit restoring refuel** (retained earlier journal
evidence, not new earnings). The new negotiated terms are assessed above;
compare each offer using:

`acceptance + fulfillment payments - remaining goods cost - fuel - contingency`

Also check acquisition liquidity, units already owned, cargo batches (capacity
40 here), price/volume changes, delivery deadline, travel/cooldown time and
opportunity cost versus trading. Preserve at least 50,000 credits plus all known
goods/fuel obligations. Mining has no goods purchase bill but still costs time,
fuel and wear; random yields/byproducts can make procurement slower than buying.

After negotiation, inspect fresh terms before accepting.
The existing `auto contract SOURCE_CODE-1 NEW_CONTRACT_ID` is a GET-only dry run
(with local observation writes and deliberate STOP clearance), not negotiation.
It only supports single-good acquisition at the delivery market and requires
fresh visible purchase prices. Remote/multi-good contracts require a different
costed plan; do not accept them merely because the displayed payout is large.
Only a profitable supported plan should proceed to explicitly reviewed execution.
`auto earn` does not negotiate and refuses active contract obligations.

## Mining Follow-Up

The proposed one-off negotiation is now complete, not a step to repeat. The
next contract steps are price discovery and economic review above. Mining is
outside this task's live scope and remains an unperformed follow-up experiment.

For mining, first recheck XC5Z's depletion state and cargo disposal markets.
With explicit approval and journal support, a short round-trip visit and **one
basic extraction** can distinguish a working but depleted site from an API
rejection while measuring actual yield/cooldown/events. Stop after that result,
retain cargo and reconcile it; no auto-repeat, survey-first delay, jettison or
profit claim. If XC5Z proves unsuitable, cost a refueling route to an ordinary
asteroid before moving the command ship farther away.

## Sources

- [Upstream OpenAPI](https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/reference/SpaceTraders.json),
  fetched 2026-09-08 02:15 UTC, version 2.3.0; extraction, survey, negotiation
  operation descriptions reviewed (not a full schema audit).
- [Game mining quickstart](https://docs.spacetraders.io/quickstart/mine-asteroids)
  and [resource concepts](https://docs.spacetraders.io/game-concepts/extracting-resources).
  Their fetched text exposed navigation/headings only; detailed prerequisites
  above are grounded in the OpenAPI descriptions and live data, not unseen prose.
- `src/py_st/client/endpoints/ships.py`, `services/ships.py`,
  `cli/ships_cmd.py`, `cli/_errors.py`, and corresponding contracts modules.
- Temporary read-only-inspection observations:
  `/tmp/opencode/astra-mining-observations.sqlite3`; disposable, not the live
  journal and not a replacement for either preserved handoff backup.
