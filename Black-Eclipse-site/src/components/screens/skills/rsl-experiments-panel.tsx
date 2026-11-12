"use client";

// RSL experiment review — the operator's evidence surface inside the learning
// journey. It reads the runtime's recorded experiments, never invents a metric,
// and "Prepare landing" only builds the existing promotion preview (the
// single-use approval is still the only write path).

import { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "@/lib/icons";
import { useT } from "@/lib/i18n/use-t";
import {
  getEvolutionMetricsBrowser,
  listEvolutionExperimentsBrowser,
  prepareEvolutionLandingBrowser,
} from "@/lib/harness/clients/evolution-browser";
import { EVOLUTION_VERIFIED_EVENT } from "@/lib/harness/evolution-events";
import type {
  EvolutionExperiment,
  EvolutionLandingResult,
  EvolutionMetrics,
} from "@/lib/harness/clients/evolution-client";
import { CandidateEvidencePanel } from "./candidate-evidence-panel";
import { experimentCandidateId, ExperimentList } from "./experiment-list";
import { ParetoFrontierCard } from "./pareto-frontier-card";
import { RslControlPanel } from "./rsl-control-panel";
import { RslOperatorPanel } from "./rsl-operator-panel";

const SCOPE_STORAGE_KEY = "eclipse.rsl.scope";
const LEGACY_SCOPE_KEYS = ["eclipse.rsl.experimentScope", "eclipse.rsl.driftScope"];

function storedScope(): string {
  if (typeof window === "undefined") return "all";
  try {
    const stored = window.localStorage.getItem(SCOPE_STORAGE_KEY);
    if (stored) return stored;
    for (const key of LEGACY_SCOPE_KEYS) {
      const legacy = window.localStorage.getItem(key);
      if (legacy) return legacy;
    }
    return "all";
  } catch {
    return "all";
  }
}

function isTodayUtc(stamp: string): boolean {
  const parsed = new Date(stamp);
  if (Number.isNaN(parsed.getTime())) return false;
  const now = new Date();
  return parsed.getUTCFullYear() === now.getUTCFullYear()
    && parsed.getUTCMonth() === now.getUTCMonth()
    && parsed.getUTCDate() === now.getUTCDate();
}

export function RslExperimentsPanel() {
  const t = useT();
  const [experiments, setExperiments] = useState<EvolutionExperiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preparingId, setPreparingId] = useState<string | null>(null);
  const [landing, setLanding] = useState<EvolutionLandingResult | null>(null);
  const [evidenceCandidateId, setEvidenceCandidateId] = useState<string | undefined>(undefined);
  const [today, setToday] = useState<EvolutionMetrics | null>(null);
  const [scope, setScope] = useState(storedScope);

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

  const loadToday = useCallback(async () => {
    try {
      setToday(await getEvolutionMetricsBrowser(1));
    } catch {
      setToday(null);
    }
  }, []);
  useEffect(() => { void loadToday(); }, [loadToday]);

  useEffect(() => {
    const handler = () => {
      void load();
      void loadToday();
    };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    return () => window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
  }, [load, loadToday]);

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

  const scopes = Array.from(new Set([
    "all",
    ...experiments.map((experiment) => String(
      (experiment.metadata ?? {}).scope ?? "global",
    )),
    ...(scope !== "all" ? [scope] : []),
  ]));
  const chooseScope = (next: string) => {
    setScope(next);
    try {
      window.localStorage.setItem(SCOPE_STORAGE_KEY, next);
    } catch {
      // Persistence is best-effort; the in-memory selection still works.
    }
  };
  const visibleExperiments = scope === "all"
    ? experiments
    : experiments.filter((experiment) => String(
      (experiment.metadata ?? {}).scope ?? "global",
    ) === scope);
  const todayExperiments = visibleExperiments
    .filter((experiment) => isTodayUtc(experiment.startedAt))
    .slice(0, 8);
  const todayMeasured = todayExperiments.filter((experiment) => String(
    (experiment.metadata ?? {}).benchmark ?? "UNMEASURED",
  ).toUpperCase() === "MEASURED");
  const todayAccepted = todayMeasured.filter((experiment) => {
    const metadata = experiment.metadata ?? {};
    const decision = String(metadata.decision ?? "").toLowerCase();
    return metadata.accepted === true
      || decision.includes("accepted")
      || decision === "composed"
      || decision === "tests_passed";
  }).length;
  const todayCounts = {
    experiments: todayExperiments.length,
    accepted: todayAccepted,
    rejected: todayMeasured.length - todayAccepted,
    unmeasured: todayExperiments.length - todayMeasured.length,
  };

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
        <RslControlPanel scope={scope} onScopeChange={chooseScope} />
        <ParetoFrontierCard scope={scope} />
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border/40 bg-background/30 px-2.5 py-1.5 text-[10px] text-muted-foreground">
        <span className="font-medium text-foreground">{t("evolution.experiment.todayTitle")}</span>
        <label>{t("evolution.experiment.scope")}</label>
        <select
          value={scope}
          onChange={(event) => chooseScope(event.target.value)}
          className="rounded-lg border border-border/50 bg-background/40 px-1.5 py-0.5 text-[10px] text-foreground"
        >
          {scopes.map((item) => (
            <option key={item} value={item}>
              {item === "all" ? t("evolution.experiment.scopeAll") : item}
            </option>
          ))}
        </select>
        {" A "}
        {scope === "all" && today?.rsl_experiments == null ? (
          <span>{t("evolution.experiment.todayUnmeasured")}</span>
        ) : (
          <span>{t("evolution.experiment.todayCounts", scope === "all" ? {
            experiments: today?.rsl_experiments ?? 0,
            accepted: today?.rsl_accepted ?? 0,
            rejected: today?.rsl_rejected ?? 0,
            unmeasured: today?.rsl_unmeasured ?? 0,
          } : todayCounts)}</span>
        )}
      </div>
      {todayExperiments.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
          <span>{t("evolution.experiment.todayCandidates")}</span>
          {todayExperiments.map((experiment) => {
            const candidateId = experimentCandidateId(experiment);
            if (!candidateId) return null;
            const decision = String(
              (experiment.metadata ?? {}).decision
              ?? experiment.config?.benchmark
              ?? "-",
            );
            const drift = String(
              (experiment.metadata ?? {}).subjectType ?? "",
            ).toLowerCase() === "drift";
            return (
              <button
                key={experiment.id}
                type="button"
                onClick={() => setEvidenceCandidateId(candidateId)}
                className="rounded-full border border-sky-400/30 bg-sky-400/10 px-2 py-0.5 text-sky-300 transition hover:bg-sky-400/15"
              >
                {drift && (
                  <span className="mr-1 rounded-full border border-rose-400/30 bg-rose-400/10 px-1.5 text-[9px] text-rose-300">
                    {t("evolution.experiment.driftCandidate")}
                  </span>
                )}
                {candidateId} · {decision}
              </button>
            );
          })}
        </div>
      )}
      {loading ? (
        <p className="text-xs text-muted-foreground">{t("evolution.experiment.loading")}</p>
      ) : error ? (
        <p className="rounded-xl border border-rose-400/30 bg-rose-400/5 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      ) : (
        <ExperimentList
          experiments={visibleExperiments}
          t={t}
          onPrepare={prepare}
          onViewEvidence={setEvidenceCandidateId}
          preparingId={preparingId}
          landing={landing}
        />
      )}
      <CandidateEvidencePanel initialCandidateId={evidenceCandidateId} scope={scope} />
      <RslOperatorPanel />
    </section>
  );
}
