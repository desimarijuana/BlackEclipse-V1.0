"use client";

// Command Center drift widget: the per-scope signal plus a short trend. It reads
// the same drift API as the operator card and never creates a candidate.

import { useCallback, useEffect, useState } from "react";
import { Activity } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  getEvolutionDriftHistoryBrowser,
  getEvolutionDriftScopesBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionDriftHistory,
  EvolutionDriftScopes,
} from "@/lib/harness/evolution-client";
import { EVOLUTION_VERIFIED_EVENT } from "@/lib/harness/evolution-events";

export function DriftStatusWidget() {
  const [overview, setOverview] = useState<EvolutionDriftScopes | null>(null);
  const [history, setHistory] = useState<EvolutionDriftHistory | null>(null);

  const load = useCallback(async () => {
    try {
      const [scopes, points] = await Promise.all([
        getEvolutionDriftScopesBrowser({ includeGlobal: false }),
        getEvolutionDriftHistoryBrowser({ limit: 12 }),
      ]);
      setOverview(scopes);
      setHistory(points);
    } catch {
      setOverview(null);
      setHistory(null);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const handler = () => { void load(); };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    return () => window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
  }, [load]);

  const signals = overview?.signals ?? [];
  const drifting = signals.filter((row) => row.signal.status === "drift");
  const maxDrop = Math.max(
    0.01,
    ...(history?.points ?? []).map((point) => point.drop ?? 0),
  );

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-3 flex items-center justify-between gap-2 border-b border-border/10 pb-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Activity size={14} className="shrink-0 text-primary" />
          <h3 className="truncate font-serif text-sm font-semibold text-foreground">
            Production Drift
          </h3>
        </div>
        <span className={cn(
          "shrink-0 rounded border px-1 py-0.5 font-mono text-[8px] font-bold uppercase tracking-wide",
          drifting.length
            ? "border-rose-500/25 bg-rose-500/10 text-rose-400"
            : "border-emerald-500/25 bg-emerald-500/10 text-emerald-400",
        )}>
          {drifting.length ? `${drifting.length} drifting` : "stable"}
        </span>
      </div>

      <div className="flex flex-wrap gap-1">
        {signals.length === 0 ? (
          <p className="text-[11px] italic text-muted-foreground">No measured agent scope.</p>
        ) : signals.map(({ scope, signal }) => (
          <span
            key={scope}
            className={cn(
              "rounded border px-1.5 py-0.5 text-[9px]",
              signal.status === "drift"
                ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                : signal.status === "stable"
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : "border-border/40 bg-background/30 text-muted-foreground",
            )}
          >
            {scope}
            {" "}
            {signal.drop == null ? signal.status : `${Math.round(signal.drop * 100)}%`}
          </span>
        ))}
      </div>

      <div className="mt-auto pt-3">
        <div className="flex h-10 items-end gap-0.5">
          {(history?.points ?? []).slice().reverse().map((point) => (
            <span
              key={point.offset}
              title={`-${point.offset}: ${point.status}`}
              className={cn(
                "min-h-[2px] flex-1 rounded-t",
                point.status === "drift" ? "bg-rose-400/60" : "bg-emerald-400/40",
              )}
              style={{ height: `${Math.max(6, ((point.drop ?? 0) / maxDrop) * 100)}%` }}
            />
          ))}
        </div>
        <p className="mt-1 text-[9px] text-muted-foreground">older ← now</p>
      </div>
    </div>
  );
}
