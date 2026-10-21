"use client";

// Production controls for the RSL conductor: mode/lifecycle/budget visibility,
// an operator-triggered tick, and a staging form for code proposals. Everything
// goes through the operator-gated Next.js proxy; nothing applies automatically.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  activateEvolutionSurfaceStateBrowser,
  createEvolutionDriftCandidateBrowser,
  getEvolutionDriftBrowser,
  getEvolutionDriftHistoryBrowser,
  getEvolutionDriftScopesBrowser,
  getEvolutionRslStatusBrowser,
  modelProposeEvolutionCandidateBrowser,
  getEvolutionSurfacePreviewBrowser,
  listEvolutionStatesBrowser,
  listEvolutionSurfaceActivationsBrowser,
  prepareEvolutionLandingBrowser,
  promoteEvolutionStateBrowser,
  proposeEvolutionCandidateBrowser,
  rollbackEvolutionSurfaceActivationBrowser,
  tickEvolutionRslBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionCandidate,
  EvolutionDriftCandidateResult,
  EvolutionDriftHistory,
  EvolutionDriftScopes,
  EvolutionDriftSignal,
  EvolutionHarnessState,
  EvolutionHarnessStates,
  EvolutionLandingResult,
  EvolutionModelProposeResult,
  EvolutionRslStatus,
  EvolutionRslTickResult,
  EvolutionSurfaceActivation,
  EvolutionSurfacePreview,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";
import { PromoteChange } from "@/components/chat/promote-change";
import {
  EVOLUTION_EVIDENCE_EVENT,
  EVOLUTION_VERIFIED_EVENT,
  type EvolutionEvidenceEventDetail,
  type EvolutionVerifiedEventDetail,
} from "@/lib/harness/evolution-events";
import { SurfaceActivationCard } from "./surface-activation-card";

function announceVerified(result: EvolutionRslTickResult) {
  if (typeof window === "undefined" || !result.candidateId) return;
  window.dispatchEvent(new CustomEvent<EvolutionVerifiedEventDetail>(
    EVOLUTION_VERIFIED_EVENT,
    {
      detail: {
        candidateId: result.candidateId,
        stateId: result.stateId,
        decision: result.decision,
      },
    },
  ));
}

const RSL_SCOPE_KEY = "eclipse.rsl.scope";
const DRIFT_SCOPE_KEY = "eclipse.rsl.driftScope";
const DRIFT_POLICY_KEY = "eclipse.rsl.driftPolicy";

interface DriftPolicy {
  window: number;
  baseline: number;
  threshold: number;
  minSamples: number;
}

function storedDriftPolicy(): DriftPolicy {
  const fallback: DriftPolicy = { window: 30, baseline: 100, threshold: 0.1, minSamples: 10 };
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(DRIFT_POLICY_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<DriftPolicy>;
    return {
      window: Math.max(1, Number(parsed.window) || fallback.window),
      baseline: Math.max(1, Number(parsed.baseline) || fallback.baseline),
      threshold: Math.max(0, Number(parsed.threshold) || fallback.threshold),
      minSamples: Math.max(1, Number(parsed.minSamples) || fallback.minSamples),
    };
  } catch {
    return fallback;
  }
}

function storedDriftScope(): string {
  if (typeof window === "undefined") return "global";
  try {
    return window.localStorage.getItem(RSL_SCOPE_KEY)
      ?? window.localStorage.getItem(DRIFT_SCOPE_KEY)
      ?? "global";
  } catch {
    return "global";
  }
}

const SAMPLE_OPS = JSON.stringify(
  [
    {
      op: "create",
      path: "python/harness/rsl_fixture.py",
      content: "VALUE = 1\n",
      reason: "operator-staged proposal",
    },
  ],
  null,
  2,
);

