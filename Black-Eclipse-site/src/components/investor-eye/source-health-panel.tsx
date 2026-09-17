'use client';

// ── Investor Eye — Source Health & Data Sources ──────────────────────────────
// The operator view of §15 / §19 / §34: one row per source with its honest
// state, last success/failure, latency and record accounting — from the real
// `SourceRun` log via `/api/investor-eye/health`.
//
// It also carries the DATA GOVERNANCE view (§6 / §36): license, commercial-use
// status and rate limit per source, plus the centralised attribution block. A
// source that can run but has not declared its license is shown as an explicit
// gap — not a blank cell that would read as "nothing required".
//
// A throttle is rendered as its own state, never folded into "error", so a
// temporary upstream limit is never mistaken for a broken integration.

import { useEffect, useState } from 'react';
import { Activity, Loader2, ChevronDown, ChevronRight, ExternalLink, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CatalogInfo {
  provider: string;
  category: string;
  website: string;
  license: string;
  licenseUrl: string | null;
  termsUrl: string | null;
  commercialUse: string;
  commercialUseLabel: string;
  requiresApiKey: boolean;
  attributionRequired: boolean;
  attribution: string | null;
  rateLimit: string | null;
  dataFreshness: string;
  note: string;
}

interface HealthSource {
  id: string;
  name: string;
  capabilities: string[];
  requiresCredentials: boolean;
  state: 'healthy' | 'error' | 'rate_limited' | 'idle' | string;
  lastRunAt: string | null;
  lastError: string | null;
  lastSuccessAt: string | null;
  latencyMs: number | null;
  runCount: number;
  totals: { received: number; accepted: number; rejected: number };
  catalog: CatalogInfo | null;
  hasCatalogEntry: boolean;
}

const DOT: Record<string, string> = {
  healthy: 'bg-emerald-400',
  rate_limited: 'bg-amber-400',
  error: 'bg-red-500',
  idle: 'bg-muted-foreground/40',
};

const LABEL: Record<string, string> = {
  healthy: 'LIVE',
  rate_limited: 'THROTTLED',
  error: 'ERROR',
  idle: 'IDLE',
};

const FRESHNESS_LABEL: Record<string, string> = {
  seconds: 'seconds',
  minutes: 'minutes',
  hourly: 'hourly',
  daily: 'daily',
  static: 'static',
};

function ago(iso: string | null): string {
  if (!iso) return 'never';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'never';
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}

export function SourceHealthPanel() {
  const [sources, setSources] = useState<HealthSource[]>([]);
  const [attributions, setAttributions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch('/api/investor-eye/health')
      .then((r) => r.json())
      .then((json: { sources?: HealthSource[]; attributions?: string[] }) => {
        if (cancelled) return;
        setSources(json.sources ?? []);
        setAttributions(json.attributions ?? []);
      })
      .catch(() => { if (!cancelled) { setSources([]); setAttributions([]); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const degraded = sources.filter((s) => s.state === 'error' || s.state === 'rate_limited').length;
  // A runnable source with no catalog entry is a real governance gap.
  const unlicensed = sources.filter((s) => !s.hasCatalogEntry).length;

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          {open ? <ChevronDown size={12} className="text-muted-foreground" /> : <ChevronRight size={12} className="text-muted-foreground" />}
          <Activity size={12} className={cn(degraded > 0 ? 'text-amber-400' : 'text-muted-foreground')} />
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Data Sources</span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[9px]">
          {loading && <Loader2 size={11} className="animate-spin text-muted-foreground" />}
          <span className={cn(degraded > 0 ? 'text-amber-300' : 'text-muted-foreground/70')}>
            {sources.length} sources{degraded > 0 ? ` · ${degraded} degraded` : ''}
          </span>
        </span>
      </button>

      {open && (
        <div className="space-y-1 border-t border-border/10 px-3 py-2">
          {unlicensed > 0 && (
            <div className="mb-1 flex items-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2 py-1 text-[9px] text-amber-200/90">
              <ShieldAlert size={11} className="shrink-0" />
              {unlicensed} source{unlicensed === 1 ? '' : 's'} can run without a declared license — governance gap.
            </div>
          )}

          {/* Column header — the spec §19 table shape, kept dense. */}
          <div className="hidden items-center gap-2 px-1 pb-0.5 font-mono text-[8px] uppercase tracking-wider text-muted-foreground/50 sm:flex">
            <span className="w-[150px] shrink-0">Source</span>
            <span className="w-[74px] shrink-0">Category</span>
            <span className="w-[64px] shrink-0">Auth</span>
            <span className="flex-1">License</span>
            <span className="w-[52px] shrink-0 text-right">Updated</span>
            <span className="w-[58px] shrink-0 text-right">State</span>
          </div>

          {sources.length === 0 && !loading && (
            <div className="text-[10px] italic text-muted-foreground/70">No source runs recorded yet.</div>
          )}

          {sources.map((s) => {
            const cat = s.catalog;
            const isOpen = expanded === s.id;
            return (
              <div key={s.id} className="border-b border-border/10 pb-1 last:border-b-0">
                <button
                  onClick={() => setExpanded(isOpen ? null : s.id)}
                  className="flex w-full flex-wrap items-center gap-2 py-0.5 text-left cursor-pointer"
                >
                  <div className="flex w-[150px] shrink-0 items-center gap-1.5">
                    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', DOT[s.state] ?? DOT.idle)} />
                    <span className="truncate text-[10px] text-foreground">{s.name}</span>
                  </div>
                  <span className="w-[74px] shrink-0 truncate font-mono text-[9px] text-muted-foreground/70">
                    {cat?.category?.toUpperCase() ?? '—'}
                  </span>
                  <span className="w-[64px] shrink-0 font-mono text-[9px] text-muted-foreground/70">
                    {s.requiresCredentials ? 'Key' : 'None'}
                  </span>
                  <span className="flex-1 truncate text-[9px] text-muted-foreground/70" title={cat?.license}>
                    {cat ? (
                      <>
                        {cat.license}
                        {cat.commercialUse === 'unknown' && (
                          <span className="ml-1 text-amber-300/80">· {cat.commercialUseLabel}</span>
                        )}
                      </>
                    ) : (
                      <span className="text-amber-300/80">No license declared</span>
                    )}
                  </span>
                  <span className="w-[52px] shrink-0 text-right font-mono text-[9px] text-muted-foreground/60">
                    {ago(s.lastRunAt)}
                  </span>
                  <span
                    className={cn(
                      'w-[58px] shrink-0 text-right font-mono text-[9px]',
                      s.state === 'healthy' ? 'text-emerald-400'
                        : s.state === 'rate_limited' ? 'text-amber-400'
                          : s.state === 'error' ? 'text-red-400'
                            : 'text-muted-foreground/70',
                    )}
                    title={s.lastError ?? `accepted ${s.totals.accepted} / received ${s.totals.received}`}
                  >
                    {LABEL[s.state] ?? s.state.toUpperCase()}
                  </span>
                </button>

                {isOpen && (
                  <div className="mb-1 ml-3 space-y-0.5 rounded-lg border border-border/15 bg-background/30 px-2 py-1.5 font-mono text-[9px] text-muted-foreground/80">
                    {cat ? (
                      <>
                        <div>Provider: <span className="text-foreground/80">{cat.provider}</span></div>
                        <div>Freshness: <span className="text-foreground/80">{FRESHNESS_LABEL[cat.dataFreshness] ?? cat.dataFreshness}</span></div>
                        <div>Commercial use: <span className="text-foreground/80">{cat.commercialUseLabel}</span></div>
                        <div>Key required: <span className="text-foreground/80">{cat.requiresApiKey ? 'yes' : 'no'}</span></div>
                        {cat.rateLimit && <div>Rate limit: <span className="text-foreground/80">{cat.rateLimit}</span></div>}
                        {cat.attributionRequired && cat.attribution && (
                          <div>Attribution: <span className="text-foreground/80">{cat.attribution}</span></div>
                        )}
                        <div className="pt-0.5 text-muted-foreground/60">{cat.note}</div>
                        <div className="flex flex-wrap items-center gap-2 pt-0.5">
                          <a
                            href={cat.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-0.5 text-sky-300/80 hover:text-sky-200"
                          >
                            Website <ExternalLink size={9} />
                          </a>
                          {cat.licenseUrl && (
                            <a
                              href={cat.licenseUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-0.5 text-sky-300/80 hover:text-sky-200"
                            >
                              License <ExternalLink size={9} />
                            </a>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="text-amber-200/80">
                        No catalog entry. This source can fetch data but has not declared its
                        license, commercial-use status or attribution.
                      </div>
                    )}
                    <div className="pt-0.5 text-muted-foreground/60">
                      Runs: {s.runCount} · accepted {s.totals.accepted} / received {s.totals.received}
                      {s.latencyMs !== null ? ` · ${s.latencyMs}ms` : ''}
                      {s.lastSuccessAt ? ` · last success ${ago(s.lastSuccessAt)}` : ''}
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {sources.length > 0 && (
            <div className="pt-1 text-[9px] leading-relaxed text-muted-foreground/60">
              A throttled source is temporary, not broken. Failed sources render as UNAVAILABLE —
              the map never fills the gap with synthetic data.
            </div>
          )}

          {attributions.length > 0 && (
            <div className="border-t border-border/10 pt-1.5 text-[9px] leading-relaxed text-muted-foreground/60">
              <span className="font-bold uppercase tracking-wider text-muted-foreground/70">Attribution: </span>
              {attributions.join(' · ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
