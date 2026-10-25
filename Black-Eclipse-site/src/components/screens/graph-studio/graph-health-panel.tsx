'use client';

// Bounded operator telemetry for graph runs. Everything shown comes from the
// runtime's persisted run/node rows; a missing value renders "—", never a zero.

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from '@/lib/icons';
import { getGraphHealth, type GraphHealth } from '@/lib/graph-studio/execution-client';
import { formatDuration, formatTimestamp } from '@/lib/graph-studio/history-model';

const WINDOWS: [number, string][] = [[1, '1h'], [24, '24h'], [168, '7d']];

function pct(value: number | null): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

export function GraphHealthPanel() {
  const [windowHours, setWindowHours] = useState(24);
  const [health, setHealth] = useState<GraphHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await getGraphHealth(windowHours));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load graph health');
    } finally {
      setLoading(false);
    }
  }, [windowHours]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/10 p-2">
        {WINDOWS.map(([hours, label]) => (
          <button
            key={hours}
            type="button"
            onClick={() => setWindowHours(hours)}
            className={`flex-1 rounded-md px-2 py-1 text-[11px] ${
              windowHours === hours ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          title="Refresh health"
          className="shrink-0 rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : undefined} />
        </button>
      </div>

      {error && (
        <p className="mx-2 mt-2 shrink-0 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {!health && !error && (
          <p className="px-1 py-3 text-[11px] text-muted-foreground">{loading ? 'Loading…' : 'No telemetry yet.'}</p>
        )}
        {health && (
          <>
            {health.watch.status === 'degraded' && (
              <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[10px] text-rose-200">
                <div className="font-medium">Graph health degraded</div>
                {health.watch.reasons.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            {health.watch.status === 'insufficient' && (
              <p className="rounded border border-white/10 px-2 py-1 text-[10px] text-muted-foreground">
                Health watch has too little data: {health.watch.reasons[0] ?? 'no runs yet'}.
              </p>
            )}
            {health.watch.status === 'healthy' && (
              <p className="rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1 text-[10px] text-emerald-200">
                Health watch: healthy
                {health.watch.checkedAt ? ` (checked ${formatTimestamp(health.watch.checkedAt)})` : ''}.
              </p>
            )}
            <div className="grid grid-cols-2 gap-1.5">
              <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
                <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">Runs</div>
                <div className="text-[13px] text-foreground">{health.runs.total}</div>
                <div className="text-[9.5px] text-muted-foreground">{health.runs.throughputPerHour}/h</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
                <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">Success</div>
                <div className="text-[13px] text-foreground">{pct(health.runs.successRate)}</div>
                <div className="text-[9.5px] text-muted-foreground">of {health.runs.terminal} terminal</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
                <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">Duration p95</div>
                <div className="text-[13px] text-foreground">{formatDuration(health.durationMs.p95)}</div>
                <div className="text-[9.5px] text-muted-foreground">p50 {formatDuration(health.durationMs.p50)}</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5">
                <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">Queue wait p95</div>
                <div className="text-[13px] text-foreground">{formatDuration(health.queueWaitMs.p95)}</div>
                <div className="text-[9.5px] text-muted-foreground">avg {formatDuration(health.queueWaitMs.avg)}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-1 text-[9.5px] text-muted-foreground">
              {Object.entries(health.runs.byStatus).map(([status, count]) => (
                <span key={status} className="rounded border border-white/10 px-1.5 py-0.5">
                  {status} {count}
                </span>
              ))}
            </div>

            <div>
              <div className="mb-1 text-[9.5px] uppercase tracking-wide text-muted-foreground">
                Node runs · {health.nodeRuns.total} · {health.nodeRuns.failed} failed · checkpoint{' '}
                {pct(health.nodeRuns.checkpointRate)}
              </div>
              {health.failures.length === 0 ? (
                <p className="text-[10px] text-muted-foreground">No failed nodes in this window.</p>
              ) : (
                health.failures.map((failure) => (
                  <div key={failure.code} className="flex justify-between text-[10px] text-slate-300">
                    <span className="truncate font-mono">{failure.code}</span>
                    <span className="text-muted-foreground">{failure.count}</span>
                  </div>
                ))
              )}
            </div>

            <div>
              <div className="mb-1 text-[9.5px] uppercase tracking-wide text-muted-foreground">Slowest node types</div>
              {health.slowestNodes.length === 0 ? (
                <p className="text-[10px] text-muted-foreground">No node durations in this window.</p>
              ) : (
                health.slowestNodes.map((node) => (
                  <div key={node.nodeType} className="flex items-center justify-between gap-2 text-[10px] text-slate-300">
                    <span className="min-w-0 flex-1 truncate font-mono">{node.nodeType}</span>
                    <span className="shrink-0 text-muted-foreground">{node.runs}×</span>
                    <span className="shrink-0 text-muted-foreground">{formatDuration(node.avgMs)}</span>
                  </div>
                ))
              )}
            </div>

            {(health.truncated.runs || health.truncated.nodeRuns) && (
              <p className="rounded border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[9.5px] text-amber-200">
                Bounded read hit its cap; figures cover the most recent rows only.
              </p>
            )}
            <p className="text-[9px] text-muted-foreground">as of {formatTimestamp(health.generatedAt)}</p>
          </>
        )}
      </div>
    </div>
  );
}
