# Flight Ledger browser foundation

Design, panel inventory, wireframes and downstream contract:
[`docs/UI_UX.md`](../docs/UI_UX.md).

Use Node 22 LTS (22.12 or newer) and npm. From this directory:

```sh
npm ci
npm run check
npm run build
```

From the repository root, `make install-hooks` installs both the normal commit
hooks and a pre-push hook that runs the complete Python quality/test suite plus
the frontend checks, rebuild, and generated-asset drift check. A failed check
blocks `git push`; bypassing hooks with Git's `--no-verify` remains an explicit
operator choice.

`npm run format` formats frontend source. Build runs strict TypeScript and Vite,
producing `src/py_st/services/ui/shell.js` and `shell.css`. Commit both source and
generated assets; CI rebuilds and rejects drift. The lockfile pins the dependency
graph. Do not hand-edit generated bundles. Vite preserves dependency license
notices in the bundle.

The Python application embeds the production bundle under its existing nonce
CSP. It serves no CDN assets, needs no Node process at runtime and adds no static
file path/Host/Origin exception. Run the ordinary demo server/worker described in
[`FLIGHT_OPERATIONS.md`](../docs/FLIGHT_OPERATIONS.md). To iterate, rebuild and
restart the Python server (which reads its HTML/assets at startup), then reload
and log in. `vite build --watch` may rebuild assets; a Vite development server
is not the application/authentication boundary.

## Ownership boundaries

- `src/main.tsx`: navigation, global state summary, Overview and contextual help.
- `src/components.tsx`: `Panel`, `EntitySummary`, `Status`, `EmptyState`,
  `Freshness` and clock/unknown handling. New gameplay uses these typed patterns.
- `src/bridge.ts`: typed snapshot subscription, explicit legacy panel inventory,
  section visibility and presentation-only manual-command availability.
  It is the sole writer of disabled/title state on the four manual buttons;
  legacy submission code publishes `submitting` instead of overriding that guard.
- `dashboard.html`: existing controllers and panel descendants. It publishes a
  new snapshot reference on `ledger-ui` events. No game credentials are exposed.
  React must not render into a legacy-owned panel, and legacy code must not
  modify React-owned descendants. Its ship selector is moved but retains one
  owner. Scope-keyed local storage remembers selection until logout; selecting
  a ship never grants execution authority.

Navigation uses `#/section` fragments, which must not double as DOM element IDs.
The adapter hides panels during migration and applies the initial route before
React commits. Keep the inventory/browser tests when replacing panels; missing
legacy anchors throw an error naming the missing ID. Inspection previews are
non-mutating and may remain available when manual mutations are blocked.
Overview takes the first five commands from the queue report's newest-ID-first
ordering. The global credit observation age is never a market-quote timestamp.

Add new gameplay as React components, replace legacy panels one at a time, and
remove the corresponding adapter entry. Keep the current shared command API,
request IDs, queue and server/worker checks. Do not add parallel polling or a
second mutation path just to use a component library.

## Browser verification

From the repository root, sequentially with other flight suites:

```sh
ST_LIVE_TESTS=0 DASHBOARD_BROWSER_TESTS=1 \
  ST_CACHE_DIR=.cache/nightly/ui-browser-cache TMPDIR="$PWD/.cache/nightly" \
  .venv/bin/python -m pytest tests/test_flight.py tests/test_dashboard.py -q \
  --basetemp=.cache/nightly/ui-browser-tests
```

Uses real loopback HTTP, Playwright/installed Chrome, synthetic persistent game
state and actual queue/worker. Covers navigation and all retained panel locations,
desktop/390px layout, draft/selection retention, liveness independent of data age,
STOP/reconciliation, auth, CSP, escaping and flight economics after page closure.
Python quality checks and the full offline suite remain required too.
