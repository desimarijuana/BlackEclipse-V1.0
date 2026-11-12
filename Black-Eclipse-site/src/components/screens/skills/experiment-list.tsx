"use client";

// The shared experiment evidence list. Used by the main RSL panel and by the
// candidate evidence view, so the benchmark badge, critical-regression block
// and prepare-landing affordance stay identical in both places.

import { Check, X } from "@/lib/icons";
import type { TranslateFn } from "@/lib/i18n/translate";
import type {
  EvolutionExperiment,
  EvolutionLandingResult,
} from "@/lib/harness/clients/evolution-client";
import { cn } from "@/lib/utils";

function meta(experiment: EvolutionExperiment, key: string): unknown {
  return (experiment.metadata ?? {})[key];
}

function benchmarkOf(experiment: EvolutionExperiment): string {
  return String(meta(experiment, "benchmark") ?? experiment.config?.benchmark ?? "UNMEASURED");
}

export function experimentCandidateId(experiment: EvolutionExperiment): string | null {
  const value = meta(experiment, "proposalId");
  return typeof value === "string" && value ? value : null;
}

function proposalOf(experiment: EvolutionExperiment): string | null {
  return experimentCandidateId(experiment);
}

function measuredTrials(experiment: EvolutionExperiment): number {
  const value = meta(experiment, "measuredTrials");
  return typeof value === "number" ? value : 0;
}

function criticalDeltasOf(experiment: EvolutionExperiment): Array<{
  taskId: string;
  before: number | null;
  after: number | null;
}> {
  const record = meta(experiment, "decisionRecord");
  if (!record || typeof record !== "object") return [];
  const rows = (record as { criticalDeltas?: unknown }).criticalDeltas;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    if (!row || typeof row !== "object") return [];
    const value = row as Record<string, unknown>;
    if (typeof value.taskId !== "string" || !value.taskId) return [];
    return [{
      taskId: value.taskId,
      before: typeof value.before === "number" ? value.before : null,
      after: typeof value.after === "number" ? value.after : null,
    }];
  });
}

export interface ExperimentListProps {
  experiments: EvolutionExperiment[];
  t: TranslateFn;
  onPrepare?: (candidateId: string) => void;
  onViewEvidence?: (candidateId: string) => void;
  preparingId?: string | null;
  landing?: EvolutionLandingResult | null;
}

export function ExperimentList({
  experiments, t, onPrepare, onViewEvidence, preparingId, landing,
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
        const criticalDeltas = criticalDeltasOf(experiment);
        const testsPassed = meta(experiment, "testsPassed");
        const target = meta(experiment, "targetPath");
        const targetDimension = meta(experiment, "targetDimension");
        const decision = meta(experiment, "decision");
        const subjectType = String(meta(experiment, "subjectType") ?? "").toLowerCase();
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
                  {typeof decision === "string" && decision ? ` · ${decision}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                {subjectType === "drift" && (
                  <span className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] text-rose-300">
                    {t("evolution.experiment.driftCandidate")}
                  </span>
                )}
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

            {criticalDeltas.length > 0 && (
              <div className="mt-1.5 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
                <p>{t("evolution.experiment.criticalRegressions", {
                  count: criticalDeltas.length,
                })}</p>
                {criticalDeltas.map((row) => (
                  <p key={`critical:${row.taskId}`}>
                    {t("evolution.experiment.criticalRegression", {
                      taskId: row.taskId,
                      before: row.before == null ? "UNMEASURED" : row.before.toFixed(3),
                      after: row.after == null ? "UNMEASURED" : row.after.toFixed(3),
                    })}
                  </p>
                ))}
              </div>
            )}

            {(canPrepare || (onViewEvidence && proposalId)) && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {canPrepare && (
                  <>
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
                  </>
                )}
                {onViewEvidence && proposalId && (
                  <button
                    type="button"
                    onClick={() => onViewEvidence(proposalId)}
                    className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[11px] text-sky-300 transition hover:bg-sky-400/15"
                  >
                    {t("evolution.experiment.viewEvidence")}
                  </button>
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
