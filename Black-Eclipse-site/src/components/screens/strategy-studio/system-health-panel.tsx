'use client';

// ── System health (Strategy Studio) ─────────────────────────────────────────
// One operator view: data, broker, risk, runner and lifecycle. A blocked system
// must not send a new live order.

import React, { useCallback, useEffect, useState } from 'react';
import { backtestClient } from '@/lib/backtest/backtest-client';
import { Activity, Loader2, RefreshCw } from '@/lib/icons';

export interface SystemHealthPanelProps {
  strategyId?: string;
  version?: string;
  onError?: (message: string | null) => void;
}

interface Check {
  check: string;
  passed: boolean;
  detail: string;
  critical: boolean;
}

interface Health {
  status: string;
  score: number;
  checks: Check[];
  blockers: string[];
  unknown: string[];
}

export function SystemHealthPanel({ strategyId, version, onError }: SystemHealthPanelProps) {
  const [report, setReport] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    onError?.(null);
    try {
      setReport(await backtestClient.systemHealth(strategyId, version));
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'health check failed');
    } finally {
      setBusy(false);
    }
  }, [onError, strategyId, version]);

  useEffect(() => { void load(); }, [load]);

  const tone = report?.status === 'OK'
    ? 'text-emerald-300'
    : report?.status === 'DEGRADED'
      ? 'text-amber-300'
      : 'text-red-300';

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Activity className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">System health</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          data · broker · risk · runner · lifecycle
        </span>
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[11px]"
        >
          <RefreshCw className={`h-3 w-3 ${busy ? 'animate-spin' : ''}`} />
          Check
        </button>
      </div>

      {report ? (
        <>
          <p className={`text-xs ${tone}`}>
            {report.status} · {report.score}/100
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            A blocked system must not send a new live order.
          </p>
          <ul className="mt-2 space-y-1">
            {report.checks.map((check) => (
              <li key={check.check} className="flex items-start gap-2 text-[11px]">
                <span className={check.passed ? 'text-emerald-400' : 'text-red-400'}>
                  {check.passed ? 'OK' : 'FAIL'}
                </span>
                <span className="w-16 shrink-0 font-mono text-[10px] text-muted-foreground">
                  {check.check}
                </span>
                <span className="min-w-0 flex-1 truncate">{check.detail}</span>
              </li>
            ))}
          </ul>
          {report.unknown.length > 0 ? (
            <p className="mt-2 text-[10px] text-muted-foreground">
              Not checked: {report.unknown.join(', ')}
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          {busy ? <Loader2 className="inline h-3 w-3 animate-spin" /> : null} Loading health.
        </p>
      )}
    </div>
  );
}
