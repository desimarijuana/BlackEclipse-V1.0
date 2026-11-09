'use client';

// ── SEC filings list ────────────────────────────────────────────────────────
// Reads the native /api/stocks/[symbol]/filings route (SEC EDGAR submissions
// index). The route never fabricates a document URL: a filing without a
// provider-published primary document renders without a link.

import React, { useEffect, useMemo, useState } from 'react';
import { ExternalLink, FileText, Loader2, RefreshCw } from '@/lib/icons';

interface FilingRow {
  form: string | null;
  filed: string | null;
  period: string | null;
  accession: string | null;
  document: string | null;
  description: string | null;
}

interface FilingsPayload {
  status: 'OK' | 'UNAVAILABLE' | 'AMBIGUOUS';
  symbol?: string;
  market?: string;
  cik?: number | null;
  entityName?: string | null;
  provider?: string;
  retrievedAt?: string;
  matched?: number;
  count?: number;
  truncated?: boolean;
  note?: string;
  error?: string;
  reason?: string;
  filings?: FilingRow[];
  cached?: boolean;
}

const FORM_FILTERS = ['All', '10-K', '10-Q', '8-K', '4', 'DEF 14A', '20-F', '6-K'];

export function FilingsSection({ symbol, market }: { symbol: string; market: string }) {
  const [payload, setPayload] = useState<FilingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState('All');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams({ market: market || 'US' });
        if (form !== 'All') qs.set('form', form);
        const res = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/filings?${qs.toString()}`, {
          cache: 'no-store',
        });
        const body = (await res.json()) as FilingsPayload;
        if (cancelled) return;
        if (!res.ok) {
          setError(body.error ?? `Filing request failed (${res.status}).`);
          setPayload(null);
        } else {
          setPayload(body);
        }
      } catch {
        if (!cancelled) {
          setError('Filing request failed.');
          setPayload(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol, market, form, reloadKey]);

  const filings = useMemo(() => payload?.filings ?? [], [payload]);
  const unavailable = payload && payload.status !== 'OK';

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-foreground">SEC filings</p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {payload?.provider === 'sec-edgar'
              ? `EDGAR submissions index${payload.entityName ? ` · ${payload.entityName}` : ''}${payload.cik ? ` · CIK ${payload.cik}` : ''}`
              : 'US issuers only — non-US filing indexes are handled by the provider layer.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={form}
            onChange={(e) => setForm(e.target.value)}
            className="h-8 rounded-lg border border-border/30 bg-background/40 px-2 font-mono text-[11px] text-foreground outline-none focus:border-primary"
            aria-label="Filter by form type"
          >
            {FORM_FILTERS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg glass-card-subtle border border-border/20 text-muted-foreground hover:text-foreground cursor-pointer"
            aria-label="Refresh filings"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 rounded-xl glass-card-subtle border border-border/10 py-8 text-[12px] font-mono text-muted-foreground">
          <Loader2 size={13} className="animate-spin" /> Loading SEC filings…
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-[12px] text-rose-300 font-mono">
          {error}
        </div>
      )}

      {!loading && !error && unavailable && (
        <div className="rounded-xl border border-dashed border-border/25 p-5 text-center">
          <FileText size={18} className="mx-auto text-muted-foreground/60" />
          <p className="mt-2 font-mono text-[12px] text-foreground">UNAVAILABLE</p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {payload?.error ?? payload?.reason ?? payload?.note ?? `No SEC filings returned for ${symbol}.`}
          </p>
        </div>
      )}

      {!loading && !error && !unavailable && filings.length === 0 && (
        <div className="rounded-xl border border-dashed border-border/25 p-5 text-center text-[12px] text-muted-foreground">
          No filings matched this filter.
        </div>
      )}

      {!loading && !error && filings.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl glass-card border border-border/10">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-border/10">
                  {['Form', 'Filed', 'Period', 'Description', ''].map((header) => (
                    <th
                      key={header || 'open'}
                      className="text-left px-3 py-2.5 font-mono text-[10px] uppercase tracking-[0.05em] text-muted-foreground font-medium whitespace-nowrap"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filings.map((filing, index) => (
                  <tr
                    key={`${filing.accession ?? filing.filed ?? index}-${index}`}
                    className="border-b border-border/10 last:border-0 hover:bg-accent/20 transition-colors"
                  >
                    <td className="px-3 py-2 font-mono font-semibold text-foreground whitespace-nowrap">
                      {filing.form ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">
                      {filing.filed ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">
                      {filing.period ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-foreground/90 max-w-[34ch] truncate" title={filing.description ?? ''}>
                      {filing.description ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {filing.document ? (
                        <a
                          href={filing.document}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline"
                        >
                          Open <ExternalLink size={10} />
                        </a>
                      ) : (
                        <span className="text-[11px] text-muted-foreground/60">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] font-mono text-muted-foreground/70">
            {payload?.count ?? filings.length} filings
            {payload?.truncated ? ' · truncated at the source ceiling — narrow the form/date window' : ''}
            {payload?.retrievedAt ? ` · retrieved ${payload.retrievedAt.slice(0, 10)}` : ''}
            {payload?.cached ? ' · cached' : ''}
          </p>
        </>
      )}
    </section>
  );
}
