'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, RefreshCw, Sparkles } from '@/lib/icons';
import {
  acceptGap,
  declineGap,
  gapSummary,
  listGaps,
  suppressGap,
  type CapabilityGapRow,
  type CapabilityGapSummary,
} from '@/lib/harness/clients/capabilities-client';

/**
 * The durable gap queue: runs that could not finish and the one route Eclipse
 * offers for each. Accepting a row never performs the work here; it returns the
 * exact prompt/surface, and that surface asks for its own approval.
 */
export function GapsSection() {
  const [rows, setRows] = useState<CapabilityGapRow[]>([]);
  const [summary, setSummary] = useState<CapabilityGapSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [allRows, nextSummary] = await Promise.all([
        listGaps(),
        gapSummary(),
      ]);
      setRows(allRows.filter((row) => row.state === 'open' || row.state === 'offered'));
      setSummary(nextSummary);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read the gap queue.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = useCallback(async (gapId: string, action: 'accept' | 'decline' | 'suppress') => {
    setBusy(gapId);
    setError('');
    setNotice('');
    try {
      if (action === 'accept') {
        const result = await acceptGap(gapId);
        const prompt = String((result.result as Record<string, unknown> | undefined)?.actionPrompt ?? '');
        setNotice(prompt ? `Accepted. Next prompt: ${prompt}` : 'Accepted.');
      } else if (action === 'decline') {
        await declineGap(gapId);
        setNotice('Not now. The gap stays in history.');
      } else {
        await suppressGap(gapId);
        setNotice('Eclipse will not ask for this gap again.');
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The action failed.');
    } finally {
      setBusy(null);
    }
  }, [load]);

  const open = summary?.byState?.open ?? rows.length;
  const offered = summary?.byState?.offered ?? 0;
  const accepted = summary?.byState?.accepted ?? 0;

  return (
    <div className="glass-card rounded-xl p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          <Sparkles size={12} /> Gaps &amp; offers
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          aria-label="Refresh gaps"
          className="rounded-md p-1 text-muted-foreground hover:text-foreground"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      <p className="mb-2 text-[11px] text-muted-foreground">
        Each row is a request Eclipse could not finish and the route it can take.
        Accepting starts that route; it does not grant a permission.
      </p>

      <div className="mb-2 flex flex-wrap gap-2 font-mono text-[10px] text-muted-foreground">
        <span>open {open}</span>
        <span>offered {offered}</span>
        <span>accepted {accepted}</span>
      </div>

      {error ? <p className="mb-2 text-[11px] text-rose-300">{error}</p> : null}
      {notice ? <p className="mb-2 text-[11px] text-emerald-300">{notice}</p> : null}

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No unresolved gaps.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.gapId} className="rounded-xl border border-border/20 bg-white/[0.02] px-3 py-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <AlertTriangle size={11} className="text-amber-300" />
                    <span className="truncate text-xs font-medium text-foreground">{row.need}</span>
                    <span className="rounded-full border border-border/30 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                      {row.kind}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    {row.offer.actionLabel}
                    {row.offer.nextTool ? ` via ${row.offer.nextTool}` : ''}
                    {row.reason ? ` — ${row.reason}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    disabled={busy === row.gapId}
                    onClick={() => void act(row.gapId, 'accept')}
                    className="glass-button flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-foreground disabled:opacity-50"
                  >
                    <Check size={10} /> Accept
                  </button>
                  <button
                    type="button"
                    disabled={busy === row.gapId}
                    onClick={() => void act(row.gapId, 'decline')}
                    className="rounded-lg px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    Not now
                  </button>
                  <button
                    type="button"
                    disabled={busy === row.gapId}
                    onClick={() => void act(row.gapId, 'suppress')}
                    className="rounded-lg px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    Never
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
