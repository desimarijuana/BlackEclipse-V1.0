// ── Quick alert (client) ────────────────────────────────────────────────────
// Creates a price alert for a single symbol without opening the full alert
// builder. Used by the command palette's parameterized commands
// (`alert AAPL`, `watch AAPL`) so they do real work instead of re-querying.
//
// The alert uses the existing PriceAlert engine via `POST /api/alerts` with a
// CHANGE_PCT condition — the same shape the alert builder produces, so it shows
// up in the Alerts screen like any other watch.

export interface QuickAlertResult {
  ok: boolean;
  error?: string;
}

/**
 * Create a simple "±move%" alert for one symbol. `movePct` defaults to 3%.
 * Never throws — returns `{ ok:false, error }` so callers can surface a toast.
 */
export async function createQuickAlert(symbol: string, movePct = 3): Promise<QuickAlertResult> {
  const ticker = symbol.trim().toUpperCase();
  if (!ticker) return { ok: false, error: 'no symbol' };

  try {
    const res = await fetch('/api/alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `${ticker} moves ±${movePct}%`,
        symbols: [ticker],
        // CHANGE_PCT is signed, so one OR group covers both directions.
        conditions: [
          { indicator: 'CHANGE_PCT', operator: '>=', compareMode: 'value', value: movePct },
          { indicator: 'CHANGE_PCT', operator: '<=', compareMode: 'value', value: -movePct },
        ],
        logic: 'OR',
        timeframe: '1d',
        dataSource: 'Auto',
        intervalSec: 60,
        cooldownMin: 15,
        actions: { toast: true },
        active: true,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return { ok: false, error: data?.error || `HTTP ${res.status}` };
    }
    // Tell any mounted Alerts screen (keep-alive tab) to re-list.
    try {
      window.dispatchEvent(new CustomEvent('be:alerts-changed'));
    } catch { /* non-browser — ignore */ }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'network error' };
  }
}
