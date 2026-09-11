import type { ReactNode } from "react";

export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="ui-panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function Status({
  label,
  children,
  attention = false,
}: {
  label: string;
  children: ReactNode;
  attention?: boolean;
}) {
  return (
    <div className={`ui-status${attention ? " attention" : ""}`}>
      <strong>{label}</strong>
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function EntitySummary({
  name,
  state,
  children,
}: {
  name: string;
  state: string;
  children: ReactNode;
}) {
  return (
    <article className="ui-entity">
      <div className="ship-top">
        <strong>{name}</strong>
        <span>{state}</span>
      </div>
      {children}
    </article>
  );
}

/** Unknown/future dates cannot provide freshness or liveness evidence. */
export function elapsed(stamp: string | null | undefined, now: number) {
  if (
    !stamp ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      stamp,
    )
  )
    return null;
  const parsed = Date.parse(stamp);
  if (
    !Number.isFinite(parsed) ||
    parsed > now ||
    new Date(stamp.slice(0, 10) + "T00:00:00Z").toISOString().slice(0, 10) !==
      stamp.slice(0, 10)
  )
    return null;
  return Math.floor((now - parsed) / 1000);
}

export function Freshness({ stamp, now }: { stamp?: string; now: number }) {
  const seconds = elapsed(stamp, now);
  return (
    <span>
      {seconds === null
        ? "Unknown observation age"
        : `${Math.floor(seconds / 60)}m old · ${seconds > 900 ? "stale" : "recent stored, not live"}`}
      <br />
      {stamp || "No timestamp"}
    </span>
  );
}
