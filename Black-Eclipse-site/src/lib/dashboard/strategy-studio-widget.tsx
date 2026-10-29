'use client';

// ── Strategy Studio widget ──────────────────────────────────────────────────
// The dashboard's front door into the studio: your saved strategies, newest
// first, each linking straight to its workspace. It reads the quant store
// through the same client the studio uses; a runtime that is down says so.

import React, { useCallback, useEffect, useState } from 'react';
import {
  backtestClient,
  type StrategySummary,
} from '@/lib/backtest/backtest-client';
import { hrefForTab } from '@/lib/search/deep-link';
import { ChevronRight, FlaskConical, Loader2 } from '@/lib/icons';

export function StrategyStudioWidget() {
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [grades, setGrades] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, gallery] = await Promise.all([
        backtestClient.listStrategies(),
        fetch('/api/harness/gallery')
          .then((response) => (response.ok ? response.json() : { entries: [] }))
          .catch(() => ({ entries: [] })) as Promise<{
          entries?: Array<{ strategyId?: string; grade?: string | null }>;
        }>,
      ]);
      const byStrategy: Record<string, string> = {};
      for (const entry of gallery.entries ?? []) {
        if (entry.strategyId && entry.grade) byStrategy[entry.strategyId] = entry.grade;
      }
      setGrades(byStrategy);
      setStrategies(
        [...list].sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? '')).slice(0, 6),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the quant store is unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Strategy Studio</span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground">
          {loading ? 'loading…' : `${strategies.length} saved`}
        </span>
      </div>

      {error ? <p className="font-mono text-[9px] text-rose-300">{error}</p> : null}

      {!error && !loading && strategies.length === 0 ? (
        <div className="flex flex-1 flex-col items-start justify-center gap-1">
          <p className="font-mono text-[9px] leading-relaxed text-muted-foreground">
            No strategies yet. Draft one from a thesis or a template.
          </p>
          <a
            href={hrefForTab('strategy-studio')}
            className="flex items-center gap-1 rounded border border-primary/40 px-1.5 py-0.5 text-[9px] text-primary"
          >
            Open the studio <ChevronRight className="h-2.5 w-2.5" />
          </a>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto scrollbar-hide">
        {strategies.map((strategy) => (
          <a
            key={strategy.id}
            href={hrefForTab('strategy-studio', { strategy: strategy.id })}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition hover:bg-white/5"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[10px] text-foreground">
                {strategy.name || strategy.id}
              </span>
              <span className="block truncate font-mono text-[8px] text-muted-foreground">
                {strategy.id} · v{strategy.latestVersion}
                {strategy.updatedAt ? ` · ${strategy.updatedAt.slice(0, 10)}` : ''}
              </span>
            </span>
            {grades[strategy.id] ? (
              <span className="shrink-0 rounded border border-primary/40 bg-primary/10 px-1 font-mono text-[8px] text-primary">
                {grades[strategy.id]}
              </span>
            ) : null}
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          </a>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <a
          href={hrefForTab('strategy-studio')}
          className="ml-auto flex items-center gap-1 font-mono text-[9px] text-muted-foreground hover:text-foreground"
        >
          open studio <ChevronRight className="h-2.5 w-2.5" />
        </a>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
          aria-label="Refresh saved strategies"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
        </button>
      </div>
    </div>
  );
}
