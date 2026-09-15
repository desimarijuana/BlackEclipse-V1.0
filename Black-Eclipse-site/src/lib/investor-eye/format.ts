// ── Investor Eye — formatting helpers (client-safe) ──────────────────────────
// Kept free of server imports so client components can use them without pulling
// Prisma (and `better-sqlite3`) into the browser bundle.

/** ISO timestamp → 'HH:MM UTC'. */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${hh}:${mm} UTC`;
  } catch {
    return iso;
  }
}

/** Signed percentage, e.g. '+1.24%'. */
export function formatPct(value: number | undefined | null): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}
