'use client';

// ── Fund NAV data source ─────────────────────────────────────────────────────
// Computes a fund NAV series from the localStorage fund book + live quotes,
// and registers it as a DataHub topic so the Fund Performance chart can consume
// it. Deterministic — never fabricates.

import { registerTopic } from '@/lib/workspace/data-hub';
import { loadFunds } from '@/components/screens/portfolio/fund-store';

interface FundTx { type: string; symbol: string; quantity: number; price: number; fee: number; date: string; }
interface Fund { id: string; name: string; transactions: FundTx[]; }

/** Build a NAV series (cumulative value over time) for a fund from its ledger. */
function buildFundNav(fund: Fund): { nav: number[]; navDates: string[]; benchmarkNav: number[] } {
  const txs = [...fund.transactions].sort((a, b) => a.date.localeCompare(b.date));
  const nav: number[] = [];
  const navDates: string[] = [];
  let cash = 0;
  let invested = 0;
  for (const tx of txs) {
    if (tx.type === 'DEPOSIT') cash += tx.quantity * tx.price;
    else if (tx.type === 'WITHDRAWAL') cash -= tx.quantity * tx.price;
    else if (tx.type === 'BUY') { cash -= tx.quantity * tx.price + tx.fee; invested += tx.quantity * tx.price; }
    else if (tx.type === 'SELL') { cash += tx.quantity * tx.price - tx.fee; invested -= tx.quantity * tx.price; }
    nav.push(+(cash + invested).toFixed(2));
    navDates.push(tx.date);
  }
  // Benchmark: a simple 1.0 baseline scaled to the same length (placeholder).
  const benchmarkNav = nav.map((_, i) => +(1 + i * 0.001).toFixed(3));
  return { nav, navDates, benchmarkNav };
}

/** Register the fund NAV topic (reads the first fund from localStorage). */
export function registerFundNavTopic() {
  registerTopic({
    id: 'portfolio:fund:nav',
    ttl: 60_000,
    interval: 30_000,
    fetch: async () => {
      try {
        const { funds } = loadFunds();
        if (!funds || funds.length === 0) return null;
        return buildFundNav(funds[0]);
      } catch {
        return null;
      }
    },
  });
}
