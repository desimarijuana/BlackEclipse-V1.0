"use client";

import { useT } from "@/lib/i18n/use-t";
import type {
  EvolutionHarnessState,
  EvolutionSurfacePreview,
} from "@/lib/harness/clients/evolution-client";

export function SurfaceActivationCard({
  state,
  preview,
  scope,
  onScopeChange,
  onActivate,
  onClose,
  activating,
}: {
  state: EvolutionHarnessState;
  preview: EvolutionSurfacePreview;
  scope: string;
  onScopeChange: (scope: string) => void;
  onActivate: () => void;
  onClose?: () => void;
  activating: boolean;
}) {
  const t = useT();
  return (
    <div className="rounded-lg border border-sky-400/20 bg-sky-400/5 p-2 text-[10px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-sky-300">{t("evolution.states.previewTitle")}</p>
        <span className={preview.canActivate ? "text-emerald-300" : "text-rose-300"}>
          {preview.canActivate
            ? t("evolution.states.canActivate")
            : t("evolution.states.cannotActivate")}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <label className="text-muted-foreground">{t("evolution.states.scope")}</label>
        <select
          value={scope}
          onChange={(event) => onScopeChange(event.target.value)}
          className="rounded-lg border border-border/50 bg-background/40 px-2 py-1 text-[10px] text-foreground"
        >
          {preview.availableScopes.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <span className={preview.baseDigestMatches ? "text-emerald-300" : "text-rose-300"}>
          {preview.baseDigestMatches
            ? t("evolution.states.baseMatch")
            : t("evolution.states.baseMismatch")}
        </span>
      </div>
      {preview.reasons.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-rose-300">
          {preview.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {preview.diff && (
        <div className="mt-1 space-y-0.5 text-muted-foreground">
          <p>{t("evolution.states.promptChange", {
            before: preview.diff.systemPromptBeforeChars,
            after: preview.diff.systemPromptAfterChars,
          })}</p>
          <p>{t("evolution.states.toolsRemoved", {
            tools: preview.diff.toolsRemoved.join(", ") || "none",
          })}</p>
          <p>{t("evolution.states.toolsAdded", {
            tools: preview.diff.toolsAdded.join(", ") || "none",
          })}</p>
          <p>{t("evolution.states.ceilings", {
            stepsBefore: preview.diff.maxStepsBefore,
            stepsAfter: preview.diff.maxStepsAfter,
            callsBefore: preview.diff.maxToolCallsBefore,
            callsAfter: preview.diff.maxToolCallsAfter,
          })}</p>
        </div>
      )}
      {preview.evidence ? (
        <details className="mt-1.5 text-[9.5px] text-muted-foreground">
          <summary className="cursor-pointer select-none">
            {t("evolution.states.evidence", {
              count: preview.evidence.trials.length,
            })}
          </summary>
          <div className="mt-1 space-y-0.5 font-mono">
            {preview.evidence.criticalDeltas.length > 0 && (
              <div className="rounded border border-rose-400/30 bg-rose-400/5 px-1.5 py-1 text-rose-300">
                <p>{t("evolution.states.criticalRegressions", {
                  count: preview.evidence.criticalDeltas.length,
                })}</p>
                {preview.evidence.criticalDeltas.map((row) => (
                  <p key={`critical:${row.taskId}`}>
                    {t("evolution.states.criticalRegression", {
                      taskId: row.taskId,
                      before: row.before?.toFixed(3) ?? "UNMEASURED",
                      after: row.after?.toFixed(3) ?? "UNMEASURED",
                    })}
                  </p>
                ))}
              </div>
            )}
            {preview.evidence.target && (
              <p className={
                preview.evidence.target.delta == null
                  ? "text-muted-foreground"
                  : preview.evidence.target.delta > 0
                    ? "text-emerald-300"
                    : "text-rose-300"
              }>
                {preview.evidence.target.before == null
                  || preview.evidence.target.after == null
                  ? t("evolution.states.evidenceTargetUnmeasured", {
                    dimension: preview.evidence.target.dimension,
                  })
                  : `${t("evolution.states.evidenceTarget", {
                    dimension: preview.evidence.target.dimension,
                    before: preview.evidence.target.before.toFixed(3),
                    after: preview.evidence.target.after.toFixed(3),
                  })} · ${t("evolution.states.evidenceDelta", {
                    delta: (preview.evidence.target.delta ?? 0).toFixed(3),
                  })}`}
              </p>
            )}
            <p className="flex flex-wrap items-center gap-1">
              {preview.evidence.baseline?.run?.id ? (
                <>
                  <span>{t("evolution.states.evidenceBaselineRun", {
                    id: preview.evidence.baseline.run.id,
                  })}</span>
                  <a
                    className="underline underline-offset-2 hover:text-foreground"
                    href={`/api/evolution/experiments/${encodeURIComponent(preview.evidence.baseline.run.id)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("evolution.states.evidenceOpenBaseline")}
                  </a>
                </>
              ) : (
                <span>{t("evolution.states.evidenceNoBaseline")}</span>
              )}
              <span>·</span>
              <span>{t("evolution.states.evidenceCandidateRun", {
                id: preview.evidence.run.id,
              })}</span>
              <a
                className="underline underline-offset-2 hover:text-foreground"
                href={`/api/evolution/experiments/${encodeURIComponent(preview.evidence.run.id)}`}
                target="_blank"
                rel="noreferrer"
              >
                {t("evolution.states.evidenceOpenRun")}
              </a>
            </p>
            {preview.evidence.metrics.map((metric) => (
              <p key={`${metric.scope ?? "overall"}:${metric.dimension}`}>
                {t("evolution.states.evidenceMetric", {
                  dimension: metric.dimension,
                  value: metric.value == null ? "UNMEASURED" : metric.value.toFixed(3),
                })}
              </p>
            ))}
            {preview.evidence.trials.slice(0, 8).map((trial) => (
              <p key={`${trial.taskId}:${trial.trialIndex ?? 0}`}>
                {t("evolution.states.evidenceTrial", {
                  taskId: trial.taskId,
                  status: trial.status || (trial.passed ? "passed" : "failed"),
                })}
              </p>
            ))}
            <div className="mt-1 border-t border-border/20 pt-1">
              <p className="text-muted-foreground/70">{t("evolution.states.taskDeltas")}</p>
              {preview.evidence.taskDeltas.length === 0 ? (
                <p>{t("evolution.states.taskDeltaNone")}</p>
              ) : (
                preview.evidence.taskDeltas.slice(0, 10).map((row) => (
                  <p
                    key={row.taskId}
                    className={
                      row.delta == null
                        ? "text-muted-foreground"
                        : row.delta > 0
                          ? "text-emerald-300"
                          : row.delta < 0
                            ? "text-rose-300"
                            : "text-muted-foreground"
                    }
                  >
                    {row.delta == null
                      ? t("evolution.states.taskDeltaUnmeasured", { taskId: row.taskId })
                      : t("evolution.states.taskDeltaRow", {
                        taskId: row.taskId,
                        before: row.before?.toFixed(3) ?? "UNMEASURED",
                        after: row.after?.toFixed(3) ?? "UNMEASURED",
                        delta: row.delta.toFixed(3),
                      })}
                  </p>
                ))
              )}
            </div>
            {preview.evidence.baseline?.metrics.map((metric) => (
              <p key={`baseline:${metric.dimension}`} className="text-muted-foreground/70">
                {t("evolution.states.evidenceBaseline", {
                  dimension: metric.dimension,
                  value: metric.value == null ? "UNMEASURED" : metric.value.toFixed(3),
                })}
              </p>
            ))}
          </div>
        </details>
      ) : (
        <p className="mt-1.5 text-[9.5px] text-muted-foreground">
          {t("evolution.states.evidenceNone")}
        </p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={onActivate}
          disabled={!preview.canActivate || activating}
          className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[10px] text-emerald-300 transition hover:bg-emerald-400/15 disabled:opacity-50"
        >
          {activating
            ? t("evolution.states.activating")
            : t("evolution.states.activateScope", { scope })}
        </button>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.states.close")}
          </button>
        )}
        <span className="text-muted-foreground">{state.id}</span>
      </div>
    </div>
  );
}
