'use client';

// ── Shared trade table ──────────────────────────────────────────────────────
// The executed-trade ledger, identical on the Backtest bench and in the Studio.

import React from 'react';
import type { BacktestResult } from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';

export function TradeTable({
  result,
  maxRows = 200,
  newestFirst = true,
  emptyLabel = 'No trades were generated for this configuration.',
}: {
  result: BacktestResult;
  maxRows?: number;
  newestFirst?: boolean;
  emptyLabel?: string;
}) {
  if (!result.trades.length) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  const rows = newestFirst ? result.trades.slice(-maxRows).reverse() : result.trades.slice(0, maxRows);
  return (
    <div className="max-h-[300px] overflow-auto">
      <table className="w-full text-left font-mono text-[11px]">
        <thead className="sticky top-0 bg-black/30 text-muted-foreground">
          <tr>
            <th className="px-2 py-1">Symbol</th>
            <th className="px-2 py-1">Dir</th>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1 text-right">Net P&amp;L</th>
            <th className="px-2 py-1 text-right">%</th>
            <th className="px-2 py-1">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((trade) => (
            <tr key={trade.id} className="border-t border-white/5">
              <td className="px-2 py-1">{trade.symbol}</td>
              <td className={cn('px-2 py-1', trade.direction === 'long' ? 'text-emerald-400' : 'text-rose-400')}>
                {trade.direction}
              </td>
              <td className="px-2 py-1">{trade.entryPrice.toFixed(2)}</td>
              <td className="px-2 py-1">{trade.exitPrice.toFixed(2)}</td>
              <td className={cn('px-2 py-1 text-right', trade.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                {trade.netPnl.toFixed(2)}
              </td>
              <td className="px-2 py-1 text-right">{trade.pnlPct.toFixed(2)}%</td>
              <td className="px-2 py-1 text-muted-foreground">{trade.exitReason || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
