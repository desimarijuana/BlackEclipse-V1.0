"use client";

import { useState } from "react";
import { Check } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { getLLMPreset } from "@/lib/agent/presets";
import { ProviderConnect, type ProviderConnectResult } from "@/components/providers/provider-connect";
import type { SetupDraft, SetupState } from "../types";

/**
 * Onboarding › AI & Chat.
 *
 * One job: get a working model with as few decisions as possible. The shared
 * `ProviderConnect` panel handles paste-detection, the real test and model
 * discovery, and persists the connection atomically. Choosing "Set up later"
 * keeps chat unavailable (honestly) without blocking the rest of setup.
 */
export function AiStep({
  state,
  draft,
  setDraft,
}: {
  state: SetupState;
  draft: SetupDraft;
  setDraft: (patch: Partial<SetupDraft>) => void;
}) {
  const [changing, setChanging] = useState(false);
  // A connection made in this wizard is persisted immediately, so `aiModel` is
  // the freshest proof it worked — the setup snapshot only refreshes on reload.
  const connected =
    !changing && draft.aiKind === "keep" && (state.ai.configured || Boolean(draft.aiModel));

  const onConnected = (result: ProviderConnectResult) => {
    // The connect call already persisted the provider, key, base URL and model,
    // so the wizard must NOT re-apply it at Finish (that was another source of
    // drift). `keep` means "leave the saved configuration alone".
    setDraft({
      aiKind: "keep",
      aiPreset: result.providerId,
      aiBaseUrl: result.baseUrl,
      aiModel: result.model,
      aiApiKey: "",
    });
    setChanging(false);
  };

  return (
    <div className="space-y-5">
      {connected && (
        <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-3.5">
          <Check size={14} className="text-emerald-400" />
          <span className="text-[12.5px] font-semibold text-foreground">Already configured</span>
          <span className="text-[11.5px] text-muted-foreground">
            {getLLMPreset(draft.aiPreset)?.name ?? state.ai.provider} ·{" "}
            {draft.aiModel || state.ai.model}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="ml-auto cursor-pointer rounded-lg text-[11.5px]"
            onClick={() => {
              setDraft({ aiKind: "keep" });
              setChanging(true);
            }}
          >
            Change
          </Button>
        </div>
      )}

      {!connected && (
        <>
          <ProviderConnect allowSkip onConnected={onConnected} onSkip={() => setDraft({ aiKind: "skip" })} />
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            You can connect or change the model later in Settings → AI. Skipping only turns chat
            off; every other part of Eclipse keeps working.
          </p>
        </>
      )}

      {draft.aiKind === "skip" && !connected && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3">
          <p className="text-[11.5px] leading-relaxed text-amber-200/90">
            Chat will be unavailable until you connect a model. You can do that any time in
            Settings → AI.
          </p>
        </div>
      )}
    </div>
  );
}
