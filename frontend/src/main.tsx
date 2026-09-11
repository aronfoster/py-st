import { useEffect, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import {
  migratePanels,
  pages,
  readSnapshot,
  shipPages,
  showPage,
  setManualAvailability,
  subscribe,
  type Page,
  type Snapshot,
  type TradePreview,
} from "./bridge";
import {
  elapsed,
  EmptyState,
  EntitySummary,
  Freshness,
  Panel,
  Status,
} from "./components";
import "./style.css";

function currentPage(): Page {
  const page = location.hash.startsWith("#/") ? location.hash.slice(2) : "";
  return Object.hasOwn(pages, page) ? (page as Page) : "overview";
}

const descriptions: Record<Page, string> = {
  overview:
    "Check what happened, what needs attention and what is still unknown.",
  explorer:
    "Inspect recorded waypoints, preview a trip and fly the selected ship.",
  fleet: "Inspect owned ships, cargo, fuel and navigation evidence.",
  markets: "Compare stored prices, history and estimated routes.",
  contracts: "Inspect obligations and cost the whole plan before committing.",
  automation:
    "Inspect recorded decisions and understand who owns the next action.",
  reports: "Review measured cash flows, history and open positions.",
  operations:
    "Inspect durable commands, reconcile uncertain outcomes and diagnose safety.",
};
const deferred: Partial<Record<Page, string>> = {
  fleet:
    "Purchase, outfitting and maintenance controls: later FOS-63 fleet slice. Recorded shipyard detail remains in Explorer.",
  contracts:
    "Accept, deliver and fulfill controls: FOS-71 browser contracts slice. The existing cost model is offline only.",
  automation:
    "Goal scheduling and manual takeover: FOS-71 persistent pilot slice. Pause requests STOP; it does not transfer ownership.",
};

function Trading({ snapshot, now }: { snapshot: Snapshot; now: number }) {
  const markets = snapshot.ledger.markets || [];
  const ship = (snapshot.ledger.ships || []).find(
    (row) => row.key === snapshot.selectedShip,
  );
  const local = markets.find(
    (row) => row.key === ship?.data.nav.waypointSymbol,
  );
  const goods = local?.data.tradeGoods || [];
  const [kind, setKind] = useState<"purchase" | "sell">("purchase");
  const [good, setGood] = useState("");
  const [units, setUnits] = useState(1);
  const [preview, setPreview] = useState<TradePreview | null>(null);
  const [message, setMessage] = useState("");
  const block =
    commandBlock(snapshot, kind === "sell") ||
    (snapshot.ledger.paused || snapshot.flight?.settings.paused
      ? "STOP requested"
      : null);
  useEffect(() => {
    setPreview(null);
    setGood("");
  }, [snapshot.selectedShip, local?.observed_at]);
  const inspect = async () => {
    setMessage("");
    try {
      setPreview(
        await window.ledgerUI.previewTrade({
          scope: snapshot.ledger.scope,
          ship: snapshot.selectedShip,
          good,
          units,
          kind,
        }),
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed");
    }
  };
  const submit = async () => {
    if (!preview || preview.unit_price === null || !preview.observed_at)
      return;
    setMessage("Submitting durable command…");
    try {
      const command = await window.ledgerUI.submitCommand({
        kind: preview.kind,
        ship: preview.ship,
        good: preview.good,
        units: preview.units,
        waypoint: preview.waypoint,
        quote: preview.unit_price,
        observed_at: preview.observed_at,
      });
      setMessage(
        `Command #${command.id} ${command.status}. Track it in Operations.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Submission was not confirmed",
      );
    }
  };
  return (
    <Panel title="Trade through durable command authority">
      <p>
        Known goods are advertisements. Only dated detailed observations below
        contain prices; stale or missing detail is never treated as current or
        zero.
      </p>
      <p className="small">
        {ship
          ? `${ship.key} · ${ship.data.nav.waypointSymbol} · ${ship.data.nav.status} · cargo ${ship.data.cargo.units}/${ship.data.cargo.capacity}`
          : "Select an owned ship."}
      </p>
      {!local ? (
        <EmptyState>
          No market observation at this ship. Inspect movement in{" "}
          <a href="#/explorer">Explorer</a>.
        </EmptyState>
      ) : (
        <>
          <p className="small">
            Local market observed{" "}
            <Freshness stamp={local.observed_at} now={now} />
          </p>
          {!goods.length ? (
            <EmptyState>
              Known goods:{" "}
              {[
                ...local.data.exports,
                ...local.data.imports,
                ...local.data.exchange,
              ]
                .map((g) => g.symbol)
                .join(", ") || "none"}
              . Current price detail is unknown.
            </EmptyState>
          ) : (
            <div className="trade-form">
              <label>
                Action{" "}
                <select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value as "purchase" | "sell");
                    setPreview(null);
                  }}
                >
                  <option value="purchase">Purchase</option>
                  <option value="sell">Sell</option>
                </select>
              </label>
              <label>
                Commodity{" "}
                <select
                  value={good}
                  onChange={(e) => {
                    setGood(e.target.value);
                    setPreview(null);
                  }}
                >
                  <option value="">Choose good</option>
                  {goods.map((g) => (
                    <option key={g.symbol}>{g.symbol}</option>
                  ))}
                </select>
              </label>
              <label>
                Quantity{" "}
                <input
                  type="number"
                  min="1"
                  value={units}
                  onChange={(e) => {
                    setUnits(Number(e.target.value));
                    setPreview(null);
                  }}
                />
              </label>
              <button disabled={!good || units < 1} onClick={inspect}>
                Preview against stored evidence
              </button>
            </div>
          )}
        </>
      )}
      {preview && (
        <div
          className={
            preview.feasible ? "trade-preview" : "trade-preview attention"
          }
        >
          <strong>
            {preview.feasible ? "Guarded estimate" : "Not currently feasible"}
          </strong>
          <p>
            {preview.units} {preview.good} × {preview.unit_price ?? "unknown"}{" "}
            = {preview.total_price ?? "unknown"} credits. Cargo{" "}
            {preview.cargo_before} → {preview.cargo_after}/
            {preview.cargo_capacity}; credits {preview.credits_before} →{" "}
            {preview.credits_after ?? "unknown"}.
          </p>
          <p>
            Fixed floor {preview.fixed_floor}; fixed-floor headroom{" "}
            {preview.fixed_floor_headroom} must still cover the known fuel
            reserve of {preview.fuel_reserve} and contract obligations.
            Protected contract cargo:{" "}
            {JSON.stringify(preview.protected_contract_cargo)}. Sellable
            selected cargo: {preview.sellable_units}.
          </p>
          <p className="small">
            {preview.reason} · quote{" "}
            {preview.stale ? "STALE" : "recent stored, not live"} ·{" "}
            {preview.observed_at || "unknown timestamp"}
          </p>
          <button
            disabled={!preview.feasible || block !== null}
            title={block || "Submit to guarded worker"}
            onClick={submit}
          >
            Submit guarded {preview.kind}
          </button>
          {block && <p className="small">Inspection only · {block}</p>}
        </div>
      )}
      <p role="status">{message}</p>
      <p className="small">
        Cargo transfer remains the next bounded extension; it is not exposed
        until its live revalidation and ambiguous-outcome evidence use this
        authority.
      </p>
    </Panel>
  );
}
const active = (status: string) =>
  !["completed", "blocked", "cancelled"].includes(status);

function commandBlock(
  snapshot: Snapshot,
  allowProtectedSale = false,
): string | null {
  const { ledger, flight, selectedShip } = snapshot;
  if (!snapshot.managed) return "unmanaged ledger";
  if (!snapshot.authenticated) return "owner login required";
  if (snapshot.error) return "state update unavailable";
  if (!flight || ledger.scope !== flight.settings.scope)
    return "command authority unknown or historical scope";
  if (snapshot.submitting) return "submission in progress";
  if (snapshot.pending)
    return "recover prior submission with the same request ID";
  if (flight.commands.some((c) => c.status === "reconciliation_required"))
    return "reconciliation required";
  if ((ledger.actions || []).some((a) => a.status === "pending"))
    return "pending mutation journal outcome requires reconciliation";
  if ((ledger.positions || []).some((r) => r.data.status !== "closed"))
    return "automation exposure unresolved";
  if (
    !allowProtectedSale &&
    (ledger.contracts || []).some((r) => r.data.accepted && !r.data.fulfilled)
  )
    return "active contract obligations uncosted";
  const owned = flight.commands.find(
    (c) => c.payload.ship === selectedShip && active(c.status),
  );
  if (owned) return `worker command #${owned.id} ${owned.status}`;
  return null;
}

function App() {
  const snapshot = useSyncExternalStore(subscribe, readSnapshot);
  const [page, setPage] = useState(currentPage);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const changed = () => {
      if (location.hash === "#page-title") return;
      setPage(currentPage());
      document.getElementById("page-title")?.focus();
    };
    window.addEventListener("hashchange", changed);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.removeEventListener("hashchange", changed);
      clearInterval(clock);
    };
  }, []);
  useEffect(() => {
    showPage(page);
  }, [page]);

  const { ledger, flight } = snapshot;
  const commands =
    flight && ledger.scope === flight.settings.scope ? flight.commands : [];
  const uncertain = commands.filter(
    (c) => c.status === "reconciliation_required",
  );
  const pending = (ledger.actions || []).filter((a) => a.status === "pending");
  const settings = flight?.settings;
  const heartbeat = elapsed(settings?.heartbeat, now);
  const livenessUnknown = !settings || heartbeat === null || heartbeat > 15;
  const credit = ledger.credits?.at(-1);
  const ships = ledger.ships || [];
  const selected = ships.find((s) => s.key === snapshot.selectedShip);
  const obligations = (ledger.contracts || []).filter(
    (c) => c.data.accepted && !c.data.fulfilled,
  );
  const block = commandBlock(snapshot);
  const ownership = block
    ? `Inspection only · ${block}`
    : ledger.paused || settings?.paused
      ? "STOP requested · queued work waits for explicit resume"
      : "Manual requests use the worker · authority and reserves revalidated at dispatch";
  useEffect(() => {
    setManualAvailability(block || (!selected ? "Select a ship first" : null));
  }, [block, selected]);

  return (
    <>
      {createPortal(
        <nav className="ui-nav" aria-label="Main navigation">
          {Object.entries(pages).map(([key, label]) => (
            <a
              key={key}
              href={`#/${key}`}
              aria-current={page === key ? "page" : undefined}
            >
              {label}
            </a>
          ))}
        </nav>,
        document.getElementById("ui-navigation")!,
      )}
      <div className="ui-states" aria-label="Independent state dimensions">
        <Status label="Observation freshness">
          <Freshness stamp={credit?.observed_at} now={now} />
          <div>Account observation; entity/detail dates may differ.</div>
        </Status>
        <Status
          label="Worker liveness"
          attention={snapshot.managed && livenessUnknown}
        >
          {!snapshot.managed ? (
            "Not monitored · recorded ledger only"
          ) : !settings ? (
            "Unknown · no worker report"
          ) : (
            <>
              {livenessUnknown
                ? "Unknown · stale or missing heartbeat"
                : "Recent heartbeat"}
              <br />
              {settings.mode === "demo"
                ? "SYNTHETIC OFFLINE WORLD"
                : "LIVE ADAPTER"}{" "}
              · {settings.paused ? "PAUSED" : settings.worker_state}
              <details>
                <summary>Worker evidence</summary>
                {settings.scope}
                <br />
                {settings.heartbeat || "Never observed"}
              </details>
            </>
          )}
        </Status>
        <Status
          label="Mutation certainty"
          attention={
            !!(uncertain.length || pending.length || snapshot.pending)
          }
        >
          {!ledger.scope ||
          (snapshot.managed && (!flight || ledger.scope !== settings?.scope))
            ? "Unknown · scope or matching command report unavailable"
            : `${uncertain.length} reconciliation required`}
          {ledger.scope && <> · {pending.length} pending journal entries</>}
          {snapshot.pending ? " · submission outcome unknown" : ""}
          <br />
          <a href="#/operations">Inspect commands and journal</a>
          <br />
          Reported records only; not an all-clear.
        </Status>
      </div>
      {snapshot.error && (
        <p className="ui-warning" role="status">
          Update unavailable: {snapshot.error}. Retained observations keep
          their original dates; worker liveness and outcomes may be unknown.
        </p>
      )}
      {(ledger.paused || uncertain.length > 0 || pending.length > 0) && (
        <p className="ui-warning">
          {ledger.paused ? "STOP requested. " : "Outcome review needed. "}STOP
          cannot cancel a dispatched request. Inspect queued work and uncertain
          outcomes in <a href="#/operations">Operations</a> before resuming.
        </p>
      )}
      <h1 id="page-title" tabIndex={-1}>
        {pages[page]}
      </h1>
      <p className="ui-intent">{descriptions[page]}</p>
      {deferred[page] && <p className="ui-deferred">{deferred[page]}</p>}
      {page === "markets" && <Trading snapshot={snapshot} now={now} />}
      {shipPages.includes(page) &&
        createPortal(
          <>
            <p id="ship-ownership" className="small">
              {ownership}
            </p>
            {selected && (
              <p className="small">
                {selected.data.nav.waypointSymbol} · {selected.data.nav.status}{" "}
                · Fuel {selected.data.fuel.current}/
                {selected.data.fuel.capacity} · Cargo{" "}
                {selected.data.cargo.units}/{selected.data.cargo.capacity}
                <br />
                <Freshness stamp={selected.observed_at} now={now} />
              </p>
            )}
          </>,
          document.getElementById("ship-context-summary")!,
        )}
      <div hidden={page !== "overview"} id="page-overview">
        <div className="ui-columns">
          <Panel title="What needs attention?">
            {!ledger.scope ? (
              <EmptyState>
                Log in if required, then select a reset/agent scope. Refresh
                ledger retries stored observations.
              </EmptyState>
            ) : (
              <>
                <p>
                  {obligations.length} recorded active contract obligations.
                  Uncosted obligations are not zero; fixed-floor headroom
                  excludes fuel and contracts.
                </p>
                {snapshot.managed && livenessUnknown && (
                  <p className="ui-warning">
                    Worker liveness is unknown. A fresh ledger does not prove
                    that work stopped. Request STOP if activity is unwanted and
                    inspect Operations; do not infer safety from silence.
                  </p>
                )}
                <p>
                  <a href="#/contracts">Inspect obligations</a> ·{" "}
                  <a href="#/reports">Review cash and open positions</a>
                </p>
              </>
            )}
          </Panel>
          <Panel title="Recent work">
            {commands.length ? (
              commands.slice(0, 5).map((c) => (
                <EntitySummary
                  key={c.id}
                  name={`#${c.id} ${c.payload.kind}`}
                  state={c.status.toUpperCase()}
                >
                  <p>{c.detail}</p>
                  <p className="small">Updated {c.updated_at}</p>
                </EntitySummary>
              ))
            ) : (
              <EmptyState>
                No command records available for this scope. Historical
                activity remains in Reports and Operations.
              </EmptyState>
            )}
            <a href="#/operations">Open command evidence and recovery</a>
          </Panel>
        </div>
        <Panel title="Fleet check-in">
          {!ships.length && (
            <EmptyState>No stored ship observations in this scope.</EmptyState>
          )}
          <div className="ui-columns">
            {ships.map(({ key, data: ship, observed_at }) => (
              <EntitySummary
                key={key}
                name={ship.symbol}
                state={ship.nav.status}
              >
                <p>
                  {ship.nav.waypointSymbol}
                  {ship.nav.status === "IN_TRANSIT" && (
                    <>
                      {" "}
                      →{" "}
                      {ship.nav.route?.destination?.symbol ||
                        "unknown destination"}
                      <br />
                      Arrival {ship.nav.route?.arrival || "unknown"}; estimate,
                      observation required.
                    </>
                  )}
                </p>
                <p className="small">
                  Fuel {ship.fuel.current}/{ship.fuel.capacity} · Cargo{" "}
                  {ship.cargo.units}/{ship.cargo.capacity} · Cooldown{" "}
                  {ship.cooldown.remainingSeconds}s at observation
                </p>
                <p className="small">
                  <Freshness stamp={observed_at} now={now} />
                </p>
                <a href="#/fleet">Inspect fleet</a> ·{" "}
                <a href="#/explorer">Explore and fly</a>
              </EntitySummary>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}

migratePanels();
showPage(currentPage());
createRoot(document.getElementById("ui-root")!).render(<App />);
