# Browser UI foundation — FOS-72

## Checkpoint and evidence

Design checkpoint: 2026-09-11, before shell changes. Canonical requirements:
FOS-72, including the later clarification that there is no no-build preference.
Fetched `origin/master` equals `a28f76d` (PRs #45, #46 and #47 merged). Inspected
all of `dashboard.html`, its API/auth handler, queue/worker architecture, current
browser tests, roadmap, flight guide and capability snapshot. The old handoff's
unmerged-flight statement is superseded. Baseline actual Chrome suite:
**129 passed**, at desktop and 390px; isolated synthetic state, no live requests.

Official evidence checked read-only on 2026-09-11:

- [OpenAPI 2.3.0](https://raw.githubusercontent.com/SpaceTradersAPI/api-docs/main/reference/SpaceTraders.json):
  market/yard presence-gated detail; cargo, contracts, fleet, resource, travel,
  scan/chart and construction operation clusters. This is capability evidence,
  not execution proof. Use schema payloads over older guide examples.
- Official concepts: [navigation](https://docs.spacetraders.io/game-concepts/ship-navigation),
  [markets](https://docs.spacetraders.io/game-concepts/markets),
  [resources](https://docs.spacetraders.io/game-concepts/extracting-resources),
  [outfitting](https://docs.spacetraders.io/game-concepts/outfitting),
  [maintenance](https://docs.spacetraders.io/game-concepts/maintenance),
  [first mission](https://docs.spacetraders.io/quickstart/first-mission).
  The site's Markdown extraction exposes headings rather than complete article
  bodies; detailed mechanics below use the API and the repository's documented
  evidence, rather than inventing missing guide content.
- [CAPABILITY_SNAPSHOT.md](CAPABILITY_SNAPSHOT.md): FOS-73 v1 contract and dated
  15:28:29–15:28:58 UTC observations, reset 2026-09-06, SOURCE_CODE / X1-CY22.
- [EXPLORATION.md](EXPLORATION.md), [ARCHITECTURE.md](ARCHITECTURE.md), FOS-63
  accepted scope and FOS-71 dispatch register. Combat remains a future upstream
  possibility, not a screen or implemented loop.

## Capability → decision loop matrix

Every row separates durable game support, opportunity and account evidence.
All live columns are dated FOS-73 observations, **not current live state**.
Unknowns do not remove a loop from the product. Frequent = each play session or
repeated operation; deep = planning/configuration/recovery, progressively exposed.

| Player loop / frequency | Durable mechanic evidence and prerequisites | Observed opportunity | Account observation | Unknown / deferred-live; UI and automation consequence |
| --- | --- | --- | --- | --- |
| Return and triage / frequent | Agent, fleet, contracts, receipts plus local queue/journal; scope by reset | Stored economics and historical observations | 690,120 credits; two ships | Snapshot measures neither liveness nor certainty. Overview prioritizes problems, recent work, obligations and transit; Reports holds accounting. |
| Explore → inspect → fly / frequent | Systems/waypoints + orbit/navigate/arrival/dock/refuel; location, fuel and costs | Home-system waypoints and 26 markets | Both ships at C45; frigate fuel 400/400 | Routes not executed by snapshot. System map/list share a detail pane, ship context and estimated trip; arrival needs an observation. |
| Scout → refresh intelligence → reconsider / repeated | Navigation + on-site market/yard GET; scans/charting are separate mutations with prerequisites | 25 of 26 market prices unknown; three yards | Probe has zero fuel/cargo capacity | Fuel-free movement and sustained coverage unverified here. Offer coverage and independently dated detail, later reconnaissance assignments; no automatic scout launch. |
| Buy → haul → sell → measure / repeated | Market quotes + cargo purchase/sale, volume limits, navigation, reserves | Only C45 detailed quotes returned | Frigate empty 0/40 cargo | Profitability, remote quotes and executable routes unknown. Markets joins route evidence, ship hold and costs; distinguish trade volume from inventory. FOS-71 trading owns execution. |
| Source → deliver → fulfill / repeated | Contract offer/deadlines/acceptance, cargo, destination delivery and fulfillment | Four returned procurement contracts, all fulfilled | Single-good historical shapes: 57 aluminum ore, 26 equipment, 23 electronics, 5 ship parts | No active obligation/new offer observed. Contracts separates history from commitments; protected cargo and complete obligation costing precede sale/acceptance. |
| Survey → extract → transfer/haul → sell / repeated | Survey/extract equipment, site traits, cooldown, cargo and markets | B8 mineral, B43 precious deposits; XC5Z STRIPPED | Frigate mining laser II, surveyor II, mineral processor I | Survey deposits, yields, cooldowns and plan execution unknown. Fleet capability detail + Explorer site detail feed later industrial jobs, not a new top-level mining silo. |
| Siphon → haul/refine → sell / repeated | Gas site, siphon/processor, cargo, refine inputs, markets | C44 gas giant; C45 gas exchanges; siphon-drone offer | Frigate siphon II and gas processor I, empty cargo | Recipes/yields/net returns unknown. Compare raw versus refined proceeds with assumptions; later industrial coordination owns execution. |
| Compare → acquire → outfit → maintain / deep | Shipyard offers/purchase; components, slots/power/crew, repair/scrap economics | C45 probe 25,382, siphon drone 39,709; remote advertised types only | Existing probe and industrial frigate | Remote price/configuration and live fit/repair execution unknown. Fleet distinguishes advert from offer, condition from integrity; reserves and cargo recovery before later purchases/replacement. |
| Assign goal → monitor → pause/take over / frequent + deep | Application policy over shared queue/worker, not a game API endpoint | Existing sequential flight queue and historical pilot records | FOS-73 makes no ownership observation | Historical RUNNING is not a process lease. Automation owns goals later; Operations owns executable command/recovery detail now. No second command authority. |
| Review results → improve plan / deep | Scoped observations, receipts, open positions and cash reconciliation | Existing chart, reports and export | Fulfilled contracts are history, not new commitments | Cash change is not inventory-adjusted profit. Reports separates receipts/costs, unvalued cargo and estimates. Time/ship/strategy filters are later reporting work. |
| Fund gate → supply → travel → expand / deep | Construction requirements, gate connections/jump or warp capability, return fuel/cost plan | Headquarters system only | Both ships in X1-CY22 | Gate construction/route feasibility unknown. Explorer already selects recorded systems; future multi-system slice owns supply/jump/warp. Selecting a system never moves a ship. |
| Reset → archive → prepare next season / occasional | Server reset/status and public identity; owner-controlled setup | Snapshot reset known | SOURCE_CODE tied to this reset | Next reset timing not established here. Global scope selector remains; no cross-reset selection/job replay, silent registration or fabricated countdown. |

FOS-73 consumers preserve `state`, null versus observed-empty lists, independent
`details_state` / `details_observed_at`, `scope.truncated`, truncation reasons,
and `time_budget` / `detail_budget`. Do not label an entire report fresh using
`completed_at`. This foundation consumes the committed evidence for design;
it does not import a dated snapshot into the operational ledger as new data.

## Information architecture and complete migration inventory

Navigation: **Overview · Explorer · Fleet · Markets · Contracts · Automation ·
Reports · Operations**. Operations is an always-reachable operator section, not
a settings drawer. Use hash links with Back/Forward and a current-page marker.
Overview is the default. Sections stay mounted across navigation so inspection
choices, contract drafts and reconciliation explanations are retained.

Global: reset/agent scope, credits, fixed floor headroom (explicitly before fuel
and contract obligations), STOP, separate worker/certainty indicators, refresh
ledger, authenticated snapshot refresh/logout and STOP/resume controls. A
historical scope carries no command authority. Global status is available on
every section; phone layout wraps instead of horizontally scrolling the page.

Ship context persists across Explorer/Fleet/Markets/Contracts/Automation and
across section changes; Overview/Reports/Operations remain account-scoped.
Remember the selection per reset/agent in local storage until logout, validate it
against each new report, and clear it on logout. A worker-owned ship remains
selectable for inspection. Selection is never authorization. System choice is
separate: selecting a ship may locate its recorded system; changing system does
not change ship or imply travel. Detail → preview → explicit submission is the
command sequence; progress/reconciliation links lead to Operations.

| Existing surface / DOM anchor | Disposition in foundation |
| --- | --- |
| Brand, scope, STOP (`scope`, `state`) | Migrate global header; scope remains reset/agent, not selected ship |
| Ledger refresh, pause, resume (`refresh`, `pause`, `resume`) | Migrate global controls; preserve unmanaged Clear stop versus managed Resume worker semantics |
| Owner login/logout (`flight-login`, `flight-logout`) | Login remains global; logout globally reachable when managed/authenticated |
| Game snapshot refresh, heartbeat (`flight-refresh`, `flight-heartbeat`) | Refresh globally; typed global liveness summary with worker evidence disclosure. Original detailed heartbeat line relocates to Operations to avoid duplicate phone status. |
| Flight selection, preview, trip options, orbit/dock/refuel, pending request recovery | Relocate beside Explorer; retain command envelopes, deduplication and recovery IDs |
| Durable commands and outcome-review drafts (`flight-commands`) | Relocate Operations; Overview summarizes command state and links here |
| Account metrics (`credits`, `profit`, `reserve`, `coverage`, `observed`) | Retain global summary, compact spacing; headroom is not spendable cash |
| Credit chart (`chart`) | Reports; Overview shows scope cash change and recent activity |
| System/map/ship/list/waypoint detail (`system-select`, `explorer-ship`, `map`, `waypoint-list`, `waypoint-detail`) | Explorer; ship selector relocated to persistent ship-context region |
| Fleet readiness, cargo/nav details (`fleet`) | Fleet; Overview adds compact fleet/transit/cooldown check-in rows |
| Contract cards (`contracts`) | Contracts; fulfilled cards retained as history |
| Strategy notes (`plans`) | Automation; read-only recorded plans |
| Market desk selectors, prices, history and trend | Markets, unchanged inspection behavior and freshness provenance |
| Contract sources, ship snapshot, form builder, advanced JSON, model result | Contracts, unchanged offline costing; modeling ship remains an explicitly independent counterfactual input, not a command selection |
| Automation run history (`automation-runs`) | Automation, remains recorded progress rather than liveness |
| Safety/doctor button and findings | Operations, fully working on scoped stored records |
| Route watchlist (`routes`) | Markets, estimates with age/assumptions |
| Cash reconciliation, goods receipts (`audit`, `cash`) | Reports, remains working |
| Open positions/recovery intent (`positions`) | Reports, with operator navigation for reconciliation |
| Market intelligence (`markets`) | Markets, coverage/advertisements retained |
| Mutation journal (`journal`) | Operations, fully working, pending never called safely retryable |
| Export JSON and local-boundary footer (`export`) | Global footer, scoped and disabled until scope loaded |

No existing surface is removed or replaced by a placeholder. New placeholders
are scoped notices adjacent to real data: buy/sell/transfer (FOS-71 trading),
accept/deliver/fulfill (FOS-71 contracts), goal scheduling/manual takeover
(FOS-71 persistent pilot), purchase/outfit/maintenance (FOS-63 fleet slice).
Industrial, supply-chain, reconnaissance and multi-system additions live in the
sections identified in the matrix and remain named later FOS-63 slices.

## Architecture decision

| Option | Maintainability / defects / ecosystem | Security / operation / migration |
| --- | --- | --- |
| Split current no-build HTML/vanilla JS into modules | Minimal dependencies, but current dense DOM constructors, shared mutable variables and manual draft/focus preservation scale poorly to interactive trading/loadouts. Requires bespoke component/state conventions and lacks typed component contracts. | Lowest immediate migration cost. Existing Python packaging/nonce works. Browser tests still necessary; simpler installation does not remove UI lifecycle defects. |
| React + TypeScript + Vite, client-side components **selected** | Mature, broadly adopted component model and typing; easy discovery by future developers/LLMs, broad accessible-component/testing ecosystem. React owns new UI lifecycles; domain/API authority stays Python. Incremental adoption avoids reimplementing tested forms. | Adds Node/npm lockfile and build checks in development/CI. Production bundle needs no Node service, external CDN or eval. Ship built assets in Python package. Existing nonce CSP and exact Host/Origin/session checks can remain byte-for-byte. |
| Vue + TypeScript + Vite | Credible mature alternative, concise templates and reactive forms; comparable defect reduction. No game-specific advantage here over React's larger shared component/testing knowledge base. | Similar build/deploy/CSP cost and incremental migration feasibility. Not rejected as unsafe or immature. |
| Full-stack Next.js / SSR | Mature routing/server stack but duplicates this application's working API/session boundary; no SEO or server-rendering requirement for a private operations console. | Another runtime and security integration on a small VM; highest rework and operational cost without a demonstrated benefit for this slice. |

Implement React/TypeScript **islands plus shell**, not a second application or a
big-bang conversion. A small typed bridge projects ledger/flight/context state
from the existing controller into React. React owns navigation, check-in summary,
status primitives and new content; existing panels keep their DOM ownership and
are shown/hidden by an explicit adapter. Never let both renderers own the same
descendants. Future slices replace one named legacy panel at a time with typed
components; do not add new gameplay DOM constructors to the legacy script.

Build a self-contained production IIFE with Vite; embed its trusted build output
in a nonce-bearing script and CSS in the existing style block. No dynamic imports,
runtime CDN, `eval`, inline event attributes, or new public static-file router.
Escape closing script/style sequences when composing the response. Existing
`script-src nonce`, `style-src unsafe-inline`, frame exclusion, no-store,
nosniff, loopback Host/Origin, CSRF and owner session semantics remain. React
does not require CSP weakening. Local dev uses a production build/watch and the
real Python boundary rather than opening a Vite proxy to mutations.

Commit lockfile and generated package assets; CI rebuilds and compares them.
Node 22 LTS is a build dependency only (absent locally initially; install under
ignored project cache, no system changes). Use strict TypeScript and formatter
checks, existing Playwright/Chrome tests for actual integration and security,
and focused state/navigation browser regressions. No second browser framework,
client state library, CSS framework or custom router framework is needed for
eight hash sections. Add mature table/dialog libraries when a real slice needs
their behavior, rather than implementing bespoke focus traps or virtual tables.

GCP receives built Python package/assets; no Node daemon, new port or runtime
npm install. Hosting still requires its own authenticated HTTPS boundary and
single-authority handover; changing bind/Host allowlists is not deployment.
Bundle size and dependency updates are real maintenance costs accepted in
exchange for typed reusable UI. Generated assets are reviewed via source and
reproducible build diff; never hand-edit them. Intermediate bridge removal is
per panel, with existing scenario tests as the exit criterion.

## Shared patterns and state contract

- **Entity summary:** name, observed location/status, fuel/cargo/cooldown,
  observation timestamp and ownership; details disclose raw evidence. IDs/indexes
  are zero-based where shown. Tables retain native headers/captions and scroll
  inside a labeled region. Filters never imply missing data is absent globally.
- **Page/detail:** one page heading, intent/help, primary workspace + detail pane;
  native links/buttons and visible focus. Empty, loading and error are explicit;
  a retained value after failure is labeled with its original timestamp.
- **Observation freshness:** unknown/invalid/future/stale/recent stored, timestamp
  and source. Market detail uses its own 15-minute convention; capability
  snapshot has no universal threshold. Refresh ledger reloads local evidence;
  refresh game snapshot enqueues bounded worker observations.
- **Worker liveness:** heartbeat timestamp/age independently of desired pause
  and worker state. Over 15 seconds or invalid/future/missing = liveness unknown.
  Recompute age while the page is open even if polling fails. Historical pilot
  RUNNING never proves a worker is running. An HTTP polling error is not STOP.
- **Mutation certainty:** queued/waiting/dispatching/completed/blocked/cancelled
  and reconciliation-required have distinct labels. Pending journal or ambiguous
  browser submission remains uncertain. No pending records in a bounded report
  is not a global all-clear. STOP cannot cancel an already dispatched request.
- **Ownership:** inspection always allowed for observed ships; queued/running
  commands, unresolved positions or obligations explain non-commandability.
  Server/worker revalidates all authority; a frontend indicator is not a lease.
  Pause is not manual takeover. Later takeover must stop new dispatch, settle or
  reconcile in-flight work, observe fresh state, then explicitly release ownership.
- **Money/obligations:** credits, 50,000 fixed floor, known fuel/contract costs
  and uncosted obligations separately. Fixed-floor headroom is never spendable
  funds. Accepted/unfulfilled contract cargo remains protected. Current flight
  worker blocks active obligations and open automation exposure.
- **Commands:** explicit preview with inputs/timestamps/assumptions, then named
  confirmation; stable request ID survives uncertain submission. Clear drafts
  only on explicit reset/context invalidation, not navigation/polling. High-impact
  later actions disclose irreversible effects and exact ship/units/cost; no
  generic “Are you sure?” replacing a real preview. Countdown is an estimate;
  successful arrival/cooldown availability requires authoritative observation.
- **Alerts:** inline form errors plus persistent global safety summary/link to
  Operations; no toast-only loss of important errors. Error text is escaped.
  STOP/pause is directly reachable, resume is explicit and authenticated.

## Diffable low-fidelity screens

Shared desktop frame (global data is account-scoped):

```text
Flight Ledger       [reset / agent v]       STOP requested | [Pause] [Resume]
[Overview] [Explorer] [Fleet] [Markets] [Contracts] [Automation] [Reports] [Operations]
Credits | cash change (not profit) | above fixed floor (before obligations) | coverage
Observation: dated stored | Worker: heartbeat, desired state | Certainty: review needed
[Refresh ledger] [Refresh game snapshot] [Log out]
Ship-centric only: [ship v, includes worker-owned] location / fuel / cargo / ownership
PAGE TITLE / intent / section-specific workspace
```

```text
OVERVIEW: What needs attention?
STOP + unknown outcome -> [Operations]; do not retry or assume stopped in-flight
Recent commands: #42 trip WAITING / arrival observation pending
Fleet check-in: hauler A -> B, arrival timestamp (estimate); cooldown at observation
Obligations: accepted/unfulfilled count; uncosted is not zero
Recent cash movement -> [Reports]     Useful next action -> [Explorer]

EXPLORER: Explore and fly
System [X1-… v]                 shared selected ship / inspection-only reason
Map + keyboard waypoint list   | Waypoint detail: traits, independent market/yard age
Ship in transit: destination ring, no invented exact position
Preview: fuel/time ESTIMATE / assumptions / unknown inputs
[orbit] [dock] [paid refuel]     [dock on arrival] [paid refuel on arrival]
[Submit trip] -> command ID/status -> [Operations]

FLEET: Understand capacity before assigning work
Owned rows: name / location / nav / cargo / fuel / cooldown / observation
Selected ship detail: cargo + route; later equipment/capability/condition/integrity
Later: yards / compare offers (advertised != priced) / acquire & fit / maintenance
Worker-owned ship selectable for inspection; manual action blocked with reason

MARKETS: Choose a viable trade
Current: market selector, goods/prices/volume, detail age, history, route watchlist
Later trading: selected ship hold [protected units] / target market / good / units
Preview spend + fuel + obligations + sale uncertainty -> explicit Buy/Sell
Unknown remote price -> scout/read, never zero-cost opportunity

CONTRACTS: Complete obligations without stranding capital
Current cards: offered / accepted / fulfilled; goods delivered/required and deadline
Current source shortlist + offline cost form / independent modeling ship / JSON
Later: accept -> source/protect -> haul/deliver -> fulfill; deadlines revalidated
Blocked: insufficient reserved funding or protected cargo -> explain exact obligation

AUTOMATION: Who owns the next action?
Current recorded runs + decisions + strategy notes (RUNNING is historical)
Later goals/jobs: ship / budget / desired state / actual heartbeat / next decision
[Pause/STOP global] -> settle dispatch -> reconcile -> fresh snapshot -> takeover
No start/takeover button until the persistent-pilot slice implements that protocol

REPORTS: What actually happened?
Credit trail | goods spent/received | contract receipts | unexplained cash change
Open positions / unvalued cargo / recovery intent; export current scoped JSON
Later period/ship/strategy filters, capital/maintenance and season comparisons

OPERATIONS: Diagnose and recover
Durable commands: queued / waiting / dispatching / blocked / completed / review
Review required: evidence details + persistent explanation draft + record review
Mutation journal: pending/succeeded/rejected / ID / path / timestamp
[Check recorded safety] -> actual scoped doctor findings and recovery directions
STOP remains set; observation/review may queue, but clearing STOP also permits
other queued work. Inspect queue before resume. Review cancels remaining steps.
```

Phone check-in (390px, same real account state; no decorative mini-map):

```text
Flight Ledger / reset-agent
STOP requested   [Pause] [Resume]
Navigation links wrap; Overview default
Credits / fixed-floor headroom
OBSERVATION: recent stored, timestamp
WORKER: heartbeat stale — liveness UNKNOWN
CERTAINTY: command #42 reconciliation required
[Operations: inspect queue/journal]
Ship: A -> B; arrival estimate, not confirmed
Cooldown: 20s at observation (not live readiness)
Recent activity / [Reports]
```

Dense tables scroll within their region. Explorer/outfitting remain
desktop-oriented; phone users can still inspect and safely request STOP. No
claim of safe inactivity based on a stale heartbeat alone.

## Scenario walkthroughs and resulting revisions

| Scenario | Walkthrough / expected decision | Gap found → revision |
| --- | --- | --- |
| Return after hours | Overview: inspect dates, STOP/liveness/certainty, recent commands, transit and obligations; Reports for cash/positions; Operations for blockers | Credit delta could be mistaken for profit or “since last visit” → label scope cash change; no invented last-visit interval. |
| Trade at another waypoint | Select ship, Markets compare known quotes/capacity/reserves, Explorer preview/fly, confirm arrival, later buy/sell preview then receipt | Separate pages could lose ship or sell contract cargo → persistent scoped context, protected-unit convention. Today only market inspection and flight execute. |
| Accept/work contract | Contracts inspect deadlines, cost complete sources/routes, reserve, later accept and protect cargo, deliver at destination then fulfill | Fulfilled historical terms could look like obligations → explicit status; no active observation is not proof of no fresh obligations. |
| Manual takeover | Automation inspect recorded run + real heartbeat, request STOP, Operations wait/reconcile dispatch, fresh snapshot, later explicit release | Pause alone could be confused with ownership transfer → no takeover claim/button in foundation. |
| Failed/ambiguous command | Operations distinguishes rejection from unknown; open evidence, observe current state, write explanation, record review cancels dependents | Recovery controls hidden in flight panel → dedicated always-reachable Operations plus global certainty link. |
| STOP + reconciliation required | Overview shows both independently; Operations journal and command agree about uncertainty; inspect before resuming queued review/work | “STOP means nothing can have happened” and “review runs while paused” are unsafe assumptions → explain already-dispatched requests and queued review/resume semantics. |
| Phone + stale worker | Read original observation age, independently stale heartbeat, latest command; request STOP if activity is unwanted, verify response; investigate worker from supervised host | Successful ledger refresh could turn liveness green → recompute heartbeat age independently; unknown liveness never proves paused/dead/safe to ignore. |
| Compare/buy ship | Fleet inspect capability gap; Explorer yard detail distinguishes advert/offer; later compare price/config/reserves and confirm purchase | A remote advert could imply priced availability → unknown offer state, named later fleet slice instead of fake Buy control. |
| Another system | Explorer choose another recorded system, retain ship location/system, inspect gate evidence; later cost return/refuel before travel | Browsing could imply reachability → system selection is observation navigation only; jump/warp stay deferred. |

No unresolved human-owned product/risk fork remains. This checkpoint supports
implementation of the shell and migration; it does not authorize wider gameplay.

## UI contract for subsequent slices

1. **Navigation:** the eight hash sections above; new gameplay belongs in a named
   section. Operations is the permanent journal/doctor/command-recovery surface.
2. **Ship context:** shared per reset/agent on ship-centric screens, persisted
   across navigation, cleared on logout/invalid scope. Inspect worker-owned ships;
   do not infer authority from selection or a recent heartbeat. Offline model
   ship is explicitly independent of the command context.
3. **Components:** new UI uses typed React page/panel, status, empty-state and
   entity-summary primitives; native accessible form/table/detail patterns.
   The bridge is the only shell-to-legacy boundary. Replace a legacy panel
   atomically; never let React and legacy code edit the same descendants.
4. **State:** observation age, worker liveness, mutation certainty, ownership and
   estimate assumptions are separate. Preserve drafts on poll/navigation and
   reject late responses after scope changes. Reuse existing authenticated API,
   stable command IDs, queue/worker, STOP/reconciliation/reserve policy.
5. **Real now:** all inventory rows above; shell/check-in, explorer/flight,
   historical markets/contracts, offline cost model, reports, recorded runs,
   doctor/journal/reconciliation. **Not implemented:** trading writes (Task 03),
   contract writes (next contracts task), goal scheduling/takeover (pilot task),
   purchases/outfits/maintenance/industry/multi-system (named FOS-63 slices).
6. **Delivery:** build/typecheck/format frontend, run Python quality checks and
   explicit browser suite at desktop + 390px through the real loopback server.
   Package generated assets. No runtime Node or new hosted security boundary.
