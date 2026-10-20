"use client";

// RSL experiment review — the operator's evidence surface inside the learning
// journey. It reads the runtime's recorded experiments, never invents a metric,
// and "Prepare landing" only builds the existing promotion preview (the
// single-use approval is still the only write path).

import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCcw, X } from "@/lib/icons";
import { useT } from "@/lib/i18n/use-t";
import type { TranslateFn } from "@/lib/i18n/translate";
import {
  listEvolutionExperimentsBrowser,
  prepareEvolutionLandingBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionExperiment,
  EvolutionLandingResult,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";
import { RslControlPanel } from "./rsl-control-panel";
import { RslOperatorPanel } from "./rsl-operator-panel";

function meta(experiment: EvolutionExperiment, key: string): unknown {
  return (experiment.metadata ?? {})[key];
}

function benchmarkOf(experiment: EvolutionExperiment): string {
  return String(meta(experiment, "benchmark") ?? experiment.config?.benchmark ?? "UNMEASURED");
}

function proposalOf(experiment: EvolutionExperiment): string | null {
  const value = meta(experiment, "proposalId");
  return typeof value === "string" && value ? value : null;
}

function measuredTrials(experiment: EvolutionExperiment): number {
  const value = meta(experiment, "measuredTrials");
  return typeof value === "number" ? value : 0;
}

export interface ExperimentListProps {
  experiments: EvolutionExperiment[];
  t: TranslateFn;
  onPrepare?: (candidateId: string) => void;
  preparingId?: string | null;
  landing?: EvolutionLandingResult | null;
}

export function ExperimentList({
  experiments, t, onPrepare, preparingId, landing,
}: ExperimentListProps) {
  if (experiments.length === 0) {
    return (
      <p className="rounded-xl border border-border/40 bg-background/30 px-4 py-6 text-center text-xs text-muted-foreground">
        {t("evolution.experiment.empty")}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {experiments.map((experiment) => {
        const proposalId = proposalOf(experiment);
        const benchmark = benchmarkOf(experiment);
        const testsPassed = meta(experiment, "testsPassed");
        const target = meta(experiment, "targetPath");
        const targetDimension = meta(experiment, "targetDimension");
        const decision = meta(experiment, "decision");
        const targetLabel = typeof target === "string" && target
          ? target
          : typeof targetDimension === "string" && targetDimension
            ? targetDimension
            : experiment.suite;
        const canPrepare = Boolean(
          onPrepare && proposalId && testsPassed === true && benchmark === "UNMEASURED",
        );
        const prepared = landing && landing.candidateId === proposalId ? landing : null;
        return (
          <li key={experiment.id} className="rounded-xl border border-border/40 bg-background/30 p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-foreground">
                  {proposalId ?? experiment.id}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                  {targetLabel}
                  {typeof decision === "string" && decision ? ` A ${decision}` : ""}
                </p>
              </div>
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[10px]",
                  benchmark === "MEASURED"
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                    : "border-amber-400/30 bg-amber-400/10 text-amber-300",
                )}
              >
                {benchmark === "MEASURED"
                  ? t("evolution.experiment.benchmark.measured")
                  : t("evolution.experiment.benchmark.unmeasured")}
              </span>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
              {testsPassed === true && (
                <span className="inline-flex items-center gap-1 text-emerald-300">
                  <Check size={12} /> {t("evolution.experiment.testsPassed")}
                </span>
              )}
              {testsPassed === false && (
                <span className="inline-flex items-center gap-1 text-rose-300">
                  <X size={12} /> {t("evolution.experiment.testsFailed")}
                </span>
              )}
              {benchmark === "MEASURED" && (
                <span>{t("evolution.experiment.measuredTrials", { count: measuredTrials(experiment) })}</span>
              )}
              <span>{experiment.startedAt}</span>
            </div>

            {canPrepare && (
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onPrepare?.(proposalId as string)}
                  disabled={preparingId === proposalId}
                  className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
                >
                  {preparingId === proposalId
                    ? t("evolution.experiment.preparing")
                    : t("evolution.experiment.prepareLanding")}
                </button>
                {prepared && (
                  <span className="text-[10px] text-muted-foreground">
                    {t("evolution.experiment.prepared", { runId: prepared.runId })}
                  </span>
                )}
              </div>
            )}

            {prepared && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                {t("evolution.experiment.promotionHint", {
                  count: Number((prepared.preview as { filesChanged?: number }).filesChanged ?? 0),
                })}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function RslExperimentsPanel() {
  const t = useT();
  const [experiments, setExperiments] = useState<EvolutionExperiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preparingId, setPreparingId] = useState<string | null>(null);
  const [landing, setLanding] = useState<EvolutionLandingResult | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setExperiments(await listEvolutionExperimentsBrowser(50));
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load experiments");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const prepare = useCallback(async (candidateId: string) => {
    setPreparingId(candidateId);
    setError(null);
    try {
      setLanding(await prepareEvolutionLandingBrowser(candidateId));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "prepare landing failed");
    } finally {
      setPreparingId(null);
    }
  }, [load]);

  return (
    <section className="glass-card mt-5 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">
            {t("evolution.experiment.title")}
          </h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {t("evolution.experiment.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-border/50 p-1.5 text-muted-foreground transition hover:text-foreground"
          aria-label={t("evolution.experiment.refresh")}
        >
          <RefreshCcw size={14} />
        </button>
      </div>
      <div className="mb-4">
        <RslControlPanel />
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground">{t("evolution.experiment.loading")}</p>
      ) : error ? (
        <p className="rounded-xl border border-rose-400/30 bg-rose-400/5 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      ) : (
        <ExperimentList
          experiments={experiments}
          t={t}
          onPrepare={prepare}
          preparingId={preparingId}
          landing={landing}
        />
      )}
      <RslOperatorPanel />
    </section>
  );
}
