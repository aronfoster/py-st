# Beyond the Home System

## Intent and Scope

Owner direction: flesh out home-system trading first, understand combat if it
exists, then repair/complete the jumpgate and explore other systems, where we
may encounter other players. This is a phased plan, not permission to travel now.

Research checked public official documentation and upstream OpenAPI read-only
on **2026-09-08 UTC**. No game API calls, credentials, live ledger access or
state mutations were used. Published endpoint coverage is not live behavior
verification. Local context: `AGENTS.md`, `ROADMAP.md`, `ASTRA_LOG.md`,
`HANDOFF.md` and the vendored `src/py_st/_generated/reference/SpaceTraders.json`.

**Preserve the existing FOS-63 live jump/warp guard.** Neither this document nor
an existing manual CLI command relaxes it. Cross-system actions stay disabled
until needed, behavior is tested, and the particular bounded experiment is
authorized under the ticket; resolve any conflict with the explicit run ban
before dispatch. No allowlist, STOP, code or runtime-state changes here.

## Combat and Players

- **Combat is planned, not a currently documented callable capability.** The
  official roadmap lists asynchronous player/NPC combat as future work, with
  dedicated combat sectors or a PVP flag described only as possibilities. It
  also lists piracy/patrolling and faction warfare as future features [1].
- Upstream OpenAPI reports version **2.3.0** and exposes no combat/attack
  operation [2]. Weapon names, military ship descriptions, factions, ship wear
  or a scanning operation do not establish implemented ship-to-ship combat.
  Do not invent attack, escort, defense or PVP-toggle workflows. Recheck official
  releases/spec before implementing any combat behavior; no release date is
  established by these sources.
- **Multiplayer economic competition already exists.** The official site
  describes competing with other players for routes and credits, and a universe
  driven by player activity and cooperation [3]. This is distinct from combat;
  other players need not wait for us to leave the home system to affect markets.
- `GET /agents` and `GET /agents/{agentSymbol}` expose public agent details;
  `GET /` includes leaderboards. These are not a nearby-player radar or access
  to another agent's private fleet. `GET /my/ships` lists our own ships [2].
- `POST /my/ships/{shipSymbol}/scan/ships` documents nearby ships in range,
  requires a Sensor Array mount, and creates a cooldown. Returned scanned
  details include symbol, registration and navigation, with limited hardware
  information [2, 7]. It is a mutation, not a read-only discovery GET, and was
  not exercised here. Presence is a possible encounter, not an attack or a
  guarantee that another player will be nearby on arrival.

## Jumpgate Construction

Treat the owner's "repair jumpgate" goal as **completing construction**, if
fresh waypoint data says it is under construction. Do not confuse this with
the ship repair endpoint or assume the home gate is currently unfinished.

1. Locate `JUMP_GATE` waypoints with system waypoint GETs. Inspect the waypoint
   and `GET /systems/{systemSymbol}/waypoints/{waypointSymbol}/jump-gate` for
   the actual connected gate waypoint symbols [2, 6].
2. When `isUnderConstruction` is true, read the corresponding `/construction`.
   Its `materials` contain `tradeSymbol`, `required` and `fulfilled`; remaining
   demand is `max(0, required - fulfilled)` for each item. `isComplete` records
   completion [2, 5]. These responses, not a hard-coded recipe, determine the
   supply list. No current home-gate material quantities, prices or completion
   status were fetched in this task.
3. Cost sourcing and hauling every outstanding material, including cargo
   capacity, market volume, price changes, fuel, travel time and obligations.
   Refresh demand before buying and supplying: shared progress may change.
   Do not assume construction payments, exclusive ownership or guaranteed ROI;
   the supply response documents construction and cargo, not a payout [2].
4. The documented mutation is `POST .../construction/supply` with `shipSymbol`,
   `tradeSymbol`, and `units`. The site must be under construction and the goods
   must already be in that ship's cargo; supplying removes them from cargo [2].
   Plan to deliver at the site. Exact docking/location rejection behavior is
   not specified in that operation's prose and remains a validation item, not
   a claimed tested prerequisite. Bound units by fresh remaining demand and
   available non-contract cargo; reconcile cargo/site after uncertain outcomes.
5. Refresh completion and both ends of the proposed gate connection before
   planning travel. Treat unfinished/unknown gate readiness as a planner stop;
   exact source/destination construction restrictions need current evidence
   and tests before an execution path is enabled.