export function RslControlPanel({
  scope,
  onScopeChange,
}: {
  scope?: string;
  onScopeChange?: (scope: string) => void;
} = {}) {
  const t = useT();
  const [status, setStatus] = useState<EvolutionRslStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [ticking, setTicking] = useState(false);
  const [tickResult, setTickResult] = useState<EvolutionRslTickResult | null>(null);
  const [tickError, setTickError] = useState<string | null>(null);
  const [states, setStates] = useState<EvolutionHarnessStates | null>(null);
  const [statesError, setStatesError] = useState<string | null>(null);
  const [promotingId, setPromotingId] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [activations, setActivations] = useState<EvolutionSurfaceActivation[]>([]);
  const [rollingBackId, setRollingBackId] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    state: EvolutionHarnessState;
    data: EvolutionSurfacePreview;
  } | null>(null);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [activationScope, setActivationScope] = useState("eclipse-agent");
  const [drift, setDrift] = useState<EvolutionDriftSignal | null>(null);
  const [driftHistory, setDriftHistory] = useState<EvolutionDriftHistory | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [driftScopes, setDriftScopes] = useState<EvolutionDriftScopes | null>(null);
  const [initialPolicy] = useState(storedDriftPolicy);
  const [driftWindow, setDriftWindow] = useState(initialPolicy.window);
  const [driftBaseline, setDriftBaseline] = useState(initialPolicy.baseline);
  const [driftThreshold, setDriftThreshold] = useState(initialPolicy.threshold);
  const [driftMinSamples, setDriftMinSamples] = useState(initialPolicy.minSamples);
  const [localScope, setLocalScope] = useState(storedDriftScope);
  const driftScope = scope ?? localScope;
  const requestScope = driftScope === "all" ? "global" : driftScope;
  const chooseDriftScope = (next: string) => {
    if (scope === undefined) setLocalScope(next);
    onScopeChange?.(next);
    setDriftCandidate(null);
    try {
      window.localStorage.setItem(RSL_SCOPE_KEY, next);
      window.localStorage.setItem(DRIFT_SCOPE_KEY, next);
    } catch {
      // Persistence is best-effort; the in-memory selection still works.
    }
  };
  const [driftError, setDriftError] = useState<string | null>(null);
  const [driftCandidate, setDriftCandidate] = useState<EvolutionDriftCandidateResult | null>(null);
  const [driftCandidateLoading, setDriftCandidateLoading] = useState(false);
  const [driftProposal, setDriftProposal] = useState<EvolutionModelProposeResult | null>(null);
  const [driftProposalLoading, setDriftProposalLoading] = useState(false);
  const [driftProposalError, setDriftProposalError] = useState<string | null>(null);
  const [driftVerifyResult, setDriftVerifyResult] = useState<EvolutionRslTickResult | null>(null);
  const [driftVerifyLoading, setDriftVerifyLoading] = useState(false);
  const [driftVerifyError, setDriftVerifyError] = useState<string | null>(null);
  const [driftLanding, setDriftLanding] = useState<EvolutionLandingResult | null>(null);
  const [driftLandingLoading, setDriftLandingLoading] = useState(false);
  const [driftLandingError, setDriftLandingError] = useState<string | null>(null);

  const [candidateId, setCandidateId] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [ops, setOps] = useState(SAMPLE_OPS);
  const [proposing, setProposing] = useState(false);
  const [proposal, setProposal] = useState<EvolutionCandidate | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusError(null);
    try {
      setStatus(await getEvolutionRslStatusBrowser());
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "RSL status failed");
    }
  }, []);
  useEffect(() => { void loadStatus(); }, [loadStatus]);

  useEffect(() => {
    setHistoryOffset(0);
  }, [driftScope, driftWindow, driftBaseline, driftThreshold, driftMinSamples]);

  useEffect(() => {
    try {
      window.localStorage.setItem(DRIFT_POLICY_KEY, JSON.stringify({
        window: driftWindow,
        baseline: driftBaseline,
        threshold: driftThreshold,
        minSamples: driftMinSamples,
      }));
    } catch {
      // Persistence is best-effort; the in-memory policy still works.
    }
  }, [driftBaseline, driftMinSamples, driftThreshold, driftWindow]);

  const loadDrift = useCallback(async () => {
    setDriftError(null);
    try {
      const policy = {
        window: driftWindow,
        baseline: driftBaseline,
        threshold: driftThreshold,
      };
      const [signal, history, scopes] = await Promise.all([
        getEvolutionDriftBrowser({
          scope: requestScope, ...policy, minSamples: driftMinSamples,
        }),
        getEvolutionDriftHistoryBrowser({
          scope: requestScope, ...policy, minSamples: driftMinSamples,
          limit: 12, offset: historyOffset,
        }),
        getEvolutionDriftScopesBrowser({
          ...policy, minSamples: driftMinSamples, includeGlobal: false,
        }),
      ]);
      setDrift(signal);
      setDriftHistory(history);
      setDriftScopes(scopes);
    } catch (err) {
      setDriftError(err instanceof Error ? err.message : t("evolution.drift.loading"));
    }
  }, [driftBaseline, driftMinSamples, driftThreshold, driftWindow, historyOffset, requestScope, t]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadDrift(); }, 350);
    return () => window.clearTimeout(timer);
  }, [loadDrift]);

  useEffect(() => {
    const handler = () => { void loadDrift(); };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    return () => window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
  }, [loadDrift]);

  const openDriftCandidate = useCallback(async () => {
    setDriftCandidateLoading(true);
    setDriftError(null);
    try {
      setDriftCandidate(await createEvolutionDriftCandidateBrowser({
        scope: requestScope,
        window: driftWindow,
        baseline: driftBaseline,
        threshold: driftThreshold,
        minSamples: driftMinSamples,
      }));
    } catch (err) {
      setDriftError(err instanceof Error ? err.message : "drift candidate failed");
    } finally {
      setDriftCandidateLoading(false);
    }
  }, [driftBaseline, driftMinSamples, driftThreshold, driftWindow, requestScope]);

  const proposeDriftCandidate = useCallback(async (candidateId: string) => {
    setDriftProposalLoading(true);
    setDriftProposalError(null);
    setDriftProposal(null);
    try {
      setDriftProposal(await modelProposeEvolutionCandidateBrowser(candidateId));
    } catch (err) {
      setDriftProposalError(
        err instanceof Error ? err.message : t("evolution.drift.proposalError"),
      );
    } finally {
      setDriftProposalLoading(false);
    }
  }, [t]);

  const loadStates = useCallback(async () => {
    setStatesError(null);
    try {
      const [nextStates, nextActivations] = await Promise.all([
        listEvolutionStatesBrowser({ limit: 50 }),
        listEvolutionSurfaceActivationsBrowser(20),
      ]);
      setStates(nextStates);
      setActivations(nextActivations);
    } catch (err) {
      setStatesError(err instanceof Error ? err.message : t("evolution.states.error"));
    }
  }, [t]);
  useEffect(() => { void loadStates(); }, [loadStates]);

  const verifyDriftProposal = useCallback(async () => {
    setDriftVerifyLoading(true);
    setDriftVerifyError(null);
    setDriftVerifyResult(null);
    try {
      const result = await tickEvolutionRslBrowser();
      setDriftVerifyResult(result);
      announceVerified(result);
      await Promise.all([loadStates(), loadDrift()]);
    } catch (err) {
      setDriftVerifyError(
        err instanceof Error ? err.message : t("evolution.drift.verifyError"),
      );
    } finally {
      setDriftVerifyLoading(false);
    }
  }, [loadDrift, loadStates, t]);

  const prepareDriftLanding = useCallback(async (candidateId: string) => {
    setDriftLandingLoading(true);
    setDriftLandingError(null);
    setDriftLanding(null);
    try {
      setDriftLanding(await prepareEvolutionLandingBrowser(candidateId));
    } catch (err) {
      setDriftLandingError(err instanceof Error ? err.message : "prepare landing failed");
    } finally {
      setDriftLandingLoading(false);
    }
  }, []);

  const promoteState = useCallback(async (state: EvolutionHarnessState) => {
    setPromotingId(state.id);
    setStatesError(null);
    try {
      await promoteEvolutionStateBrowser(state.id);
      await loadStates();
    } catch (err) {
      setStatesError(err instanceof Error ? err.message : t("evolution.states.error"));
    } finally {
      setPromotingId(null);
    }
  }, [loadStates, t]);

  const previewState = useCallback(async (state: EvolutionHarnessState, scope: string) => {
    setPreviewingId(state.id);
    setStatesError(null);
    try {
      const data = await getEvolutionSurfacePreviewBrowser(state.id, scope);
      setPreview({ state, data });
      setActivationScope(data.scope);
    } catch (err) {
      setStatesError(err instanceof Error ? err.message : t("evolution.states.error"));
    } finally {
      setPreviewingId(null);
    }
  }, [t]);

  const activateState = useCallback(async (state: EvolutionHarnessState, scope?: string) => {
    setActivatingId(state.id);
    setStatesError(null);
    try {
      await activateEvolutionSurfaceStateBrowser(state.id, scope);
      setPreview(null);
      await loadStates();
    } catch (err) {
      setStatesError(err instanceof Error ? err.message : t("evolution.states.error"));
    } finally {
      setActivatingId(null);
    }
  }, [loadStates, t]);

  const rollbackActivation = useCallback(async (activation: EvolutionSurfaceActivation) => {
    setRollingBackId(activation.id);
    setStatesError(null);
    try {
      await rollbackEvolutionSurfaceActivationBrowser(activation.id);
      await loadStates();
    } catch (err) {
      setStatesError(err instanceof Error ? err.message : t("evolution.states.error"));
    } finally {
      setRollingBackId(null);
    }
  }, [loadStates, t]);

  const tick = useCallback(async () => {
    setTicking(true);
    setTickError(null);
    setTickResult(null);
    try {
      const result = await tickEvolutionRslBrowser();
      setTickResult(result);
      announceVerified(result);
      await loadStatus();
    } catch (err) {
      setTickError(err instanceof Error ? err.message : "RSL tick failed");
    } finally {
      setTicking(false);
    }
  }, [loadStatus]);

  const stageProposal = useCallback(async () => {
    setProposing(true);
    setProposalError(null);
    setProposal(null);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(ops);
      } catch {
        throw new Error(t("evolution.propose.invalidJson"));
      }
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error(t("evolution.propose.invalidJson"));
      }
      const result = await proposeEvolutionCandidateBrowser(candidateId.trim(), {
        targetPath: targetPath.trim() || null,
        ops: parsed as Array<Record<string, unknown>>,
      });
      setProposal(result.candidate);
    } catch (err) {
      setProposalError(err instanceof Error ? err.message : "proposal failed");
    } finally {
      setProposing(false);
    }
  }, [candidateId, ops, t, targetPath]);

  const inputClass =
    "w-full rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40";
  const overviewSignals = (driftScopes?.signals ?? []).filter((row) => (
    row.signal.status !== "unmeasured"
    || row.scope === driftScope
    || (row.scope === "global" && driftScope === "all")
  ));
  const hiddenOverview = (driftScopes?.signals.length ?? 0) - overviewSignals.length;

  return (
    <section className="glass-card-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold text-foreground">{t("evolution.rsl.title")}</h4>
          <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.rsl.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadStatus()}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.rsl.refresh")}
          </button>
          <button
            type="button"
            onClick={() => void tick()}
            disabled={ticking || status?.mode === "off"}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {ticking ? t("evolution.rsl.ticking") : t("evolution.rsl.tick")}
          </button>
        </div>
      </div>

      {statusError && (
        <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
          {statusError}
        </p>
      )}
      {status ? (
        <div className="mt-2 grid gap-1 text-[10px] text-muted-foreground sm:grid-cols-3">
          <span className={cn(
            "font-medium",
            status.mode === "off" ? "text-amber-300" : "text-emerald-300",
          )}>
            {t("evolution.rsl.mode", { mode: status.mode })}
          </span>
          <span>
            {t("evolution.rsl.lifecycle", {
              state: status.running ? "running" : "stopped",
              busy: status.busy ? "busy" : "idle",
            })}
          </span>
          <span>
            {t("evolution.rsl.budget", {
              used: status.startedToday,
              max: status.maxExperimentsPerDay,
              remaining: status.remainingToday,
            })}
          </span>
          <span>{t("evolution.rsl.k", { k: status.k })}</span>
          {status.objective && (
            <span>{t("evolution.rsl.objective", { objective: status.objective })}</span>
          )}
          {status.driftWatch && (
            <span
              title={Object.entries(status.driftWatch.last)
                .map(([scope, state]) => `${scope}: ${state}`)
                .join(", ")}
            >
              {t("evolution.rsl.driftWatch", {
                state: status.driftWatch.enabled
                  ? `${status.driftWatch.intervalSeconds}s ${status.driftWatch.running ? "running" : "stopped"}`
                  : "off",
              })}
            </span>
          )}
          {status.tickSeconds != null && (
            <span>{t("evolution.rsl.tickSeconds", { seconds: status.tickSeconds })}</span>
          )}
        </div>
      ) : (
        !statusError && <p className="mt-2 text-[10px] text-muted-foreground">{t("evolution.rsl.loading")}</p>
      )}
      {status?.mode === "off" && (
        <p className="mt-2 rounded-lg border border-amber-400/30 bg-amber-400/5 px-2 py-1 text-[10px] text-amber-300">
          {t("evolution.rsl.offHint")}
        </p>
      )}
      {tickError && <p className="mt-2 text-[10px] text-rose-300">{tickError}</p>}
      {tickResult && (
        <p className="mt-2 text-[10px] text-muted-foreground">
          {t("evolution.rsl.tickResult", {
            mode: tickResult.mode,
            count: tickResult.processed?.length ?? 0,
            decision: tickResult.decision ?? "none",
          })}
        </p>
      )}

      <div className="mt-4 border-t border-border/40 pt-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h5 className="text-xs font-semibold text-foreground">{t("evolution.drift.title")}</h5>
            <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.drift.subtitle")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <label className="text-[10px] text-muted-foreground">
              {t("evolution.drift.scope")}
            </label>
            <select
              value={driftScope}
              onChange={(event) => chooseDriftScope(event.target.value)}
              className="rounded-lg border border-border/50 bg-background/40 px-1.5 py-1 text-[10px] text-foreground"
            >
              {Array.from(new Set([
                "all",
                ...(drift?.availableScopes ?? []).filter((item) => item !== "global"),
                ...(driftScope !== "all" ? [driftScope] : []),
              ])).map((item) => (
                <option key={item} value={item}>
                  {item === "all" ? t("evolution.experiment.scopeAll") : item}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
              {t("evolution.drift.window")}
              <input
                type="number"
                min={1}
                max={200}
                value={driftWindow}
                onChange={(event) => setDriftWindow(Math.max(1, Number(event.target.value) || 1))}
                className="w-12 rounded border border-border/50 bg-background/40 px-1 py-1 text-[10px] text-foreground"
              />
            </label>
            <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
              {t("evolution.drift.baseline")}
              <input
                type="number"
                min={1}
                max={500}
                value={driftBaseline}
                onChange={(event) => setDriftBaseline(Math.max(1, Number(event.target.value) || 1))}
                className="w-14 rounded border border-border/50 bg-background/40 px-1 py-1 text-[10px] text-foreground"
              />
            </label>
            <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
              {t("evolution.drift.threshold")}
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={driftThreshold}
                onChange={(event) => setDriftThreshold(Math.max(0, Number(event.target.value) || 0))}
                className="w-14 rounded border border-border/50 bg-background/40 px-1 py-1 text-[10px] text-foreground"
              />
            </label>
            <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
              {t("evolution.drift.minSamples")}
              <input
                type="number"
                min={1}
                max={200}
                value={driftMinSamples}
                onChange={(event) => setDriftMinSamples(Math.max(1, Number(event.target.value) || 1))}
                className="w-12 rounded border border-border/50 bg-background/40 px-1 py-1 text-[10px] text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadDrift()}
              className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
            >
              {t("evolution.drift.refresh")}
            </button>
          </div>
        </div>
        {overviewSignals.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1 text-[9px]">
            <span
              className="text-muted-foreground"
              title={t("evolution.drift.overviewHint")}
            >
              {t("evolution.drift.overview")}
            </span>
            {overviewSignals.map(({ scope: item, signal }) => (
              <button
                key={item}
                type="button"
                onClick={() => chooseDriftScope(item === "global" ? "all" : item)}
                className={cn(
                  "rounded border px-1.5 py-0.5 transition",
                  driftScope === item || (item === "global" && driftScope === "all")
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : signal.status === "drift"
                      ? "border-rose-400/30 bg-rose-400/10 text-rose-300 hover:bg-rose-400/15"
                      : signal.status === "stable"
                        ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15"
                        : "border-border/40 bg-background/30 text-muted-foreground hover:text-foreground",
                )}
              >
                {item === "global" ? t("evolution.experiment.scopeAll") : item}
                {" "}
                {signal.drop == null
                  ? signal.status
                  : `${Math.round(signal.drop * 100)}%`}
              </button>
            ))}
            {hiddenOverview > 0 && (
              <span className="text-muted-foreground">
                {t("evolution.drift.overviewHidden", { count: hiddenOverview })}
              </span>
            )}
          </div>
        )}
        {driftError && <p className="mt-2 text-[10px] text-rose-300">{driftError}</p>}
        {!drift && !driftError && (
          <p className="mt-2 text-[10px] text-muted-foreground">{t("evolution.drift.loading")}</p>
        )}
        {drift && (
          <div className="mt-2 space-y-0.5 text-[10px] text-muted-foreground">
            <p className={drift.status === "drift" ? "text-rose-300" : "text-emerald-300"}>
              {t("evolution.drift.status", { status: drift.status })}
            </p>
            {drift.status === "unmeasured" ? (
              <p>{t("evolution.drift.unmeasured")}</p>
            ) : (
              <>
                <p>{t("evolution.drift.rates", {
                  recent: `${Math.round((drift.current.rate ?? 0) * 100)}% (${drift.current.n})`,
                  baseline: `${Math.round((drift.baseline.rate ?? 0) * 100)}% (${drift.baseline.n})`,
                })}</p>
                <p>{t("evolution.drift.drop", { drop: drift.drop ?? "UNMEASURED" })}</p>
              </>
            )}
            {drift.reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
            {driftHistory && driftHistory.points.length > 1 && (
              <div className="mt-1">
                <p>
                  {t("evolution.drift.history")}
                  {driftHistory.truncated
                    ? ` (${t("evolution.drift.historyTruncated", {
                      computed: driftHistory.computedPoints,
                      requested: driftHistory.requestedPoints,
                    })})`
                    : ""}
                </p>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {driftHistory.points.map((point) => (
                    <span
                      key={point.offset}
                      title={point.at ?? undefined}
                      className={cn(
                        "rounded border px-1.5 py-0.5 text-[9px]",
                        point.status === "drift"
                          ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                          : point.status === "stable"
                            ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                            : "border-border/40 bg-background/30 text-muted-foreground",
                      )}
                    >
                      {point.offset === 0 ? t("evolution.drift.historyNow") : `-${point.offset}`}
                      {" "}
                      {point.drop == null ? point.status : `${Math.round(point.drop * 100)}%`}
                    </span>
                  ))}
                </div>
                <div className="mt-1 flex h-8 items-end gap-0.5">
                  {driftHistory.points.slice().reverse().map((point) => (
                    <span
                      key={`bar:${point.offset}`}
                      title={`-${point.offset}: ${point.status}`}
                      className={cn(
                        "min-h-[2px] flex-1 rounded-t",
                        point.status === "drift" ? "bg-rose-400/60" : "bg-emerald-400/40",
                      )}
                      style={{
                        height: `${Math.max(6, ((point.drop ?? 0) / Math.max(0.01, ...driftHistory.points.map((row) => row.drop ?? 0))) * 100)}%`,
                      }}
                    />
                  ))}
                </div>
                <div className="mt-1 flex gap-2 text-[9px]">
                  <button
                    type="button"
                    onClick={() => setHistoryOffset((value) => Math.max(0, value - 12))}
                    disabled={historyOffset === 0}
                    className="rounded border border-border/40 px-1.5 py-0.5 text-muted-foreground disabled:opacity-40"
                  >
                    {t("evolution.drift.historyNewer")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setHistoryOffset((value) => value + 12)}
                    className="rounded border border-border/40 px-1.5 py-0.5 text-muted-foreground"
                  >
                    {t("evolution.drift.historyOlder")}
                  </button>
                </div>
              </div>
            )}
            {drift.status === "drift" && (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void openDriftCandidate()}
                  disabled={driftCandidateLoading}
                  className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-2 py-1 text-[10px] text-rose-300 transition hover:bg-rose-400/15 disabled:opacity-50"
                >
                  {driftCandidateLoading
                    ? t("evolution.drift.openingCandidate")
                    : t("evolution.drift.openCandidate")}
                </button>
                {driftCandidate?.candidate && (
                  <>
                    <span className="text-emerald-300">
                      {driftCandidate.created
                        ? t("evolution.drift.candidateCreated", { id: driftCandidate.candidate.id })
                        : t("evolution.drift.candidateExists", { id: driftCandidate.candidate.id })}
                    </span>
                    <span className="rounded border border-border/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {t("evolution.drift.candidateScope", {
                        scope: driftCandidate.signal.scope ?? requestScope,
                      })}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        window.dispatchEvent(
                          new CustomEvent<EvolutionEvidenceEventDetail>(
                            EVOLUTION_EVIDENCE_EVENT,
                            { detail: { candidateId: driftCandidate.candidate!.id } },
                          ),
                        );
                      }}
                      className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-400/15"
                    >
                      {t("evolution.drift.viewEvidence")}
                    </button>
                    <button
                      type="button"
                      onClick={() => void proposeDriftCandidate(driftCandidate.candidate!.id)}
                      disabled={driftProposalLoading}
                      className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-400/15 disabled:opacity-50"
                    >
                      {driftProposalLoading
                        ? t("evolution.drift.proposing")
                        : t("evolution.drift.propose")}
                    </button>
                    {driftProposal && (
                      <span className="text-emerald-300">
                        {t("evolution.drift.proposed", { count: driftProposal.children.length })}
                      </span>
                    )}
                    {driftProposalError && (
                      <span className="text-rose-300">{driftProposalError}</span>
                    )}
                    {driftProposal && (
                      <button
                        type="button"
                        onClick={() => void verifyDriftProposal()}
                        disabled={driftVerifyLoading}
                        className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-300 transition hover:bg-emerald-400/15 disabled:opacity-50"
                      >
                        {driftVerifyLoading
                          ? t("evolution.drift.verifying")
                          : t("evolution.drift.verify")}
                      </button>
                    )}
                    {driftVerifyResult?.candidateId && (
                      <span className={driftVerifyResult.decision?.includes("rejected") ? "text-rose-300" : "text-emerald-300"}>
                        {t("evolution.drift.verified", {
                          id: driftVerifyResult.candidateId,
                          decision: driftVerifyResult.decision ?? "none",
                          benchmark: driftVerifyResult.benchmark ?? "UNMEASURED",
                        })}
                      </span>
                    )}
                    {driftVerifyResult && !driftVerifyResult.candidateId && (
                      <span className="text-muted-foreground">
                        {t("evolution.drift.verifyEmpty")}
                      </span>
                    )}
                    {driftVerifyError && (
                      <span className="text-rose-300">{driftVerifyError}</span>
                    )}
                    {driftVerifyResult?.candidateId
                      && ["tests_passed", "benchmark_accepted"].includes(
                        driftVerifyResult.decision ?? "",
                      ) && (
                      <button
                        type="button"
                        onClick={() => void prepareDriftLanding(driftVerifyResult.candidateId!)}
                        disabled={driftLandingLoading}
                        className="rounded-lg border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
                      >
                        {driftLandingLoading
                          ? t("evolution.drift.preparingLanding")
                          : t("evolution.drift.prepareLanding")}
                      </button>
                    )}
                    {driftLanding && (
                      <div className="w-full">
                        <span className="text-[10px] text-emerald-300">
                          {t("evolution.drift.landingPrepared", { runId: driftLanding.runId })}
                        </span>
                        <PromoteChange runId={driftLanding.runId} compact />
                      </div>
                    )}
                    {driftLandingError && (
                      <span className="text-rose-300">{driftLandingError}</span>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 border-t border-border/40 pt-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h5 className="text-xs font-semibold text-foreground">{t("evolution.states.title")}</h5>
            <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.states.subtitle")}</p>
          </div>
          <button
            type="button"
            onClick={() => void loadStates()}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.states.refresh")}
          </button>
        </div>
        {statesError && (
          <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
            {statesError}
          </p>
        )}
        {!states && !statesError && (
          <p className="mt-2 text-[10px] text-muted-foreground">{t("evolution.states.loading")}</p>
        )}
        {states && (
          <div className="mt-2 space-y-1.5">
            {states.currents.length > 0 ? (
              states.currents.map((state) => (
                <div key={state.id} className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-2 py-1.5 text-[10px]">
                  <span className="font-medium text-emerald-300">
                    {t("evolution.states.current", { scope: state.scope })}
                  </span>
                  <span className="ml-2 text-muted-foreground">
                    {t("evolution.states.utility", {
                      value: state.utility == null ? "UNMEASURED" : state.utility.toFixed(3),
                    })}
                  </span>
                  {state.candidateId && (
                    <span className="ml-2 text-muted-foreground">
                      {t("evolution.states.candidate", { id: state.candidateId })}
                    </span>
                  )}
                </div>
              ))
            ) : (
              <p className="text-[10px] text-muted-foreground">{t("evolution.states.none")}</p>
            )}
            {states.states.length === 0 && (
              <p className="text-[10px] text-muted-foreground">{t("evolution.states.empty")}</p>
            )}
            {states.states
              .filter((state) => state.status === "candidate")
              .slice(0, 8)
              .map((state) => (
                <div key={state.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/30 px-2 py-1.5 text-[10px]">
                  <span className="min-w-0 truncate text-muted-foreground">
                    {state.scope} · {t("evolution.states.utility", {
                      value: state.utility == null ? "UNMEASURED" : state.utility.toFixed(3),
                    })}
                    {state.candidateId ? ` · ${state.candidateId}` : ""}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void previewState(state, state.scope || "eclipse-agent")}
                      disabled={previewingId === state.id}
                      className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-400/15 disabled:opacity-50"
                    >
                      {previewingId === state.id
                        ? t("evolution.states.previewing")
                        : t("evolution.states.preview")}
                    </button>
                    <button
                      type="button"
                      onClick={() => void activateState(state)}
                      disabled={activatingId === state.id}
                      className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-300 transition hover:bg-emerald-400/15 disabled:opacity-50"
                    >
                      {activatingId === state.id
                        ? t("evolution.states.activating")
                        : t("evolution.states.activate")}
                    </button>
                    <button
                      type="button"
                      onClick={() => void promoteState(state)}
                      disabled={promotingId === state.id}
                      className="rounded-lg border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
                    >
                      {promotingId === state.id
                        ? t("evolution.states.promoting")
                        : t("evolution.states.promote")}
                    </button>
                  </div>
                </div>
              ))}
          </div>
        )}
        <div className="mt-3 border-t border-border/30 pt-2">
          <p className="text-[10px] font-medium text-muted-foreground">
            {t("evolution.states.activations")}
          </p>
          {activations.length === 0 ? (
            <p className="mt-1 text-[10px] text-muted-foreground">
              {t("evolution.states.noActivations")}
            </p>
          ) : (
            activations.map((activation) => (
              <div key={activation.id} className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-border/30 px-2 py-1.5 text-[10px]">
                <span className="min-w-0 truncate text-muted-foreground">
                  {activation.scope} · {activation.stateId}
                  {activation.rolledBackAt
                    ? " · rolled back"
                    : activation.active === false
                      ? " · inactive"
                      : ""}
                </span>
                {!activation.rolledBackAt && activation.active !== false && (
                  <button
                    type="button"
                    onClick={() => void rollbackActivation(activation)}
                    disabled={rollingBackId === activation.id}
                    className="shrink-0 rounded-lg border border-rose-400/30 bg-rose-400/10 px-2 py-1 text-[10px] text-rose-300 transition hover:bg-rose-400/15 disabled:opacity-50"
                  >
                    {rollingBackId === activation.id
                      ? t("evolution.states.activating")
                      : t("evolution.states.rollback")}
                  </button>
                )}
              </div>
            ))
          )}
        </div>
        {preview && (
          <div className="mt-3">
            <SurfaceActivationCard
              state={preview.state}
              preview={preview.data}
              scope={activationScope}
              onScopeChange={(next) => {
                setActivationScope(next);
                void previewState(preview.state, next);
              }}
              onActivate={() => void activateState(preview.state, activationScope)}
              onClose={() => setPreview(null)}
              activating={activatingId === preview.state.id}
            />
          </div>
        )}
      </div>

      <div className="mt-4 border-t border-border/40 pt-3">
        <h5 className="text-xs font-semibold text-foreground">{t("evolution.propose.title")}</h5>
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.propose.subtitle")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input
            className={inputClass}
            placeholder={t("evolution.propose.candidate")}
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.propose.target")}
            value={targetPath}
            onChange={(event) => setTargetPath(event.target.value)}
          />
          <textarea
            className={`${inputClass} font-mono sm:col-span-2`}
            rows={6}
            aria-label={t("evolution.propose.ops")}
            value={ops}
            onChange={(event) => setOps(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void stageProposal()}
            disabled={proposing || !candidateId.trim() || !ops.trim()}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {proposing ? t("evolution.propose.staging") : t("evolution.propose.stage")}
          </button>
          {proposal && (
            <span className="text-[10px] text-emerald-300">
              {t("evolution.propose.staged", { id: proposal.id })}
            </span>
          )}
          {proposalError && <span className="text-[10px] text-rose-300">{proposalError}</span>}
        </div>
      </div>
    </section>
  );
}
