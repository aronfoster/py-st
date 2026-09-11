# Architecture

Flight Ledger is a local browser application over shared SpaceTraders services.
FOS-71 Task 02 establishes persistent browser flight operations. FOS-63 owns
the wider gameplay, automation and future hosting roadmap.

## Execution path

Browser → authenticated loopback API → SQLite flight queue → independent worker
→ guarded Session → client/transport → game (or persistent synthetic HTTP peer).

The dashboard holds no game token. It validates typed commands and stable request
IDs, then returns without waiting for travel. The worker is a separate process;
closing the browser has no effect on execution. The same intelligence ledger
feeds explorer, fleet, credits, action history and planning panels.

| Component | Responsibility |
| --- | --- |
| `cli/flight_cmd.py` | Explicit setup, serve, worker and offline scenarios |
| `services/dashboard.py`, `dashboard.html` | Owner session, Host/Origin/CSRF boundary, UI and enqueue API |
| `frontend/src`, `services/ui` | Typed React shell/primitives and packaged Vite production assets; explicit bridge to legacy panels |
| `services/flight_queue.py` | Versioned commands, deduplication, steps, pause state and heartbeat |
| `services/flight_worker.py` | Account authority, fresh flight checks, bounded dispatch, arrival and recovery |
| `services/flight_demo.py` | Persistent synthetic world behind `httpx.MockTransport` |
| `services/flight_auth.py` | Salted password verifier; no plaintext password storage |
| `services/automation.py` | Session lock, STOP-aware waits, navigation policy and write-ahead journal |
| `services/strategies.py` | Guarded refuel planning and legacy economic strategies |
| `services/intelligence.py` | Scoped observations, receipts, reports and cash accounting |
| `client/transport.py` | Pacing, safe rejection retries, authentication latch and dispatch guard |

## Durable state and ownership

`ST_STATE_ROOT` is an explicitly configured absolute directory, independent of
checkout/current directory. It contains `.state/intelligence.sqlite3` (existing
schema 1), `.state/flight.sqlite3` (flight schema 1), `.state/owner.json` and STOP.
Demo mode additionally has `.state/remote.sqlite3`; it cannot contact the game.
Setup is explicit and preserves an existing live ledger. Missing/newer state is
refused, never replaced with an empty database.

Commands bind to a reset/agent scope. Every tick checks command schema, versions,
kinds and steps for executable work; terminal history is not decoded for
execution compatibility on each poll. Fresh account identity must match before
execution. An abstract
Linux Unix-domain socket keyed by reset/agent excludes other local workers even
when they use different state paths. The original filesystem Session lock also
excludes legacy Sessions sharing the root. Real-client mutations outside the
worker are refused at transport dispatch, including legacy CLI ship services.
The explicit owner registration endpoint is outside worker permissions.

This is local-host ownership, not cross-host coordination. Remote clients must
eventually use one authoritative service; hosted setup/handover is deferred.

## Failure and recovery

Each tick has a 120-second/10-action Session budget; each flight step dispatches
at most one mutation. Reads share pacing, including after transport failures.
Dispatch permission expires 30 seconds after step preparation, including safe
409/429 retry waits. STOP is checked during waits and before dispatch. It cannot
cancel an HTTP request already in flight. Desired pause survives restart.

The command is marked dispatching before the Session creates its pending journal
entry. On restart, absence of a journal entry means revalidation is safe. A valid
success receipt advances the step; an unknown outcome blocks it. A malformed
success response remains pending. No refuel is inferred from a full tank and no
unknown mutation is repeated. Explicit owner review stores fresh evidence and
an explanation, then cancels remaining dependent steps.

Arrival is a fresh API observation, not an elapsed countdown. Travel previews
are labeled estimates with original timestamps and assumptions; missing inputs
stay unknown. Navigation evidence includes estimated versus observed fuel/time.
Actual refuel receipts update the shared cash report.

While in transit, the next observation time is persisted in command evidence.
The worker polls at most every 30 seconds (sooner at expected arrival), keeping
heartbeat and STOP handling independent of API polling. Server polling preserves
the owner's reconciliation draft and caret rather than recreating an empty form.

## Boundaries

Only same-system CRUISE flight operations are dispatched. Credit protection keeps
at least 50,000 plus the existing fuel allowance and costed refill requirements.
Active contracts and open/unknown automation positions block flight mutations
until a later workflow can cost and coordinate them. No cargo is sold or consumed
by this milestone. Browser trading/contracts/pilot controls build on this queue
in later tasks rather than introducing another execution authority.

## Browser presentation

FOS-72 adds the eight-section shell and independent observation/liveness/certainty
status over the same API. React owns new shell/check-in components; an explicit
adapter relocates existing panel roots, retaining their controllers and drafts.
Ship selection persists per reset/agent but never grants execution authority.
Operations keeps the real command/reconciliation, journal and doctor surfaces.

Node 22/npm are development/CI build dependencies only. Vite emits a bundled
IIFE and CSS packaged with Python and embedded under the existing nonce CSP.
No new runtime server, CDN, static-file router or Host/Origin exceptions. CI
rebuilds committed assets and checks drift. See [UI/UX](UI_UX.md) for architecture
comparison, surface inventory and the contract for subsequent gameplay slices,
and [frontend instructions](../frontend/README.md) for builds and migration rules.

See [Flight Operations](FLIGHT_OPERATIONS.md) for setup and verification and
[Handoff](HANDOFF.md) for current continuation instructions.