## Travel Prerequisites

| Action | Published requirements and effects | Planning consequence |
| --- | --- | --- |
| Navigate | In orbit; destination waypoint in the same system; fuel and arrival time [2]. | Existing same-system scouting is not cross-system exploration. |
| Jump | In orbit at a gate, to a connected gate waypoint; instantaneous, followed by cooldown. One antimatter unit is automatically bought and consumed at the gate's variable market price [2, 4, 6]. | Inspect connections, gate readiness, cooldown and current jump cost; budget outbound and return costs. Do not invent a carried-antimatter or jump-drive requirement for gate travel. |
| Warp | In orbit; installed Warp Drive module; target waypoint in another system; consumes normal ship fuel and takes time [2, 4]. | Validate actual ship capabilities, route fuel, arrival and a viable refuel/return plan. Gate completion is not the documented prerequisite for warp. |

The navigation guide's example jump/warp bodies use `systemSymbol`, whereas
the current upstream OpenAPI requires **`waypointSymbol`** for both [2, 4]. Use
the current schema for implementation and flag the documentation discrepancy;
do not copy the older examples or claim either payload was live-tested here.
Faction-reputation gate restrictions are labeled **Future** in that guide [4].

Do not assume a fuel-free local probe can warp, or reuse local navigation's
fuel formula for warp without evidence. Check cooldown and fresh nav before
dispatch, and reconcile returned nav/cooldown/transaction/agent for jump or
nav/fuel/arrival for warp. Keep destination-market visibility separate from
advertisements: detailed prices require ship presence [2].

## Phased Roadmap

1. **Home-system economics first.** Improve local quote coverage, repeatable
   trading/repositioning, and costed procurement/mining where useful. Verify
   offline safety/recovery cases and bounded authorized live economics before
   diverting capital to exploration. Existing scouting has live proof; the
   earning controller's documented offline proof is not new live earnings.
2. **Capability and route assessment, read-only first.** Refresh official combat
   status, inspect gate connections/construction and actual ship capabilities,
   and price a supply/return route. Exit with sourced prerequisites, explicit
   unknowns, remaining materials and a cost ceiling, not a movement command.
3. **Complete the gate if needed and worthwhile.** Implement/test bounded supply
   planning and reconciliation offline before ticket-authorized deliveries.
   Protect accepted contract cargo and the 50,000-credit floor plus known fuel
   and contract obligations. Verify fresh completion; skip supply if already
   complete. Gate completion alone does not authorize jumping.
4. **One controlled cross-system experiment.** Only after behavior tests, a real
   need, and ticket authorization resolving the live jump/warp ban, consider a
   narrow reviewed guard change for one selected ship/route. Test disconnected
   or unfinished gates, cooldown, insufficient credits/fuel, missing warp drive,
   STOP/deadline interruption and unknown-outcome recovery. Require a costed
   return/refuel option, then verify a bounded authorized trip before expansion.
5. **Wider discovery and player awareness.** Expand system/market observations
   incrementally after travel proof; public agents and any separately tested,
   authorized sensor scans inform awareness, not combat. Reuse reset-scoped
   observations, single-writer lock, action/time bounds and the mutation journal.
   Stop on 401/4113; never register or blindly replay an uncertain action.

## Evidence

All URLs below were fetched read-only on **2026-09-08 UTC**. The official
roadmap/navigation Markdown extraction omitted article bodies; the HTML
responses include their text in the embedded page data, which was inspected.
These are mutable upstream sources, not promises about future releases.

| Ref | Official source | Evidence used |
| --- | --- | --- |
| [1] | https://docs.spacetraders.io/roadmap | Future combat, piracy/patrolling and faction warfare; tentative PVP design. |
| [2] | https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/reference/SpaceTraders.json | OpenAPI 2.3.0 operations, payloads, supply/travel/scanning/public visibility; no combat endpoint. |
| [3] | https://docs.spacetraders.io | Multiplayer route/credit competition and cooperation. |
| [4] | https://docs.spacetraders.io/game-concepts/ship-navigation | Gate versus warp mechanics, cooldown, antimatter, future reputation restrictions; stale example field names. |
| [5] | https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/models/Construction.json and https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/models/ConstructionMaterial.json | Completion and per-material required/fulfilled units; no fixed recipe. |
| [6] | https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/models/JumpGate.json | Connected gate waypoint symbols. |
| [7] | https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/models/ScannedShip.json | Limited detected ship information. |
