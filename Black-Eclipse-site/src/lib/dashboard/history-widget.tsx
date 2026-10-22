'use client';

// ── History (the local data vault) ──────────────────────────────────────────
// The durable history cache is the local copy of the market Eclipse has
// already paid for. It used to be invisible: bars were fetched, used and
// forgotten. This widget shows what the machine actually holds - which
// instruments, how many bars, how fresh, from which provider - and the
// coverage of one instrument on demand.
//
// It reads the runtime's own catalog, so it can never claim a bar the runtime
// does not have.

import React, { useCallback, useEffect, useState } from 'react';
import { Database, Loader2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface HistorySeries {
  symbol: string;
  interval: string;
  provider: string;
  barCount: number;
  start: string | null;
  end: string | null;
  adjusted?: number;
}

interface HistoryCatalog {
  available: boolean;
  reason?: string;
  series: HistorySeries[];
  count: number;
}

export function HistoryWidget() {
  const [catalog, setCatalog] = useState<HistoryCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/market/history');
      const payload = (await res.json().catch(() => ({}))) as HistoryCatalog & {
        error?: string;
      };
      if (!res.ok) {
        setError(payload.error ?? `the history catalog returned ${res.status}`);
        return;
      }
      setCatalog(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the history catalog is unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useCallback(async (symbol: string) => {
    if (selected === symbol) {
      setSelected(null);
      setCoverage(null);
      return;
    }
    setSelected(symbol);
    setCoverage(null);
    try {
      const res = await fetch(`/api/market/history/${encodeURIComponent(symbol)}`);
      const payload = (await res.json().catch(() => ({}))) as {
        coverage?: Record<string, unknown>;
        reason?: string;
      };
      setCoverage(payload.coverage ?? { reason: payload.reason ?? 'unavailable' });
    } catch {
      setCoverage({ reason: 'the coverage could not be read' });
    }
  }, [selected]);

  const series = catalog?.series ?? [];

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <div className="flex items-center gap-2">
        <Database className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Local history</span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground">
          {loading ? 'loading…' : `${series.length} series`}
        </span>
      </div>

      {error && <p className="font-mono text-[9px] text-rose-300">{error}</p>}
      {!error && !loading && series.length === 0 && (
        <p className="font-mono text-[9px] text-muted-foreground">
          Nothing cached yet. The bars Eclipse fetches are kept here from now on.
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-hide">
        {series.map((row) => (
          <div key={`${row.symbol}-${row.interval}`} className="mb-0.5">
            <button
              type="button"
              onClick={() => void open(row.symbol)}
              className={cn(
                'flex w-full items-center gap-2 rounded px-2 py-1 text-left transition',
                selected === row.symbol
                  ? 'border border-primary/40 bg-primary/10'
                  : 'border border-transparent hover:bg-white/5',
              )}
            >
              <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-foreground">
                {row.symbol}
              </span>
              <span className="shrink-0 font-mono text-[9px] text-muted-foreground">
                {row.interval} · {row.barCount} bars
              </span>
            </button>
            {selected === row.symbol && coverage && (
              <div className="px-2 py-1 font-mono text-[9px] text-muted-foreground">
                {Object.entries(coverage).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <span>{key}</span>
                    <span className="text-foreground">{String(value ?? '—')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-[8px] leading-relaxed text-muted-foreground/70">
        The local copy of the market Eclipse has already paid for. A backtest that pins
        its window is served from here; an open-ended request refetches the tail.
      </p>
    </div>
  );
}
