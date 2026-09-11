# Browser Flight Operations (FOS-71 Task 02)

## Offline launch

Use the existing Python 3.12 `.venv`. From this checkout, select a **new** ignored
demo directory. Setup refuses to overwrite existing history or fake remote state.

```sh
mkdir .cache/nightly/flight-demo
export ST_STATE_ROOT="$PWD/.cache/nightly/flight-demo"
.venv/bin/python -m py_st flight setup --demo
```

Setup prompts twice for a local owner password (any length, including blank).
It is not a game credential and is never passed in argv. A salted PBKDF2 verifier is stored with
owner-only permissions. Setup starts paused and creates STOP.

In two terminals, with the **same absolute `ST_STATE_ROOT`** in both:

```sh
.venv/bin/python -m py_st flight worker
```

```sh
.venv/bin/python -m py_st flight serve --port 8765
```

Open **http://127.0.0.1:8765**, log in, and click **Resume worker**. Select
**Explorer** in the navigation, then select `SYNTHETIC-1` in the shared ship
context and waypoint `X-DEMO-B2` in the explorer. Preview the trip, retain
Dock/Refuel on arrival and submit. The independent worker orbits, navigates,
confirms arrival, docks and refuels. The synthetic trip uses 12 fuel and paid
refueling costs 72 credits: 123,456 → 123,384, ending at B2 with 100/100 fuel.
The demo deliberately accelerates transit to three seconds; the real travel
formula is still labeled an estimate and compared with the observed route.

Use the literal IPv4 address `127.0.0.1`: `localhost` and `::1` are deliberately
not accepted by the Host/Origin boundary. Restarting `flight serve` clears its
in-memory login sessions, so log in again afterward even if the cookie has not
expired. This does not clear queued work or the worker's desired pause state.

Closing the page leaves the worker running. Reopen and log in if necessary to
see persisted commands, fleet, credits and receipts. Browser submissions keep
their request ID in local storage until acknowledged; a lost application response
can be recovered using that same ID. Reuse with a different payload is rejected.

Pause creates STOP and persists desired pause. Resume requires authentication.
Stopping/restarting `flight worker` preserves the fake world and pending work.
It never implicitly removes STOP. `worker --once` processes one bounded tick.
Ctrl-C stops each process; no system service is installed by this task.

During transit the worker records a next observation time, bounded to at most
30 seconds or the expected arrival, whichever is sooner. Between observations
it maintains its heartbeat and checks STOP without fetching the fleet again.
An elapsed arrival time only triggers another observation; it never completes
the arrival step on its own.

## Offline failure scenarios

Use a separate new demo root for each scenario, or understand that each command
deliberately changes only that root's **synthetic remote world**. Enqueue a browser
snapshot refresh afterward to show the changed observations.

```sh
.venv/bin/python -m py_st flight demo-scenario low-fuel
.venv/bin/python -m py_st flight demo-scenario low-funds
.venv/bin/python -m py_st flight demo-scenario lost-response
```

- **low-fuel:** sets carried fuel to 1; travel blocks before departure.
- **low-funds:** sets credits to 50,010 and fuel to 50; paid refuel blocks on the
  protected reserve. It does not spend down the floor.
- **lost-response:** the next successful mutation commits in the fake API, then
  loses its response. The journal stays pending, and the command shows
  **RECONCILIATION_REQUIRED**. No automatic replay or dependent step is allowed.

For an unknown outcome, refresh the game snapshot, inspect actual ship state,
credits and the command/journal evidence in **Operations**, then enter an outcome explanation
in the command's review control. Explicit review records fresh evidence and cancels
the rest of that command. Submit a new deliberate workflow only after reviewing
the result. A countdown, full tank or old observation is not sufficient proof.

## Live setup (separate verification)

Live implementation is present but this delivery is verified offline. Use the
existing authoritative root, not the demo root or another checkout's empty state:

```sh
export ST_STATE_ROOT="$PWD"
.venv/bin/python -m py_st flight setup
.venv/bin/python -m py_st flight worker
# Separate terminal, same ST_STATE_ROOT:
.venv/bin/python -m py_st flight serve --port 8765
```

The existing `.state/intelligence.sqlite3` must be a supported WAL ledger with
recorded history for the freshly verified reset/agent. Setup reads status/agent
using `ST_TOKEN` from the environment or **canonical-root `.env`**; it never
registers or silently creates live history. Preserve a consistent backup first.
The worker reobserves agent/fleet/contracts before mutation and validates identity,
ownership, travel state, same-system destination, fuel and reserves.

On HTTP 401 or code 4113 it persists STOP/pause. The owner verifies reset/account
state, updates ignored token configuration, restarts the worker to clear the
transport's authentication latch, then explicitly resumes in the browser. A new
reset/account requires separately reviewed state setup; old work is never replayed
into the new scope.

