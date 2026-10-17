'use client';

// ── Proactive monitors ──────────────────────────────────────────────────────
// Arm a portfolio monitor from the closed catalogue (from `/automations/monitors`).
// A monitor is a condition automation, created switched off; the operator enables
// it in the schedule rail. Nothing here places a trade.

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, ShieldCheck } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  createMonitor,
  listMonitors,
  type AdvisoryMonitorView,
} from '@/lib/harness/automation-browser';

const PARAM_LABEL: Record<string, string> = {
  portfolio_id: 'Portfolio id',
  symbol: 'Symbol',
  threshold: 'Threshold',
};

export function MonitorPanel({ onArmed }: { onArmed?: () => void }) {
  const [monitors, setMonitors] = useState<AdvisoryMonitorView[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMonitors(await listMonitors());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load monitors');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const arm = useCallback(async (monitor: AdvisoryMonitorView) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const numeric = (value: string) => (value.trim() !== '' && !Number.isNaN(Number(value)) ? Number(value) : value);
      const payload: Record<string, string | number> = {};
      for (const key of monitor.requiredParams) payload[key] = numeric(params[key] ?? '');
      const automation = await createMonitor({ monitorId: monitor.id, params: payload });
      setMessage(`Armed "${automation.name}" (saved off — enable it in the schedule list).`);
      setOpen(null);
      setParams({});
      onArmed?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to arm the monitor');
    } finally {
      setBusy(false);
    }
  }, [params, onArmed]);

  return (
    <div className="rounded-2xl border border-white/10 glass-card p-3">
      <div className="flex items-center gap-2">
        <ShieldCheck size={14} className="text-primary" />
        <span className="text-[12.5px] font-semibold text-foreground">Monitors</span>
        <span className="text-[10px] text-muted-foreground">runs while you&apos;re away</span>
      </div>

      {error && <div className="mt-2 rounded-lg border border-rose-500/20 bg-rose-500/5 p-2 text-[11px] text-rose-300">{error}</div>}
      {message && <div className="mt-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2 text-[11px] text-emerald-300">{message}</div>}

      <div className="mt-2 space-y-1.5">
        {monitors.map((m) => (
          <div key={m.id} className="rounded-xl border border-white/[0.06] p-2.5">
            <button
              type="button"
              onClick={() => { setOpen(open === m.id ? null : m.id); setParams({}); setMessage(null); }}
              className="flex w-full items-center justify-between gap-2 text-left"
            >
              <span className="min-w-0">
                <span className="block truncate text-[12px] font-medium text-foreground">{m.label}</span>
                <span className="block truncate text-[10px] text-muted-foreground">{m.description}</span>
              </span>
              <Plus size={13} className={cn('shrink-0 text-muted-foreground transition', open === m.id && 'rotate-45')} />
            </button>

            {open === m.id && (
              <div className="mt-2 space-y-1.5">
                <code className="block break-all rounded bg-black/30 px-1.5 py-1 text-[10px] text-muted-foreground">{m.condition}</code>
                {m.requiredParams.map((key) => (
                  <input
                    key={key}
                    value={params[key] ?? ''}
                    onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))}
                    placeholder={PARAM_LABEL[key] ?? key}
                    className="w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-foreground placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
                  />
                ))}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void arm(m)}
                  className="flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary hover:bg-primary/20 disabled:opacity-50"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />}
                  Arm monitor
                </button>
              </div>
            )}
          </div>
        ))}
        {monitors.length === 0 && !error && (
          <div className="text-[11px] text-muted-foreground">No monitors available.</div>
        )}
      </div>
    </div>
  );
}
