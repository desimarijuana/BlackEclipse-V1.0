"use client";

import { useT } from "@/lib/i18n/use-t";
import type {
  EvolutionHarnessState,
  EvolutionSurfacePreview,
} from "@/lib/harness/evolution-client";

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
