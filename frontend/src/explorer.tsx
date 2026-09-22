import { useEffect, useMemo, useRef, useState } from "react";
import { select } from "d3-selection";
import {
  zoom,
  zoomIdentity,
  type ZoomBehavior,
  type ZoomTransform,
} from "d3-zoom";
import type { Explorer as ExplorerData, Snapshot, Waypoint } from "./bridge";

type Group = { x: number; y: number; members: Waypoint[] };
const coordinates = (w: Waypoint) =>
  Number.isInteger(w.x) && Number.isInteger(w.y);
const short = (w: Waypoint) => w.symbol.split("-").at(-1) || w.symbol;
const distance = (a: Waypoint, b?: Waypoint) =>
  b && coordinates(a) && coordinates(b)
    ? Math.max(1, Math.ceil(Math.hypot(a.x! - b.x!, a.y! - b.y!)))
    : null;
const goods = (w: Waypoint) => w.market?.data;
const quoteAge = (stamp?: string) => {
  const time = stamp ? Date.parse(stamp) : NaN;
  if (!Number.isFinite(time)) return "age unknown";
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  return `${minutes}m old · ${minutes >= 15 ? "stale" : "recent"}`;
};
const fuel = (w: Waypoint) => {
  const data = goods(w);
  const priced = data?.tradeGoods?.find(
    (g) =>
      g.symbol === "FUEL" &&
      Number.isInteger(g.purchasePrice) &&
      g.purchasePrice! > 0,
  );
  if (priced)
    return `Fuel ${priced.purchasePrice} cr (${quoteAge(w.market?.observed_at)})`;
  if (
    [
      ...(data?.exports || []),
      ...(data?.imports || []),
      ...(data?.exchange || []),
    ].some((g) => g.symbol === "FUEL")
  )
    return "Fuel listed; price unknown";
  if (data && Array.isArray(data.tradeGoods))
    return "Fuel not listed in observed goods";
  return w.has_market
    ? "Fuel unknown; market goods not observed"
    : "No market evidence";
};
function stacks(points: Waypoint[]): Group[] {
  const byPosition = new Map<string, Group>();
  for (const w of points) {
    if (!coordinates(w)) continue;
    const key = `${w.x},${w.y}`;
    if (!byPosition.has(key))
      byPosition.set(key, { x: w.x!, y: w.y!, members: [] });
    byPosition.get(key)!.members.push(w);
  }
  return [...byPosition.values()].map((g) => ({
    ...g,
    members: g.members.sort((a, b) => a.symbol.localeCompare(b.symbol)),
  }));
}
function clusters(groups: Group[], project: (g: Group) => [number, number]) {
  const result: Group[][] = [];
  const ordered = [...groups].sort(
    (a, b) =>
      Math.max(...b.members.map(priority)) -
        Math.max(...a.members.map(priority)) ||
      a.members[0].symbol.localeCompare(b.members[0].symbol),
  );
  const remaining = new Set(ordered);
  for (const leader of ordered) {
    if (!remaining.delete(leader)) continue;
    const [x, y] = project(leader);
    const cluster = [leader];
    for (const candidate of ordered) {
      if (!remaining.has(candidate)) continue;
      const [cx, cy] = project(candidate);
      if (Math.hypot(x - cx, y - cy) < 32) {
        cluster.push(candidate);
        remaining.delete(candidate);
      }
    }
    result.push(cluster);
  }
  return result;
}
function priority(w: Waypoint) {
  return w.has_jump_gate
    ? 5
    : w.has_shipyard
      ? 4
      : w.has_market
        ? 3
        : w.traits?.length
          ? 2
          : 1;
}
const evidence = (w: Waypoint) =>
  [
    w.has_market && "Marketplace",
    w.has_shipyard && "Shipyard",
    w.has_jump_gate && "Jump gate",
    w.traits?.some((t) => /DEPOSITS|POOLS|CRYSTALS|GASES/.test(t)) &&
      "Resource traits",
  ]
    .filter(Boolean)
    .join(" · ") || "No facility evidence";