All real-client gameplay mutations outside the worker are disabled in this
revision. Existing CLI previews/legacy services remain, but cannot dispatch live
mutations; legacy `auto` Sessions also refuse with `ST_STATE_ROOT` configured.
Registration remains an explicit owner-only operation outside the worker. Do not
use older clients concurrently to bypass ownership. Two workers for the same
reset/agent on this Linux host cannot dispatch, even from different checkouts.

## Storage, upgrade and restore

### Interrupted setup

Setup creates several files and is **not a single atomic transaction**. It never
silently overwrites a partial root on retry. For a disposable demo, use a new
empty demo root and retain the failed root for inspection. For a live root,
preserve the existing intelligence ledger, backups and STOP: do not delete the
root or replace its history. With both processes stopped, inspect only the new
`owner.json` and `flight.sqlite3` setup artifacts. Retain a copy before removing
an incomplete owner verifier or an incomplete queue with no submitted commands,
then rerun setup. If the queue contains commands, use its supported recovery
instead of reinitializing it. Authentication/reset failures during live setup
persist STOP even when no flight queue has been created yet.

### Compatibility and backups

- Existing intelligence schema 1 is unchanged. The flight queue is a new,
  separately versioned schema 1 file; normal startup opens existing files only.
- Queue schema, executable command kinds/versions/steps and managed identity are
  checked before dispatch. Completed/cancelled/blocked history is not revalidated
  for execution on every poll. Unsupported open state needs compatible code, not
  repaired by deleting commands or resetting schema versions.
- The root path is recorded. Moving it is not an implicit migration. Keep the same
  absolute root when changing checkouts. A future relocation should be an explicit
  paused, reviewed migration; no relocation tool is included in Task 02.
- For a full backup, pause in the browser, stop **both server and worker**, then
  archive the entire canonical root's `.state` directory and STOP. Keep token
  configuration separately private. This quiesces both databases so they form one
  consistent checkpoint, including any SQLite sidecars and demo remote state.
  `auto backup NEW_PATH` is an intelligence-only online backup and is not a full
  flight backup; it now refuses a missing source ledger.
- Restore the complete checkpoint into the same absolute root with matching code,
  preserving STOP. Start the server/worker and inspect the queue before resuming.
  Do not downgrade to pre-flight code with open commands or pending actions:
  older releases do not know this execution authority. Never combine a queue from
  one checkpoint with a ledger or demo world from another.
- No cross-host execution or automatic local-to-GCP transfer is provided. Future
  remote clients must use the single authoritative service; local locks do not
  coordinate different hosts.

## Verification

Review follow-up results: **1,602 passed, 13 skipped** in normal offline pytest;
**129 passed** in the explicit browser-enabled dashboard/flight invocation
(includes integration tests). Black, Ruff `--no-fix`, mypy and diff whitespace
checks pass. Screenshots from this verification are:

- `.cache/nightly/flight-review-final-browser/test_browser_trip_1440_0/flight-1440.png`
- `.cache/nightly/flight-review-final-browser/test_browser_trip_390_0/flight-390.png`

No live credentials/API requests or authoritative runtime-state changes were
needed. Tests use isolated synthetic ledgers and fake remote state.

```sh
ST_LIVE_TESTS=0 ST_CACHE_DIR=.cache/nightly/flight-cache \
  .venv/bin/python -m pytest -q --basetemp=.cache/nightly/flight-full-tests
.venv/bin/python -m black --check .
.venv/bin/python -m ruff check --no-fix .
.venv/bin/python -m mypy .
ST_LIVE_TESTS=0 DASHBOARD_BROWSER_TESTS=1 \
  ST_CACHE_DIR=.cache/nightly/flight-browser-cache TMPDIR="$PWD/.cache/nightly" \
  .venv/bin/python -m pytest tests/test_flight.py tests/test_dashboard.py -q \
  --basetemp=.cache/nightly/flight-browser-tests
```

Browser tests use Playwright with installed Chrome (`channel="chrome"`). Install
the optional `.[browser]` extra when needed. They exercise actual login, map
selection, preview, submission, page closure, worker execution and reopened
fleet/credit views at 1440px and 390px. Screenshots are retained in each browser
test's ignored temporary root. Integration coverage includes full-trip economics,
duplicate IDs, scope/ownership, restart boundaries, STOP, changed prerequisites,
unknown/malformed outcomes, account/authentication mismatch and schema refusal.

Run these test invocations sequentially. They intentionally share a synthetic
reset/agent identity, so overlapping test processes contend for the same host
ownership lock just as two workers for a real account would.

## Known limits / stopping boundary

This is local Linux, loopback HTTP and one same-system CRUISE flight workflow.
Travel previews use a conservative round-trip reserve; execution can additionally
use the existing freshly funded destination-refuel policy. Those estimates may
differ and are not binding quotes. Active contracts and open automation exposure
block mutation because this assignment does not cost or coordinate them.

The queue executes sequentially and polls authoritative arrival; it is not a fleet
scheduler. History retention/hosted backups, HTTPS, GCP supervision, cross-host
handover, trading, contracts and persistent pilot controls belong to later tasks.
Live verification, VM restart proof and an unattended hosted soak are deferred.
