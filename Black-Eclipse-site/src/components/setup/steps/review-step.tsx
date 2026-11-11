"use client";

import { Check, CheckCircle2, CircleDashed, Loader2, WarningCircle } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CAPABILITY_BY_ID } from "@/lib/setup/capabilities";
import { computeCapabilityStatus } from "@/lib/setup/capability-status";
import { getLLMPreset } from "@/lib/agent/presets";
import type { SetupCapabilityRow, SetupDraft, SetupKeyStatuses, SetupState } from "../types";

export interface CheckItemView {
  id: string;
  label: string;
  status: "ok" | "failed" | "rate-limited" | "unavailable" | "skipped";
  message: string;
}

const STATUS_TONE: Record<string, string> = {
  ready: "text-emerald-300",
  "needs-key": "text-amber-300",
  off: "text-muted-foreground",
  unavailable: "text-rose-300",
};

export function ReviewStep({
  state,
  draft,
  keyStatuses,
  checking,
  checkItems,
  onCheck,
  error,
}: {
  state: SetupState;
  draft: SetupDraft;
  keyStatuses: SetupKeyStatuses;
  checking: boolean;
  checkItems: CheckItemView[] | null;
  onCheck: () => void;
  error: string | null;
}) {
  const keyConfigured = (envVar: string) => Boolean(keyStatuses[envVar]?.configured);
  const rows: SetupCapabilityRow[] = state.capabilities.map((cap) => {
    const def = CAPABILITY_BY_ID[cap.id];
    return {
      ...cap,
      status: def ? computeCapabilityStatus(def, draft.sources, keyConfigured) : cap.status,
    };
  });
  const prices = rows.find((r) => r.id === "prices");

  const aiLabel = (() => {
    if (draft.aiKind === "keep") {
      return state.ai.configured ? `${state.ai.provider} · ${state.ai.model}` : "Not configured";
    }
    if (draft.aiKind === "skip") return "Not configured — Chat unavailable";
    if (draft.aiKind === "local") {
      const p = getLLMPreset(draft.aiPreset);
      return `${p?.name ?? "Local"} · ${draft.aiModel || p?.model || "auto"}`;
    }
    if (draft.aiKind === "key") {
      const p = getLLMPreset(draft.aiPreset);
      return `${p?.name ?? draft.aiPreset} · ${draft.aiModel || p?.model || "auto"}`;
    }
    return `Custom · ${draft.aiModel || "model"}`;
  })();

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]">
        <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-white/[0.03] px-4 py-3">
          <span className="text-[12.5px] font-semibold text-foreground">Chat</span>
          <span
            className={cn(
              "text-[12px]",
              state.ai.configured || draft.aiKind !== "skip"
                ? "text-foreground"
                : "text-amber-300",
            )}
          >
            {aiLabel}
          </span>
        </div>
        {rows.map((cap) => (
          <div
            key={cap.id}
            className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-2.5 last:border-0"
          >
            <span className="text-[12.5px] font-medium text-foreground">{cap.label}</span>
            <span className={cn("text-[12px]", STATUS_TONE[cap.status])}>
              {cap.status === "ready"
                ? "Ready"
                : cap.status === "needs-key"
                  ? "Needs a key"
                  : cap.status === "off"
                    ? "Off"
                    : "Unavailable"}
            </span>
          </div>
        ))}
      </div>

      {prices?.status !== "ready" && (
        <p className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.05] p-3 text-[11.5px] leading-relaxed text-amber-200/90">
          <WarningCircle size={14} className="mt-0.5 shrink-0" />
          <span>
            Live prices are off. Charts and quote pages will show UNAVAILABLE until you connect a
            licensed provider or explicitly enable a community source.
          </span>
        </p>
      )}
      {!state.ai.configured && draft.aiKind === "skip" && (
        <p className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11.5px] leading-relaxed text-muted-foreground">
          <WarningCircle size={14} className="mt-0.5 shrink-0" />
          <span>
            Chat will open with a &quot;model not configured&quot; banner. You can connect one in
            Settings.
          </span>
        </p>
      )}

      <div className="space-y-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="cursor-pointer rounded-lg text-[12px]"
            disabled={checking}
            onClick={onCheck}
          >
            {checking ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
            Run a quick check
          </Button>
          <span className="text-[11px] text-muted-foreground">
            Makes real, bounded requests. Never reports a key as working just because it exists.
          </span>
        </div>

        {checkItems && (
          <div className="space-y-1.5 rounded-xl border border-white/10 bg-white/[0.02] p-3">
            {checkItems.map((item) => (
              <div key={item.id} className="flex items-start gap-2 text-[11.5px]">
                {item.status === "ok" ? (
                  <Check size={12} className="mt-0.5 shrink-0 text-emerald-400" />
                ) : item.status === "skipped" ? (
                  <CircleDashed size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
                ) : (
                  <WarningCircle size={12} className="mt-0.5 shrink-0 text-rose-300" />
                )}
                <span className="min-w-0">
                  <span className="font-semibold text-foreground">{item.label}: </span>
                  <span className="text-muted-foreground">{item.message}</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && (
        <p className="rounded-xl border border-rose-500/25 bg-rose-500/[0.05] p-3 text-[12px] text-rose-200">
          {error}
        </p>
      )}
    </div>
  );
}
