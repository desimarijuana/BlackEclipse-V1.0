"use client";

// The autonomy card: the operator-triggered activation path, its kill switch
// and its daily budget. The runtime re-checks evidence on every apply; this
// card never duplicates the admission policy and a refusal is shown, not
// bypassed.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  applyEvolutionAutonomyBrowser,
  getEvolutionAutonomyStatusBrowser,
  listEvolutionStatesBrowser,
  setEvolutionAutonomyPausedBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionAutonomyApplyResult,
  EvolutionAutonomyStatus,
  EvolutionHarnessState,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";

export interface RslAutonomyCardViewProps {
  status: EvolutionAutonomyStatus | null;
  candidates: EvolutionHarnessState[];
  error: string | null;
  busy: boolean;
  applyingId: string | null;
  refusedStateIds: string[];
  lastResult: EvolutionAutonomyApplyResult | null;
  onRefresh: () => void;
  onToggleKill: () => void;
  onApply: (stateId: string) => void;
  className?: string;
}

function utilityLabel(value: number | null): string {
  return value == null ? "UNMEASURED" : value.toFixed(3);
}

export function RslAutonomyCardView({
  status,
  candidates,
  error,
  busy,
  applyingId,
  refusedStateIds,
  lastResult,
  onRefresh,
  onToggleKill,
  onApply,
  className,
}: RslAutonomyCardViewProps) {
  const t = useT();
  const paused = Boolean(status?.killSwitch.paused);
  const budgetLeft = status
    ? status.activationsToday < status.autoMaxPerDay
    : false;
  const canAttempt = Boolean(status?.autoEligible && !paused && budgetLeft);

  return (
    <section
      className={cn("glass-card-subtle p-3", className)}
      data-testid="rsl-autonomy-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h5 className="text-xs font-semibold text-foreground">
            {t("evolution.autonomy.title")}
          </h5>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {t("evolution.autonomy.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
        >
          {t("evolution.autonomy.refresh")}
        </button>
      </div>

      {error && (
        <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
          {t("evolution.autonomy.error")}: {error}
        </p>
      )}
      {!status && !error && (
        <p className="mt-2 text-[10px] text-muted-foreground">
          {t("evolution.autonomy.loading")}
        </p>
      )}

      {status && (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted-foreground">
            <span
              className={status.autoEligible ? "text-emerald-300" : "text-amber-300"}
            >
              {t("evolution.autonomy.level", { level: status.level })}
            </span>
            <span>{t("evolution.autonomy.risk", { risk: status.riskCeiling })}</span>
            <span>
              {t("evolution.autonomy.budget", {
                used: status.activationsToday,
                max: status.autoMaxPerDay,
              })}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px]">
            <span className={paused ? "text-rose-300" : "text-emerald-300"}>
              {paused
                ? t("evolution.autonomy.paused")
                : t("evolution.autonomy.active")}
            </span>
            <button
              type="button"
              onClick={onToggleKill}
              disabled={busy}
              className={cn(
                "rounded-lg border px-2 py-0.5 text-[10px] transition disabled:opacity-50",
                paused
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15"
                  : "border-rose-400/30 bg-rose-400/10 text-rose-300 hover:bg-rose-400/15",
              )}
            >
              {paused
                ? t("evolution.autonomy.resume")
                : t("evolution.autonomy.pause")}
            </button>
          </div>

          {!canAttempt && (
            <p className="mt-1 text-[9px] text-muted-foreground">
              {t("evolution.autonomy.notEligible")}
            </p>
          )}

          <div className="mt-2 border-t border-border/40 pt-2">
            <p className="text-[10px] font-medium text-muted-foreground">
              {t("evolution.autonomy.candidates")}
            </p>
            {candidates.length === 0 ? (
              <p className="mt-1 text-[10px] text-muted-foreground">
                {t("evolution.autonomy.none")}
              </p>
            ) : (
              candidates.slice(0, 6).map((state) => {
                const refused = refusedStateIds.includes(state.id);
                return (
                  <div
                    key={state.id}
                    className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-border/30 px-2 py-1.5 text-[10px]"
                  >
                    <span className="min-w-0 truncate text-muted-foreground">
                      {state.scope} · {state.id} ·{" "}
                      {t("evolution.autonomy.utility", {
                        value: utilityLabel(state.utility),
                      })}
                    </span>
                    <button
                      type="button"
                      onClick={() => onApply(state.id)}
                      disabled={!canAttempt || busy || applyingId === state.id || refused}
                      className="shrink-0 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-300 transition hover:bg-emerald-400/15 disabled:opacity-40"
                    >
                      {applyingId === state.id
                        ? t("evolution.autonomy.applying")
                        : t("evolution.autonomy.apply")}
                    </button>
                  </div>
                );
              })
            )}
          </div>

          {lastResult && (
            <div className="mt-2 text-[10px]">
              {lastResult.applied ? (
                <p className="text-emerald-300">
                  {t("evolution.autonomy.applied", {
                    id: lastResult.stateId ?? "state",
                  })}
                </p>
              ) : (
                <p className="text-rose-300">
                  {t("evolution.autonomy.refused", {
                    reasons: (lastResult.decision?.reasons ?? [
                      lastResult.reason ?? "refused",
                    ]).join(", "),
                  })}
                </p>
              )}
              {lastResult.decision && (
                <p className="mt-0.5 text-[9px] text-muted-foreground">
                  {t("evolution.autonomy.riskClass", {
                    risk: lastResult.decision.riskClass,
                  })}
                  {" · "}
                  {t("evolution.autonomy.budget", {
                    used: lastResult.decision.activationsToday,
                    max: lastResult.decision.autoMaxPerDay,
                  })}
                </p>
              )}
            </div>
          )}

          <p className="mt-2 text-[9px] text-muted-foreground">
            {t("evolution.autonomy.policyNote")}
          </p>
        </>
      )}
    </section>
  );
}

export function RslAutonomyCard({ className }: { className?: string }) {
  const [status, setStatus] = useState<EvolutionAutonomyStatus | null>(null);
  const [states, setStates] = useState<EvolutionHarnessState[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [refused, setRefused] = useState<string[]>([]);
  const [lastResult, setLastResult] = useState<EvolutionAutonomyApplyResult | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [nextStatus, nextStates] = await Promise.all([
        getEvolutionAutonomyStatusBrowser(),
        listEvolutionStatesBrowser({ limit: 50 }),
      ]);
      setStatus(nextStatus);
      setStates(nextStates.states.filter((state) => state.status === "candidate"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "autonomy status failed");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const toggleKill = useCallback(async () => {
    if (!status) return;
    setBusy(true);
    setError(null);
    try {
      await setEvolutionAutonomyPausedBrowser(
        !status.killSwitch.paused,
        status.killSwitch.paused ? "" : "operator pause from the control panel",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "kill switch failed");
    } finally {
      setBusy(false);
    }
  }, [load, status]);

  const apply = useCallback(async (stateId: string) => {
    setApplyingId(stateId);
    setError(null);
    try {
      const result = await applyEvolutionAutonomyBrowser(stateId);
      setLastResult(result);
      if (!result.applied) {
        setRefused((current) => (
          current.includes(stateId) ? current : [...current, stateId]
        ));
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "autonomy apply failed");
    } finally {
      setApplyingId(null);
    }
  }, [load]);

  return (
    <RslAutonomyCardView
      status={status}
      candidates={states}
      error={error}
      busy={busy}
      applyingId={applyingId}
      refusedStateIds={refused}
      lastResult={lastResult}
      onRefresh={() => void load()}
      onToggleKill={() => void toggleKill()}
      onApply={(stateId) => void apply(stateId)}
      className={className}
    />
  );
}
