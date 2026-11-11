"use client";

import { useState } from "react";
import { Brain, Check, CircleDashed, Cpu, KeyRound, Loader2, Plug, Server } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { LLM_PRESETS, getLLMPreset } from "@/lib/agent/presets";
import type { SetupDraft, SetupState } from "../types";

const POPULAR = ["openai", "anthropic", "google", "deepseek", "groq", "mistral", "openrouter", "xai", "opencode", "together", "perplexity", "fireworks"];

function ChoiceCard({
  active,
  title,
  body,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  title: string;
  body: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex items-start gap-2.5 rounded-xl border p-3.5 text-left transition-colors cursor-pointer",
        active
          ? "border-primary/50 bg-primary/[0.08]"
          : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
          active
            ? "border-primary/40 bg-primary/15 text-primary"
            : "border-white/10 bg-white/[0.04] text-muted-foreground",
        )}
      >
        <Icon size={15} />
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] font-semibold text-foreground">{title}</span>
        <span className="mt-0.5 block text-[11.5px] leading-relaxed text-muted-foreground">
          {body}
        </span>
      </span>
    </button>
  );
}

export function AiStep({
  state,
  draft,
  setDraft,
}: {
  state: SetupState;
  draft: SetupDraft;
  setDraft: (patch: Partial<SetupDraft>) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const current = state.ai;
  const preset = getLLMPreset(draft.aiPreset);

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body = draft.aiKind === "keep"
        ? {}
        : {
            baseUrl: draft.aiBaseUrl || preset?.baseUrl,
            model: draft.aiModel || preset?.model,
            apiKey: draft.aiApiKey || undefined,
          };
      const res = await fetch("/api/agent/test", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as { ok?: boolean; message?: string; error?: string };
      setTestResult({ ok: Boolean(data.ok), message: data.message || data.error || "No response" });
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : "Test failed" });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {current.configured && draft.aiKind === "keep" && (
        <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-3.5">
          <Check size={14} className="text-emerald-400" />
          <span className="text-[12.5px] font-semibold text-foreground">Already configured</span>
          <span className="text-[11.5px] text-muted-foreground">
            {current.provider} · {current.model}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="ml-auto cursor-pointer rounded-lg text-[11.5px]"
            onClick={() => setDraft({ aiKind: "key" })}
          >
            Change
          </Button>
        </div>
      )}

      <div className="grid gap-2.5 sm:grid-cols-2">
        <ChoiceCard
          active={draft.aiKind === "local"}
          title="Local model"
          body="Ollama or LM Studio. No key, no data leaves this machine."
          icon={Server}
          onClick={() => setDraft({ aiKind: "local", aiPreset: "ollama", aiBaseUrl: "", aiModel: "", aiApiKey: "" })}
        />
        <ChoiceCard
          active={draft.aiKind === "key"}
          title="Use my API key"
          body="OpenAI, Anthropic, Google, DeepSeek, Groq, OpenRouter and more."
          icon={KeyRound}
          onClick={() => setDraft({ aiKind: "key", aiPreset: "openai", aiBaseUrl: "", aiModel: "", aiApiKey: "" })}
        />
        <ChoiceCard
          active={draft.aiKind === "custom"}
          title="Custom endpoint"
          body="Any OpenAI-compatible base URL and model."
          icon={Plug}
          onClick={() => setDraft({ aiKind: "custom", aiBaseUrl: "https://api.openai.com/v1", aiModel: "", aiApiKey: "" })}
        />
        <ChoiceCard
          active={draft.aiKind === "skip"}
          title="Set up later"
          body="Chat will be unavailable until a model is configured."
          icon={CircleDashed}
          onClick={() => setDraft({ aiKind: "skip" })}
        />
      </div>

      {draft.aiKind === "local" && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex flex-wrap gap-2">
            {LLM_PRESETS.filter((p) => p.id === "ollama" || p.id === "lmstudio").map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setDraft({ aiPreset: p.id, aiBaseUrl: "", aiModel: "" })}
                className={cn(
                  "rounded-lg border px-2.5 py-1.5 text-[11.5px] cursor-pointer",
                  draft.aiPreset === p.id
                    ? "border-primary/50 bg-primary/10 text-foreground"
                    : "border-white/10 text-muted-foreground hover:border-white/20",
                )}
              >
                {p.name}
              </button>
            ))}
          </div>
          <div className="grid gap-3">
            <div className="space-y-1.5">
              <Label className="text-[11.5px] text-muted-foreground">Base URL</Label>
              <Input value={draft.aiBaseUrl} onChange={(e) => setDraft({ aiBaseUrl: e.target.value })} placeholder={preset?.baseUrl} className="h-9 text-[12.5px]" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11.5px] text-muted-foreground">Model</Label>
              <Input value={draft.aiModel} onChange={(e) => setDraft({ aiModel: e.target.value })} placeholder={preset?.model} className="h-9 text-[12.5px]" />
            </div>
          </div>
        </div>
      )}

      {draft.aiKind === "key" && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {LLM_PRESETS.filter((p) => POPULAR.includes(p.id)).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setDraft({ aiPreset: p.id, aiBaseUrl: "", aiModel: "" })}
                className={cn(
                  "rounded-lg border px-2.5 py-1.5 text-left text-[11.5px] cursor-pointer",
                  draft.aiPreset === p.id
                    ? "border-primary/50 bg-primary/10 text-foreground"
                    : "border-white/10 text-muted-foreground hover:border-white/20",
                )}
              >
                {p.name}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11.5px] text-muted-foreground">API key</Label>
            <Input
              type="password"
              value={draft.aiApiKey}
              onChange={(e) => setDraft({ aiApiKey: e.target.value })}
              placeholder={preset?.envVar ?? "Paste your key"}
              className="h-9 text-[12.5px]"
              autoComplete="off"
            />
            <p className="text-[11px] text-muted-foreground">
              Stored encrypted in JDDS. {preset?.docsUrl && <a className="underline" href={preset.docsUrl} target="_blank" rel="noreferrer">Get a key</a>}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11.5px] text-muted-foreground">Model</Label>
            <Input value={draft.aiModel} onChange={(e) => setDraft({ aiModel: e.target.value })} placeholder={preset?.model} className="h-9 text-[12.5px]" />
          </div>
        </div>
      )}

      {draft.aiKind === "custom" && (
        <div className="grid gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-[11.5px] text-muted-foreground">Base URL</Label>
            <Input value={draft.aiBaseUrl} onChange={(e) => setDraft({ aiBaseUrl: e.target.value })} placeholder="https://api.example.com/v1" className="h-9 text-[12.5px]" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11.5px] text-muted-foreground">Model</Label>
            <Input value={draft.aiModel} onChange={(e) => setDraft({ aiModel: e.target.value })} placeholder="model-id" className="h-9 text-[12.5px]" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11.5px] text-muted-foreground">API key (optional for local)</Label>
            <Input type="password" value={draft.aiApiKey} onChange={(e) => setDraft({ aiApiKey: e.target.value })} className="h-9 text-[12.5px]" autoComplete="off" />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2.5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="cursor-pointer rounded-lg text-[12px]"
          disabled={testing || draft.aiKind === "skip"}
          onClick={() => void test()}
        >
          {testing ? <Loader2 size={13} className="animate-spin" /> : <Brain size={13} />}
          Test connection
        </Button>
        {testResult && (
          <span className={cn("inline-flex items-center gap-1.5 text-[11.5px]", testResult.ok ? "text-emerald-300" : "text-rose-300")}>
            {testResult.ok ? <Check size={12} /> : <Cpu size={12} />} {testResult.message}
          </span>
        )}
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Test makes one real request to the endpoint. A stored key alone is never reported as working.
      </p>
    </div>
  );
}
