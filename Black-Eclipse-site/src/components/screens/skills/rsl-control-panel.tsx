"use client";

// Production controls for the RSL conductor: mode/lifecycle/budget visibility,
// an operator-triggered tick, and a staging form for code proposals. Everything
// goes through the operator-gated Next.js proxy; nothing applies automatically.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  activateEvolutionSurfaceStateBrowser,
  getEvolutionDriftBrowser,
  getEvolutionRslStatusBrowser,
  getEvolutionSurfacePreviewBrowser,
  listEvolutionStatesBrowser,
  listEvolutionSurfaceActivationsBrowser,
  promoteEvolutionStateBrowser,
  proposeEvolutionCandidateBrowser,
  rollbackEvolutionSurfaceActivationBrowser,
  tickEvolutionRslBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionCandidate,
  EvolutionDriftSignal,
  EvolutionHarnessState,
  EvolutionHarnessStates,
  EvolutionRslStatus,
  EvolutionRslTickResult,
  EvolutionSurfaceActivation,
  EvolutionSurfacePreview,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";
import { SurfaceActivationCard } from "./surface-activation-card";

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

export function RslControlPanel() {
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
  const [driftError, setDriftError] = useState<string | null>(null);

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

  const loadDrift = useCallback(async () => {
    setDriftError(null);
    try {
      setDrift(await getEvolutionDriftBrowser());
    } catch (err) {
      setDriftError(err instanceof Error ? err.message : t("evolution.drift.loading"));
    }
  }, [t]);
  useEffect(() => { void loadDrift(); }, [loadDrift]);

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
      setTickResult(await tickEvolutionRslBrowser());
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
          <button
            type="button"
            onClick={() => void loadDrift()}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.drift.refresh")}
          </button>
        </div>
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
