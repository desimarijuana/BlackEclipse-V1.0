'use client';

// ── Investor Eye — Source Health ─────────────────────────────────────────────
// The operator view of §15: one row per source with its honest state, last
// success/failure, latency and record accounting — from the real
// `SourceRun` log via `/api/investor-eye/health`.
//
// A throttle is rendered as its own state, never folded into "error", so a
// temporary upstream limit is never mistaken for a broken integration.

import { useEffect, useState } from 'react';
import { Activity, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

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
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch('/api/investor-eye/health')
      .then((r) => r.json())
      .then((json: { sources?: HealthSource[] }) => { if (!cancelled) setSources(json.sources ?? []); })
      .catch(() => { if (!cancelled) setSources([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const degraded = sources.filter((s) => s.state === 'error' || s.state === 'rate_limited').length;

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          {open ? <ChevronDown size={12} className="text-muted-foreground" /> : <ChevronRight size={12} className="text-muted-foreground" />}
          <Activity size={12} className={cn(degraded > 0 ? 'text-amber-400' : 'text-muted-foreground')} />
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Data Health</span>
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
          {sources.length === 0 && !loading && (
            <div className="text-[10px] italic text-muted-foreground/70">No source runs recorded yet.</div>
          )}
          {sources.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-2 py-0.5">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', DOT[s.state] ?? DOT.idle)} />
                <span className="truncate text-[10px] text-foreground">{s.name}</span>
                {s.requiresCredentials && (
                  <span className="shrink-0 rounded-sm border border-border/40 px-1 font-mono text-[8px] text-muted-foreground/70">
                    KEY
                  </span>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2 font-mono text-[9px]">
                {s.latencyMs !== null && <span className="text-muted-foreground/60">{s.latencyMs}ms</span>}
                <span className="text-muted-foreground/60">{ago(s.lastRunAt)}</span>
                <span
                  className={cn(
                    s.state === 'healthy' ? 'text-emerald-400'
                      : s.state === 'rate_limited' ? 'text-amber-400'
                        : s.state === 'error' ? 'text-red-400'
                          : 'text-muted-foreground/70',
                  )}
                  title={s.lastError ?? `accepted ${s.totals.accepted} / received ${s.totals.received}`}
                >
                  {LABEL[s.state] ?? s.state.toUpperCase()}
                </span>
              </div>
            </div>
          ))}
          {sources.length > 0 && (
            <div className="pt-1 text-[9px] leading-relaxed text-muted-foreground/60">
              A throttled source is temporary, not broken. Failed sources render as UNAVAILABLE —
              the map never fills the gap with synthetic data.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
