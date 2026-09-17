// ── Journal date formatting ──────────────────────────────────────────────────
// Journal dates are UTC everywhere: `Trade.exitTime` is sliced to `YYYY-MM-DD`
// for day keys, `JournalDay.date` is stored at UTC midnight, and `aggregateDays`
// groups by the UTC slice of the exit time. Any formatter that renders those
// keys MUST therefore format in UTC too.
//
// Using `toLocaleString`/`toLocaleDateString` without a `timeZone` formats in
// the BROWSER's local zone. For `new Date(Date.UTC(2026, 8, 1))` (Sept 1 UTC)
// that renders "August 2026" west of Greenwich — the month label sits one month
// behind the grid it describes.

/** "September 2026" for a (year, 0-indexed month) pair, in UTC. */
export function formatMonthLabel(year: number, month: number): string {
  return new Date(Date.UTC(year, month, 1)).toLocaleString('en', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** "September 16, 2026" for a `YYYY-MM-DD` key, in UTC. */
export function formatDayLabel(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/** Short weekday ("Mon") for a `YYYY-MM-DD` key, in UTC. */
export function weekdayShort(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return '';
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en', { weekday: 'short', timeZone: 'UTC' });
}
