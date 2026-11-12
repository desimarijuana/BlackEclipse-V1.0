"use client";

// Read-only v2 frontier: which recorded states are not dominated on the measured
// objectives. It never ranks a "best" state or changes acceptance.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import { getEvolutionStatesParetoBrowser } from "@/lib/harness/clients/evolution-browser";
import type { EvolutionPareto } from "@/lib/harness/clients/evolution-client";
import { EVOLUTION_VERIFIED_EVENT } from "@/lib/harness/evolution-events";

export function paretoSummary(pareto: EvolutionPareto | null): {
  frontier: number;
  dominated: number;
  total: number;
} {
  return {
    frontier: pareto?.frontier?.length ?? 0,
    dominated: Object.keys(pareto?.dominated ?? {}).length,
    total: pareto?.states?.length ?? 0,
  };
}

export function ParetoFrontierCard({ scope }: { scope?: string }) {
  const t = useT();
  const [pareto, setPareto] = useState<EvolutionPareto | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPareto(await getEvolutionStatesParetoBrowser({
        scope: scope && scope !== "all" ? scope : undefined,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("evolution.pareto.error"));
    }
  }, [scope, t]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const handler = () => { void load(); };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    return () => window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
  }, [load]);

  const summary = paretoSummary(pareto);

  return (
    <div className="mt-3 rounded-lg border border-border/40 bg-background/30 p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h5 className="text-xs font-semibold text-foreground">{t("evolution.pareto.title")}</h5>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            {t("evolution.pareto.subtitle")}
          </p>
        </div>
        <span className="rounded-full border border-sky-400/30 bg-sky-400/10 px-2 py-0.5 text-[9px] text-sky-300">
          {t("evolution.pareto.counts", {
            frontier: summary.frontier,
            total: summary.total,
          })}
        </span>
      </div>
      {error && <p className="mt-1 text-[10px] text-rose-300">{error}</p>}
      {!pareto && !error && (
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.pareto.loading")}</p>
      )}
      {pareto && (pareto.states?.length ?? 0) === 0 && (
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.pareto.empty")}</p>
      )}
      {pareto && (pareto.states?.length ?? 0) > 0 && (
        <div className="mt-1.5 space-y-1">
          {(pareto.states ?? []).map((state) => {
            const onFront = (pareto.frontier ?? []).includes(String(state.id));
            return (
              <div
                key={state.id ?? "unknown"}
                className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px]"
              >
                <span className={onFront ? "text-emerald-300" : "text-muted-foreground"}>
                  {state.id ?? "unknown"}
                  {state.status === "current" ? ` · ${t("evolution.pareto.current")}` : ""}
                </span>
                <span className="text-muted-foreground">
                  {Object.entries(state.vector)
                    .filter(([, value]) => value != null)
                    .map(([key, value]) => `${key}=${Number(value).toFixed(3)}`)
                    .join(" · ")}
                </span>
                {!onFront && pareto.dominated[String(state.id)] && (
                  <span className="text-rose-300">
                    {t("evolution.pareto.dominatedBy", {
                      id: pareto.dominated[String(state.id)],
                    })}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
