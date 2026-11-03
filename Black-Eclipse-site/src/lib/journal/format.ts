// ── Journal formatting helpers (server-safe, no React) ───────────────────────

/** Format an R value with sign, e.g. +2.4R. */
export function fmtR(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
}

/** Format a price with clean precision: trims float noise, keeps significant digits. */
export function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  // 10 significant digits erases 3932.2900000000004 → 3932.29 while leaving
  // FX precision (1.11621) and JPY pairs (149.123) intact.
  return String(Number(v.toPrecision(10)));
}

/**
 * Journal timestamps are UTC everywhere (see docs/ARCHITECTURE.md). Show the
 * date AND the time — a trade table that only shows the day hides when the
 * trade actually happened.
 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  return new Date(t).toISOString().slice(0, 16).replace("T", " ");
}

/** Just the UTC clock of a timestamp, e.g. 14:05. */
export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  return new Date(t).toISOString().slice(11, 16);
}

/** Format a currency value compactly with sign. */
export function fmtMoney(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}
