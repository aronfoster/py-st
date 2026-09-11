/** Temporary boundary: only this module knows the legacy panel DOM/API. */
export interface Observation<T> {
  key: string;
  observed_at?: string;
  data: T;
}

export interface Ship {
  symbol: string;
  nav: {
    status: string;
    waypointSymbol: string;
    route?: {
      arrival?: string;
      destination?: { symbol: string };
    };
  };
  fuel: { current: number; capacity: number };
  cargo: {
    units: number;
    capacity: number;
    inventory?: { symbol: string; units: number }[];
  };
  cooldown: { remainingSeconds: number };
}

export interface Command {
  id: number;
  status: string;
  detail: string;
  updated_at: string;
  payload: { kind: string; ship?: string };
}

export interface Snapshot {
  ledger: {
    scope?: string;
    paused?: boolean;
    credits?: { observed_at: string; credits: number }[];
    ships?: Observation<Ship>[];
    contracts?: Observation<{ accepted: boolean; fulfilled: boolean }>[];
    positions?: Observation<{ status: string }>[];
    actions?: {
      id: number;
      status: string;
      path: string;
      started_at: string;
    }[];
    markets?: Observation<{
      symbol: string;
      exports: { symbol: string }[];
      imports: { symbol: string }[];
      exchange: { symbol: string }[];
      tradeGoods?: {
        symbol: string;
        purchasePrice?: number;
        sellPrice?: number;
        tradeVolume?: number;
      }[];
    }>[];
  };
  flight: {
    settings: {
      scope: string;
      mode: string;
      paused: boolean;
      worker_state: string;
      heartbeat: string | null;
    };
    commands: Command[];
  } | null;
  selectedShip: string;
  managed: boolean;
  authenticated: boolean;
  pending: boolean;
  submitting: boolean;
  error: string;
}

declare global {
  interface Window {
    ledgerUI: {
      snapshot: Snapshot;
      previewTrade: (body: object) => Promise<TradePreview>;
      submitCommand: (payload: object) => Promise<Command>;
    };
  }
}

export interface TradePreview {
  kind: "purchase" | "sell";
  ship: string;
  good: string;
  units: number;
  waypoint: string;
  unit_price: number | null;
  total_price: number | null;
  trade_volume: number | null;
  credits_before: number;
  credits_after: number | null;
  cargo_before: number;
  cargo_after: number;
  cargo_capacity: number;
  fixed_floor: number;
  fuel_reserve: number;
  fixed_floor_headroom: number;
  protected_contract_cargo: Record<string, number>;
  open_contract_obligations: boolean;
  contract_state_unknown: boolean;
  sellable_units: number;
  observed_at: string | null;
  stale: boolean;
  estimated: boolean;
  feasible: boolean;
  reason: string;
}

export const pages = {
  overview: "Overview",
  explorer: "Explorer",
  fleet: "Fleet",
  markets: "Markets",
  contracts: "Contracts",
  automation: "Automation",
  reports: "Reports",
  operations: "Operations",
} as const;
export type Page = keyof typeof pages;
export const shipPages: Page[] = [
  "explorer",
  "fleet",
  "markets",
  "contracts",
  "automation",
];

export const readSnapshot = () => window.ledgerUI.snapshot;
export function subscribe(callback: () => void) {
  document.addEventListener("ledger-ui", callback);
  return () => document.removeEventListener("ledger-ui", callback);
}

function legacyElement(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Legacy panel missing: ${id}`);
  return element;
}

/** Move each whole legacy panel once; React never owns their descendants. */
export function migratePanels() {
  const destinations: Record<Exclude<Page, "overview">, string[]> = {
    explorer: ["map", "flight-controls"],
    fleet: ["fleet"],
    markets: ["market-select", "routes", "markets"],
    contracts: ["contracts", "contract-select"],
    automation: ["automation-runs", "plans"],
    reports: ["chart", "cash"],
    operations: ["command-panel", "doctor-check", "journal"],
  };
  const host = legacyElement("legacy-pages");
  legacyElement("command-panel").prepend(legacyElement("flight-heartbeat"));
  for (const [page, ids] of Object.entries(destinations)) {
    const section = document.createElement("div");
    section.hidden = true;
    section.dataset.page = page;
    section.id = `page-${page}`;
    for (const id of ids) {
      const panel = legacyElement(id).closest("section");
      if (!panel) throw new Error(`Legacy section missing for: ${id}`);
      section.append(panel);
    }
    host.append(section);
  }
  // Empty grid containers only; every child panel was inventoried above.
  document.querySelectorAll("main > .grid:empty").forEach((n) => n.remove());
}

export function showPage(page: Page) {
  document.querySelectorAll<HTMLElement>("[data-page]").forEach((panel) => {
    panel.hidden = panel.dataset.page !== page;
  });
  document.getElementById("shared-ship-context")!.hidden =
    !shipPages.includes(page);
}

/** Presentation guard only. The worker remains the execution authority. */
export function setManualAvailability(reason: string | null) {
  for (const id of [
    "flight-trip",
    "flight-orbit",
    "flight-dock",
    "flight-refuel",
  ]) {
    const button = document.getElementById(id) as HTMLButtonElement;
    button.disabled = reason !== null;
    button.title = reason || "Submit to the guarded worker";
    button.setAttribute("aria-describedby", "ship-ownership");
  }
}
