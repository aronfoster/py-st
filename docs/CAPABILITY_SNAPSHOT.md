# Capability snapshot — FOS-73 / FOS-72 input

## Rerun

From the supervised desktop checkout, with owner-managed `ST_TOKEN` in the
environment or ignored `.env`:

```sh
.venv/bin/python -m py_st capability-snapshot
.venv/bin/python -m py_st capability-snapshot \
  --output .cache/nightly/capability-snapshot.json
```

No credential arguments are accepted. Output is projected JSON, not a raw API
dump. It excludes account IDs, transaction counterparties, descriptions, error
payloads, headers and local configuration. The CLI additionally redacts the
configured token and suppresses logging and exception details. Review the
sanitized report before publishing; runtime JSON stays ignored.

The service uses the existing client/transport GET and pagination paths. It
does not use the smart-merge cache: a new response without prices must not
make old prices look fresh. No scans, surveys, navigation, registration or
other mutations occur. Existing ledger/cache/STOP files are not modified.
HTTP 401 or API 4113 aborts immediately; the owner checks reset/account state
and refreshes `ST_TOKEN` before another live attempt.

Scope is deliberately small: fresh fleet and contracts, headquarters-system
waypoints, and at most 80 market/shipyard detail reads. The CLI stops dispatch
after a 180-second monotonic budget (an in-flight request may finish later).
Unavailable reads become unknown; authentication failures abort the report.
There is no cross-system discovery or claim that same-system destinations
have affordable, executable routes. Ships elsewhere remain in the fleet list.

## Snapshot contract, version 1

- `started_at` / `completed_at`: UTC observation window, not an atomic world
  state. Paginated observations are timestamped when collection completes.
- `reset`: observed reset date or explicit unknown.
- `scope`: headquarters system, coverage and route/freshness limitations.
- `game_capabilities`: API-implied loop vocabulary, not live execution proof.
- `account_observations`: public agent symbol/headquarters/credits, fleet
  frames/modules/mounts/cargo and fuel capacities/location, contract types,
  status, payment and delivery requirement shapes.
- `opportunity_observations`: waypoint types/traits/coordinates, market goods
  and available prices, shipyard advertised types and available offers with
  component symbols/capacities.
- Each observation has `state`, `data`, and either `observed_at` or a fixed
  unknown `reason`. Missing projected fields are null, never invented values.
- Markets/yards have independent `details_state` and `details_observed_at`.
  Null detail timestamps mean unknown, even when the site itself was freshly
  observed. Consumers compute age from that timestamp at display time; no
  arbitrary universal fresh/stale threshold is embedded.
- Empty lists are observed emptiness; null lists are unknown/not returned.
  `unknowns` records limits on route, yield, recipe and scout inference.

For FOS-72, retain capability rows when current opportunity is unknown. Keep
data age separate from worker liveness and mutation outcome certainty; this
report does not observe either of those execution dimensions.

## Offline proof before first live use

`tests/test_capabilities.py` uses `httpx.MockTransport` through the real shared
transport with a GET-only assertion. It covers pagination, fresh versus
location-gated details, unavailable reads, missing headquarters, explicit
empty contracts, field projection, token redaction, and HTTP 401/API 4113
termination with no further requests or error-payload disclosure.

Verification: six targeted tests passed before live execution. Full suite:
**1,608 passed, 13 skipped**. Black check, Ruff `--no-fix` and source mypy pass.
Base: verified remote `master` at `6d4f2ff` (merged PR #46).

## Supervised live evidence — 2026-09-11

Owner requested the run in the desktop session. Executed the output-file
command after offline proof, using existing credential configuration.
Observation window: **15:28:29–15:28:58 UTC**. Reset: **2026-09-06**.
Public agent: **SOURCE_CODE**, headquarters system **X1-CY22**, observed
credits **690,120**. Local sanitized evidence:
`.cache/nightly/fos-73-live-2026-09-11.json` (ignored, not committed).

### Capability / loop matrix for FOS-72

| Loop / game capability | Currently observed opportunity | Current-account observation | UI / automation implication and remaining unknown |
| --- | --- | --- | --- |
| Trading: market goods and price endpoints, cargo purchase/sell | 26 markets; fresh detailed prices only at C45, other 25 unknown | Frigate at C45, cargo 0/40, fuel 400/400 | Separate known goods from known prices. No profitable route established by this snapshot. |
| Continuous market intelligence: navigation plus location-gated market GET | Broad market network with only one detailed market observation | SOURCE_CODE-2 is FRAME_PROBE, zero cargo and fuel capacity, in orbit at C45 | Scout-loop candidate. Show coverage/price age; zero fuel capacity alone is not live movement or continuous-scout proof. |
| Fleet growth: shipyard advertised types and offers | A2 advertises probe/light shuttle/light hauler; H58 mining drone/surveyor; C45 returns priced offers | C45 probe 25,382 credits; siphon drone 39,709 with cargo-hold capacity 15, gas processor I and siphon I | Compare advertised versus priced/configured offers. Remote prices/configuration unknown; affordability still needs reserves and obligations. |
| Extraction and survey: extract/survey endpoints and equipment models | Asteroids include B8 with mineral deposits; B43 with precious metal deposits; XC5Z is STRIPPED | Frigate carries mining laser II, surveyor II and mineral processor I | Show equipment plus site prerequisites and adverse traits. Deposits/yields/cooldowns and executable mining/survey plans untested. |
| Siphoning: API siphon/equipment models | Gas giant C44; C45 exchanges hydrocarbon, liquid hydrogen and liquid nitrogen | Frigate carries gas siphon II and gas processor I; local siphon-drone offer exists | Candidate collect/haul/sell loop. C45 sell quotes 43/23/28 respectively are dated evidence, not a yield/profit forecast. |
| Refining: refine endpoint and processor models | Processor-equipped frigate; material markets known | Cargo empty; mineral and gas processor I installed | Keep industrial planning visible but prerequisite-gated. Recipes, inputs, yields and execution not verified. |
| Contracts: procurement requirements, sourcing/delivery workflow | Four returned procurement contracts, all fulfilled | Historical requirement shapes: 57 aluminum ore, 26 equipment, 23 electronics, 5 ship parts, each single-good | Support obligation/history views; no active unfulfilled contract or new offer observed. Do not negotiate in read-only discovery. |
| Wider exploration: systems/navigation surfaces | Headquarters-system evidence only | Both ships observed in X1-CY22 | Preserve system context in UI; cross-system routes, gate requirements and feasibility deferred. |

Waypoint suffixes above are within X1-CY22. All prices, inventory, equipment,
credits and contract statuses are transient observations of this reset/account.
The matrix is reconnaissance input to FOS-72, not UI implementation or live
authorization to execute any candidate loop.