function SystemMap({
  points,
  selected,
  ship,
  onSelect,
}: {
  points: Waypoint[];
  selected: string;
  ship?: string;
  onSelect: (w: Waypoint) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const behavior = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [size, setSize] = useState<[number, number]>([700, 420]);
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  const groups = useMemo(() => stacks(points), [points]);
  const bounds = useMemo(() => {
    const xs = groups.map((g) => g.x),
      ys = groups.map((g) => g.y);
    return {
      minX: Math.min(0, ...xs),
      maxX: Math.max(0, ...xs),
      minY: Math.min(0, ...ys),
      maxY: Math.max(0, ...ys),
    };
  }, [groups]);
  const [width, height] = size;
  const spanX = Math.max(1, bounds.maxX - bounds.minX);
  const spanY = Math.max(1, bounds.maxY - bounds.minY);
  const base = Math.min((width - 64) / spanX, (height - 64) / spanY);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const project = (g: Group): [number, number] => [
    transform.applyX(width / 2 + (g.x - centerX) * base),
    transform.applyY(height / 2 - (g.y - centerY) * base),
  ];
  const moves = (next: ZoomTransform) => {
    if (svg.current && behavior.current)
      select(svg.current).call(behavior.current.transform, next);
  };
  useEffect(() => {
    if (!svg.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.max(320, Math.round(entry.contentRect.width));
      const h = Math.max(280, Math.round(entry.contentRect.height));
      setSize([w, h]);
    });
    observer.observe(svg.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!svg.current) return;
    const z = zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, 1024])
      .clickDistance(4)
      .on("zoom", (event) => setTransform(event.transform));
    behavior.current = z;
    const selection = select(svg.current);
    selection.call(z).on("dblclick.zoom", null);
    return () => {
      selection.on(".zoom", null);
      behavior.current = null;
    };
  }, []);
  const rendered = clusters(groups, project);
  const visibleLabels: {
    x: number;
    y: number;
    width: number;
    name: string;
  }[] = [];
  const labels = rendered.map((cluster) => {
    const g = cluster[0];
    const [x, y] = project(g);
    const member =
      g.members.find((w) => w.symbol === selected) || g.members[0];
    const name =
      short(member) +
      (cluster.flatMap((c) => c.members).length > 1
        ? ` +${cluster.flatMap((c) => c.members).length - 1}`
        : "");
    const length = name.length * 7 + 12;
    const important = cluster.some((c) =>
      c.members.some((w) => w.symbol === selected || w.symbol === ship),
    );
    if (
      !important &&
      (x < 10 ||
        x + length + 16 > width ||
        y < 12 ||
        y > height - 12 ||
        visibleLabels.some(
          (r) =>
            Math.abs(r.y - y) < 20 &&
            x + 16 < r.x + r.width &&
            x + 16 + length > r.x,
        ))
    )
      return null;
    visibleLabels.push({ x: x + 16, y, width: length, name });
    return name;
  });
  return (
    <div className="ui-map-wrap">
      <div className="ui-map-controls">
        <button
          type="button"
          onClick={() =>
            behavior.current &&
            svg.current &&
            select(svg.current).call(behavior.current.scaleBy, 1.8)
          }
        >
          Zoom in
        </button>
        <button
          type="button"
          onClick={() =>
            behavior.current &&
            svg.current &&
            select(svg.current).call(behavior.current.scaleBy, 1 / 1.8)
          }
        >
          Zoom out
        </button>
        <button type="button" onClick={() => moves(zoomIdentity)}>
          Fit system
        </button>
        <button
          type="button"
          onClick={() => {
            const g = groups.find((g) =>
              g.members.some((w) => w.symbol === selected),
            );
            if (g) {
              const [x, y] = project(g);
              moves(
                zoomIdentity
                  .translate(
                    width / 2 - x + transform.x,
                    height / 2 - y + transform.y,
                  )
                  .scale(transform.k),
              );
            }
          }}
        >
          Focus selection
        </button>
        <button
          type="button"
          onClick={() => {
            const g = groups.find((g) =>
              g.members.some((w) => w.symbol === ship),
            );
            if (g) {
              const [x, y] = project(g);
              moves(
                zoomIdentity
                  .translate(
                    width / 2 - x + transform.x,
                    height / 2 - y + transform.y,
                  )
                  .scale(transform.k),
              );
            }
          }}
        >
          Focus ship
        </button>
      </div>
      <p className="small">
        Wheel or pinch to zoom; drag to pan. Keyboard: use the waypoint list.
      </p>
      <svg
        ref={svg}
        id="map"
        className="ui-system-map"
        viewBox={`0 0 ${width} ${height}`}
        data-zoom-k={transform.k}
        aria-hidden="true"
      >
        {rendered.map((cluster, index) => {
          const g = cluster[0],
            [x, y] = project(g),
            members = cluster.flatMap((c) => c.members);
          const chosen = members.some((w) => w.symbol === selected),
            atShip = members.some((w) => w.symbol === ship);
          return (
            <g
              key={`${g.x},${g.y}`}
              data-stack={cluster.length === 1 ? members.length : undefined}
              data-cluster={cluster.length > 1 ? members.length : undefined}
              onClick={() => {
                if (cluster.length > 1) {
                  const next = Math.min(1024, transform.k * 2.5);
                  moves(
                    zoomIdentity
                      .translate(
                        width / 2 - ((x - transform.x) * next) / transform.k,
                        height / 2 - ((y - transform.y) * next) / transform.k,
                      )
                      .scale(next),
                  );
                } else
                  onSelect(
                    g.members.find((w) => w.symbol === selected) ||
                      g.members[0],
                  );
              }}
            >
              <circle
                cx={x}
                cy={y}
                r={chosen || atShip ? 16 : 13}
                className={
                  chosen
                    ? "ui-map-selected"
                    : atShip
                      ? "ui-map-ship"
                      : "ui-map-marker"
                }
              />
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                className="ui-map-count"
              >
                {members.length > 1 ? members.length : ""}
              </text>
              {labels[index] && (
                <text x={x + 16} y={y + 4} className="ui-map-label">
                  {labels[index]}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function Explorer({ snapshot }: { snapshot: Snapshot }) {
  const data: ExplorerData = snapshot.ledger.explorer || {
    systems: [],
    ships: [],
  };
  const system = data.systems.find(
    (s) => s.symbol === snapshot.selectedSystem,
  );
  const points = system?.waypoints || [];
  const selected = points.find((w) => w.symbol === snapshot.selectedWaypoint);
  const ship = data.ships.find((s) => s.symbol === snapshot.selectedShip);
  const shipTarget =
    ship?.status === "IN_TRANSIT" ? ship.destination : ship?.waypoint;
  const origin = points.find((w) => w.symbol === shipTarget);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [filters, setFilters] = useState<string[]>([]);
  const [sort, setSort] = useState("distance");
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const result = useMemo(
    () =>
      points
        .filter((w) => {
          const query = search.toLowerCase().replaceAll("_", " ");
          const haystack = [w.symbol, w.type, ...(w.traits || [])]
            .join(" ")
            .toLowerCase()
            .replaceAll("_", " ");
          return (
            (!query || haystack.includes(query)) &&
            (!type || w.type === type) &&
            filters.every((f) =>
              f === "market"
                ? w.has_market
                : f === "shipyard"
                  ? w.has_shipyard
                  : f === "fuel"
                    ? /Fuel (\d+ cr|listed)/.test(fuel(w))
                    : f === "gate"
                      ? w.has_jump_gate
                      : f === "resource"
                        ? w.traits?.some((t) =>
                            /DEPOSITS|POOLS|CRYSTALS|GASES/.test(t),
                          )
                        : snapshot.ledger.contracts?.some(
                            (c) =>
                              !c.data.fulfilled &&
                              c.data.terms.deliver.some(
                                (d) => d.destinationSymbol === w.symbol,
                              ),
                          ),
            )
          );
        })
        .sort((a, b) =>
          sort === "distance" && origin
            ? (distance(a, origin) ?? Infinity) -
                (distance(b, origin) ?? Infinity) ||
              a.symbol.localeCompare(b.symbol)
            : sort === "type"
              ? (a.type || "").localeCompare(b.type || "") ||
                a.symbol.localeCompare(b.symbol)
              : a.symbol.localeCompare(b.symbol),
        ),
    [points, search, type, filters, sort, origin, snapshot.ledger.contracts],
  );
  useEffect(() => {
    const index = result.findIndex((w) => w.symbol === selected?.symbol);
    if (index >= 0) refs.current[index]?.scrollIntoView({ block: "nearest" });
  }, [selected?.symbol]);
  const choose = (w: Waypoint) =>
    window.ledgerUI.selectExplorer({
      system: system!.symbol,
      waypoint: w.symbol,
    });
  const grouped =
    selected &&
    points.filter(
      (w) => coordinates(w) && w.x === selected.x && w.y === selected.y,
    );
  const previewBlock =
    !snapshot.managed || !snapshot.authenticated
      ? "Log in to preview a trip"
      : !ship
        ? "Select an owned ship"
        : ship.system !== system?.symbol
          ? "Ship is in another system"
          : shipTarget === selected?.symbol
            ? "Ship is already here"
            : null;
  return (
    <section className="ui-explorer" aria-labelledby="explorer-title">
      <div className="eyebrow">System explorer / stored observations only</div>
      <h2 id="explorer-title">Find a destination.</h2>
      <label>
        System{" "}
        <select
          id="system-select"
          value={system?.symbol || ""}
          onChange={(e) =>
            window.ledgerUI.selectExplorer({ system: e.target.value })
          }
        >
          {!data.systems.length && (
            <option value="">No observed systems</option>
          )}
          {data.systems.map((s) => (
            <option key={s.symbol} value={s.symbol}>
              {s.symbol}
            </option>
          ))}
        </select>
      </label>
      <p id="explorer-status" role="status" className="small">
        {system
          ? `${system.symbol}: ${points.length} observed waypoints; ${points.filter(coordinates).length} plotted. `
          : "No observed waypoint systems in this scope. "}
        {ship
          ? `${ship.symbol} ${ship.status === "IN_TRANSIT" ? "in transit toward" : "recorded at"} ${shipTarget || "unknown"}.`
          : "Select a ship to see its recorded location."}
      </p>
      <div className="ui-explorer-layout">
        <div className="ui-discovery">
          <div className="ui-search">
            <label htmlFor="waypoint-search">
              Find waypoint, type or trait
            </label>
            <input
              id="waypoint-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  refs.current[0]?.focus();
                }
              }}
              placeholder="Search destinations"
            />
          </div>
          <div className="ui-filters" aria-label="Destination filters">
            {(
              [
                ["market", "Marketplace"],
                ["fuel", "Fuel listed/priced"],
                ["shipyard", "Shipyard"],
                ["gate", "Jump gate"],
                ["resource", "Resource traits"],
                ["contract", "Contract destination"],
              ] as const
            ).map(([key, label]) => (
              <button
                type="button"
                key={key}
                aria-pressed={filters.includes(key)}
                onClick={() =>
                  setFilters(
                    filters.includes(key)
                      ? filters.filter((f) => f !== key)
                      : [...filters, key],
                  )
                }
              >
                {label}
              </button>
            ))}
          </div>
          <div className="ui-sort">
            <label>
              Type{" "}
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">All types</option>
                {[
                  ...new Set(
                    points.map((w) => w.type).filter((t): t is string => !!t),
                  ),
                ]
                  .sort()
                  .map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Sort{" "}
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="distance">Distance from ship</option>
                <option value="symbol">Symbol</option>
                <option value="type">Type</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setType("");
                setFilters([]);
              }}
            >
              Clear filters
            </button>
          </div>
          <p className="small" role="status">
            Showing {result.length} of {points.length}
          </p>
          {selected && !result.includes(selected) && (
            <button className="ui-waypoint" onClick={() => choose(selected)}>
              Selected, hidden by filters: {selected.symbol}
            </button>
          )}
          <div
            id="waypoint-list"
            className="ui-waypoint-list"
            aria-label="Observed waypoints"
          >
            {result.map((w, i) => (
              <button
                key={w.symbol}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                type="button"
                className="ui-waypoint"
                aria-current={w.symbol === selected?.symbol}
                tabIndex={i === 0 ? 0 : -1}
                onKeyDown={(e) => {
                  const next =
                    e.key === "ArrowDown"
                      ? i + 1
                      : e.key === "ArrowUp"
                        ? i - 1
                        : e.key === "Home"
                          ? 0
                          : e.key === "End"
                            ? result.length - 1
                            : -1;
                  if (next >= 0 && next < result.length) {
                    e.preventDefault();
                    refs.current[next]?.focus();
                  }
                }}
                onClick={() => choose(w)}
              >
                <strong>{w.symbol}</strong> · {w.type || "unknown"}{" "}
                {distance(w, origin) !== null &&
                  `· ${distance(w, origin)} units`}
                <br />
                <span>
                  {evidence(w)} · {fuel(w)}
                </span>
              </button>
            ))}
            {!result.length && (
              <p>
                No stored observation matches these filters. Markets and traits
                not yet observed may still match.
              </p>
            )}
          </div>
        </div>
        <div id="waypoint-detail" className="ui-destination-detail">
          {selected ? (
            <>
              <h3>{selected.symbol}</h3>
              <p>
                {selected.type || "Type unknown"} · Coordinates{" "}
                {coordinates(selected)
                  ? `${selected.x}, ${selected.y}`
                  : "not observed"}{" "}
                ·{" "}
                {shipTarget === selected.symbol
                  ? "Ship here"
                  : distance(selected, origin) !== null
                    ? `${distance(selected, origin)} units from ${ship?.status === "IN_TRANSIT" ? "ship destination" : "ship"}`
                    : "Distance unknown"}
              </p>
              <p>
                {evidence(selected)}. Traits:{" "}
                {selected.traits === null
                  ? "not observed"
                  : selected.traits.length
                    ? selected.traits.join(", ")
                    : "observed empty"}
                . Waypoint observed {selected.observed_at || "time unknown"}.
              </p>
              {selected.orbits && <p>Orbits {selected.orbits}</p>}
              {selected.under_construction && <p>Under construction</p>}
              {selected.modifiers?.length ? (
                <p>Modifiers: {selected.modifiers.join(", ")}</p>
              ) : null}
              {selected.has_market && (
                <>
                  <h4>Marketplace</h4>
                  <p>
                    {selected.market
                      ? `Observed ${selected.market.observed_at || "time unknown"}`
                      : "Marketplace trait only; goods and prices unknown"}
                    . {fuel(selected)}.
                  </p>
                  <p>
                    Goods:{" "}
                    {[
                      ...(goods(selected)?.exports || []),
                      ...(goods(selected)?.imports || []),
                      ...(goods(selected)?.exchange || []),
                    ]
                      .map((g) => g.symbol)
                      .join(", ") || "not observed"}
                    .
                  </p>
                  {goods(selected)?.tradeGoods?.length ? (
                    <p>
                      Prices:{" "}
                      {goods(selected)!
                        .tradeGoods!.map(
                          (g) =>
                            `${g.symbol} buy ${g.purchasePrice ?? "unknown"}, sell ${g.sellPrice ?? "unknown"}`,
                        )
                        .join("; ")}
                      . Prices may be stale; check the observation time.
                    </p>
                  ) : (
                    <p>Detailed prices unknown.</p>
                  )}
                  <a href="#/markets">Inspect Markets</a>
                </>
              )}
              {selected.has_shipyard && (
                <p>
                  Shipyard:{" "}
                  {selected.shipyard
                    ? `observed ${selected.shipyard.observed_at || "time unknown"}; ${(selected.shipyard.data.shipTypes || []).map((s) => s.type).join(", ") || "advertised types unknown"}`
                    : "trait only; offerings and prices unknown"}
                  .
                </p>
              )}
              {selected.has_jump_gate && (
                <p>
                  Jump gate:{" "}
                  {selected.jump_gate
                    ? `observed ${selected.jump_gate.observed_at || "time unknown"}`
                    : "connections unknown"}
                  .
                </p>
              )}
              {snapshot.ledger.contracts
                ?.filter(
                  (c) =>
                    !c.data.fulfilled &&
                    c.data.terms.deliver.some(
                      (d) => d.destinationSymbol === selected.symbol,
                    ),
                )
                .map((c) => (
                  <p key={c.key}>
                    Contract {c.key}:{" "}
                    {c.data.terms.deliver
                      .filter((d) => d.destinationSymbol === selected.symbol)
                      .map(
                        (d) =>
                          `${d.tradeSymbol} ${d.unitsFulfilled}/${d.unitsRequired}`,
                      )
                      .join(", ")}{" "}
                    · {c.data.accepted ? "accepted" : "offered"}.{" "}
                    <a href="#/contracts">Inspect Contracts</a>
                  </p>
                ))}
              {grouped && grouped.length > 1 && (
                <div className="ui-colocated">
                  <h4>Same coordinates · choose a waypoint</h4>
                  {grouped.map((w) => (
                    <button
                      type="button"
                      key={w.symbol}
                      aria-current={w.symbol === selected.symbol}
                      onClick={() => choose(w)}
                    >
                      {w.symbol} · {w.type || "unknown"}
                      {w.orbits ? ` · orbits ${w.orbits}` : ""}
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                disabled={!!previewBlock}
                title={previewBlock || "Preview the selected trip"}
                onClick={async () => {
                  await window.ledgerUI.previewTrip();
                  document
                    .getElementById("flight-controls")
                    ?.scrollIntoView({ block: "start" });
                  document.getElementById("flight-preview")?.focus();
                }}
              >
                Preview trip from {ship?.symbol || "selected ship"}
              </button>
              {previewBlock && <p className="small">{previewBlock}</p>}
            </>
          ) : (
            <p>Select a waypoint in the list or on the map.</p>
          )}
        </div>
        <details
          className="ui-map-panel"
          open={typeof window !== "undefined" && window.innerWidth > 800}
        >
          <summary>
            System map · {points.filter(coordinates).length} plotted
          </summary>
          <SystemMap
            key={`${snapshot.ledger.scope}:${system?.symbol}`}
            points={points}
            selected={selected?.symbol || ""}
            ship={shipTarget}
            onSelect={choose}
          />
        </details>
      </div>
    </section>
  );
}
