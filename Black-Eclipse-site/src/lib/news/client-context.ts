// ─── Client-side personal context for news ranking ──────────────────────────
// The watchlist lives in localStorage; holdings live in the Python portfolio
// engine. This helper reads BOTH best-effort so the news tab can rank stories
// by what the user actually follows/holds. It never invents symbols: a failed
// or unavailable portfolio read simply contributes nothing.

import { listEnginePortfolios, readPortfolio } from "@/lib/portfolio/engine-read";

/** Watchlist symbols already stored under the shared watchlist key. */
export function readWatchlistSymbols(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem("watchlist_guest");
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return (Array.isArray(parsed) ? parsed : [])
      .map((w: { symbol?: string }) => String(w.symbol || "").toUpperCase())
      .filter(Boolean)
      .slice(0, 100);
  } catch {
    return [];
  }
}

/**
 * Best-effort holdings symbols from the portfolio engine. Bounded to the first
 * few funds so opening the news tab never fans out into an expensive scan.
 */
export async function loadPortfolioSymbols(maxFunds = 2): Promise<string[]> {
  try {
    const funds = await listEnginePortfolios();
    const symbols = new Set<string>();
    for (const fund of funds.slice(0, maxFunds)) {
      const res = await readPortfolio(fund.id, "holdings");
      if (!res.ok || !res.data) continue;
      for (const p of res.data.positions ?? []) {
        if (p.symbol) symbols.add(String(p.symbol).toUpperCase());
      }
    }
    return Array.from(symbols).slice(0, 200);
  } catch {
    return [];
  }
}
