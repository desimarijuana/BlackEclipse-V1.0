'use client';

// Market-wide SEC filings feed (EDGAR current events). Form filtering happens
// at the source, so each selection shows the newest filings of that type.

import React, { useEffect, useState } from 'react';
import { ExternalLink, FileText, Loader2, RefreshCw } from '@/lib/icons';

interface EdgarFiling {
  id: string;
  company: string;
  cik: string | null;
  form: string;
  filed: string | null;
  updated: string | null;
  accession: string | null;
  items: string[];
  url: string;
}

interface FilingsPayload {
  filings: EdgarFiling[];
  form?: string;
  retrievedAt?: string;
  cached?: boolean;
  error?: string;
}

const FORMS = [
  { id: '', label: 'All' },
  { id: '8-K', label: '8-K' },
  { id: '10-K', label: '10-K' },
  { id: '10-Q', label: '10-Q' },
  { id: 'S-1', label: 'S-1' },
  { id: '13F-HR', label: '13F' },
  { id: '4', label: 'Form 4' },
];

export function FilingsFeedView() {
  const [form, setForm] = useState('');
  const [payload, setPayload] = useState<FilingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams({ limit: '40' });
        if (form) qs.set('form', form);
        const res = await fetch(`/api/economics/filings?${qs.toString()}`, { cache: 'no-store' });
        const body = (await res.json()) as FilingsPayload;
        if (cancelled) return;
        if (!res.ok) {
          setPayload(null);
          setError(body.error ?? `Filings request failed (${res.status}).`);
        } else {
          setPayload(body);
        }
      } catch {
        if (!cancelled) {
          setPayload(null);
          setError('The SEC filings feed is unavailable right now.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [form, reloadKey]);

  const filings = payload?.filings ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-[10px] font-mono text-muted-foreground/70">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mr-1.5 align-middle" />
          SEC EDGAR · latest filings{form ? ` · ${form}` : ''} · {filings.length} entries
        </p>
        <div className="flex items-center gap-2">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filing form filters">
            {FORMS.map((f) => (
              <button
                key={f.id || 'all'}
                onClick={() => setForm(f.id)}
                aria-pressed={form === f.id}
                className={`h-8 px-3 rounded-full border font-mono text-[11px] transition-colors cursor-pointer ${
                  form === f.id
                    ? 'bg-primary/10 border-primary text-primary'
                    : 'border-border/30 text-muted-foreground hover:border-foreground hover:text-foreground'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
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
        <div className="flex items-center justify-center gap-2 rounded-xl glass-card-subtle border border-border/10 py-10 text-[12px] font-mono text-muted-foreground">
          <Loader2 size={13} className="animate-spin" /> Loading EDGAR feed…
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-[12px] text-rose-300 font-mono">
          {error}
        </div>
      )}

      {!loading && !error && filings.length === 0 && (
        <div className="rounded-xl border border-dashed border-border/25 p-6 text-center">
          <FileText size={18} className="mx-auto text-muted-foreground/60" />
          <p className="mt-2 text-[12px] text-muted-foreground">No filings of this type in the current feed.</p>
        </div>
      )}

      {!loading && !error && filings.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl glass-card border border-border/10">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-border/10">
                  {['Filed', 'Company', 'Form', 'Items / description', ''].map((header) => (
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
                {filings.map((filing) => {
                  const time = filing.updated
                    ? new Date(filing.updated).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
                    : null;
                  return (
                    <tr key={filing.id} className="border-b border-border/10 last:border-0 hover:bg-accent/20 transition-colors">
                      <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">
                        {filing.filed ?? '—'}
                        {time && <span className="ml-1 text-muted-foreground/60">{time}</span>}
                      </td>
                      <td className="px-3 py-2 text-foreground max-w-[26ch] truncate" title={filing.company}>
                        {filing.company}
                        {filing.cik && (
                          <span className="ml-1.5 font-mono text-[9px] text-muted-foreground/60">CIK {filing.cik}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono font-semibold text-foreground whitespace-nowrap">
                        {filing.form}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground max-w-[38ch] truncate" title={filing.items.join(' · ')}>
                        {filing.items.length > 0 ? filing.items.join(' · ') : '—'}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <a
                          href={filing.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline"
                        >
                          Open <ExternalLink size={10} />
                        </a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] font-mono text-muted-foreground/70">
            Source: SEC EDGAR current-events feed
            {payload?.retrievedAt ? ` · retrieved ${new Date(payload.retrievedAt).toLocaleTimeString('en-US')}` : ''}
            {payload?.cached ? ' · cached' : ''}
          </p>
        </>
      )}
    </div>
  );
}
