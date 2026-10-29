'use client';

// ── Data preflight ──────────────────────────────────────────────────────────
// Before a run, tell the user whether the requested symbol/interval is in the
// stored market-data catalogue — with bars and a date range — instead of
// letting a run fail for a boring reason. Absence is reported honestly: it
// means "not stored", not "no such data".

import React, { useEffect, useState } from 'react';
import { researchDataClient } from '@/lib/research-data/research-data-client';
import {
  evaluateCoverage,
  splitSymbols,
  type CoverageResult,
} from '@/lib/strategy-studio/preflight';
import { addDays, isoToday } from '@/lib/strategy-studio/paper-window';
import { Database, Loader2, RefreshCw, Search } from '@/lib/icons';
import { cn } from '@/lib/utils';

const TONE: Record<CoverageResult['state'], string> = {
  ready: 'text-emerald-400 border-emerald-500/30',
  partial: 'text-amber-400 border-amber-500/30',
  missing: 'text-rose-400 border-rose-500/30',
  unknown: 'text-muted-foreground border-white/15',
};

export function DataPreflight({ symbolInput, interval }: { symbolInput: string; interval: string }) {
  const symbols = splitSymbols(symbolInput);
  const key = `${symbols.join(',')}|${interval}`;
  const [coverage, setCoverage] = useState<CoverageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerNote, setProviderNote] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!symbols.length) {
      setCoverage(evaluateCoverage([], [], interval));
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      researchDataClient
        .storedSeries()
        .then((series) => {
          if (!cancelled) setCoverage(evaluateCoverage(series, symbols, interval));
        })
        .catch(() => {
          if (!cancelled) setCoverage(evaluateCoverage(null, symbols, interval));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // `key` captures both symbols and interval; the raw props are read above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reload]);

  const checkProviders = async () => {
    if (!symbols.length) return;
    setProviderBusy(true);
    setProviderNote(null);
    setProviderError(null);
    try {
      const result = await researchDataClient.marketData({
        symbols,
        interval,
        start: addDays(isoToday(), -30),
        end: isoToday(),
      });
      const count = Array.isArray(result.results) ? result.results.length : 0;
      setProviderNote(
        result.status === 'OK' && count
          ? `Providers returned ${count} result${count === 1 ? '' : 's'} for the last 30 days.`
          : `Providers returned no bars (status ${result.status}).`,
      );
    } catch (err) {
      setProviderError(err instanceof Error ? err.message : 'the provider check failed');
    } finally {
      setProviderBusy(false);
    }
  };

  return (
    <section className="glass-card-subtle rounded-xl p-3" aria-label="Data coverage">
      <div className="mb-1 flex items-center gap-2">
        <Database className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Data coverage</span>
        {coverage ? (
          <span
            className={cn(
              'ml-auto rounded-md border px-1.5 py-0.5 font-mono text-[9px] uppercase',
              TONE[coverage.state],
            )}
          >
            {coverage.state}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setReload((value) => value + 1)}
          disabled={loading}
          aria-label="Re-check data coverage"
          className={cn('rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-40', !coverage && 'ml-auto')}
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
        </button>
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {loading && !coverage ? 'Checking the stored market-data catalogue…' : coverage?.headline}
      </p>

      {coverage?.symbols.some((item) => item.state === 'missing') ? (
        <ul className="mt-1 space-y-0.5">
          {coverage.symbols
            .filter((item) => item.state === 'missing')
            .map((item) => (
              <li key={item.symbol} className="font-mono text-[10px] text-amber-200/90">
                {item.symbol}:{' '}
                {item.alternatives.length
                  ? `stored intervals ${item.alternatives.map((alt) => alt.interval).join(', ')}`
                  : 'not in the stored catalogue; the engine will try configured providers'}
              </li>
            ))}
        </ul>
      ) : null}

      {coverage && (coverage.state === 'ready' || coverage.state === 'partial') ? (
        <p className="mt-1 font-mono text-[10px] leading-relaxed text-muted-foreground/80">{coverage.detail}</p>
      ) : null}

      <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
        A stored series is one source, not a guarantee. The run itself reports what it actually used.
      </p>

      <div className="mt-2 border-t border-white/10 pt-2">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void checkProviders()}
            disabled={providerBusy || !symbols.length}
            title="Contacts the configured providers with a 30-day window"
            className="glass-button flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] disabled:opacity-50"
          >
            {providerBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Search className="h-3 w-3" />}
            Check providers
          </button>
          <span className="text-[9px] text-muted-foreground/60">opt-in · contacts providers</span>
        </div>
        {providerNote ? <p className="mt-1 text-[10px] text-emerald-300">{providerNote}</p> : null}
        {providerError ? <p className="mt-1 text-[10px] text-rose-300">{providerError}</p> : null}
      </div>
    </section>
  );
}
