"use client";

// ── AI provider settings — a single, well-ordered surface ───────────────────
// Replaces the old side-by-side preset grid + duplicated form. The layout is
// grouped so the operator always knows what they are looking at:
//
//   1. Active setup    — the current provider + model, with the real config
//                         (model, base URL, context window, key, test).
//   2. Connected       — providers that already work (a key is set, or a
//                         keyless local server), each disconnectable.
//   3. Popular         — the common providers, one click to connect.
//   4. Show more       — the rest of the catalog, collapsed by default.
//
// "Connect" reveals the key field for a key-gated provider (env var → vault) or
// selects a keyless local server. "Disconnect" removes the stored key / stops
// using the provider — never a fake state. The model picker reads the runtime
// catalog (declared + discovered) so it reads WHICH model is active.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Check,
  ChevronDown,
  CircleDashed,
  Cpu,
  ExternalLink,
  KeyRound,
  Loader2,
  Plug,
  Server,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { LLM_PRESETS, presetForBaseUrl, isLocalBaseUrl, type LLMPreset } from "@/lib/agent/presets";
import { loadModelCatalog, type ModelCatalog } from "@/lib/agent/model-catalog";
import { ProviderKeyEditor } from "./provider-registry-panel";
import { ModelPicker } from "./model-picker";
import type { LLMConfig } from "./settings";

interface KeyStatus {
  envVar: string;
  configured: boolean;
  publicValue: boolean;
  fromEnv: boolean;
  stored: boolean;
  testable: boolean;
  hint?: string;
}

/** Providers shown in the "Popular" group, in this order. */
const POPULAR_IDS = ["openai", "anthropic", "ollama", "deepseek", "groq", "google", "openrouter", "mistral"];

function useKeyStatuses() {
  const [map, setMap] = useState<Record<string, KeyStatus>>({});
  const reload = useCallback(() => {
    fetch("/api/provider-keys")
      .then((r) => r.json())
      .then((data: { keys?: KeyStatus[] }) => {
        if (Array.isArray(data.keys)) setMap(Object.fromEntries(data.keys.map((k) => [k.envVar, k])));
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);
  return { keys: map, reload };
}

type ProviderState = "active" | "connected" | "needs-key" | "available";

function providerState(
  preset: LLMPreset,
  keys: Record<string, KeyStatus>,
  activeId: string | undefined,
): ProviderState {
  if (preset.id === activeId) return "active";
  if (preset.keyless) return "available";
  if (preset.envVar && keys[preset.envVar]?.configured) return "connected";
  return "needs-key";
}

function StatusChip({ state }: { state: ProviderState }) {
  const map: Record<ProviderState, string> = {
    active: "border-white/15 bg-white/[0.06] text-foreground",
    connected: "border-white/12 bg-white/[0.04] text-emerald-300/90",
    available: "border-white/12 bg-white/[0.04] text-emerald-300/80",
    "needs-key": "border-white/10 text-muted-foreground",
  };
  const label: Record<ProviderState, string> = {
    active: "Active",
    connected: "Connected",
    available: "Ready",
    "needs-key": "Not connected",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold shrink-0", map[state])}>
      {state === "active" || state === "connected" || state === "available" ? <Check size={9} /> : <CircleDashed size={9} />}
      {label[state]}
    </span>
  );
}

/**
 * The active provider's full configuration block, kept separate from the
 * catalog grid so the current model is unmistakably readable.
 */
function ActiveSetup({
  llm,
  updateLlm,
  modelCatalog,
}: {
  llm: LLMConfig;
  updateLlm: (patch: Partial<LLMConfig>, debounce?: number) => void;
  modelCatalog: ModelCatalog;
}) {
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; message: string; latencyMs?: number } | null>(null);

  const activePreset = presetForBaseUrl(llm.baseUrl);
  const activeKeyEnvVar = activePreset?.envVar;
  const catalogProvider =
    (llm.provider !== "auto" && llm.provider !== "mock" ? modelCatalog[llm.provider] : undefined) ??
    modelCatalog[activePreset?.id ?? ""];
  const modelOptions = catalogProvider?.models ?? [];
  const window_ =
    catalogProvider?.modelWindows?.[llm.model] ?? catalogProvider?.contextWindow ?? null;
  const windowKnown = window_ != null;

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const res = await fetch("/api/agent/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ baseUrl: llm.baseUrl, model: llm.model }),
      });
      const data = (await res.json()) as { ok: boolean; message: string; latencyMs?: number; error?: string };
      setTest(data.error ? { ok: false, message: data.error } : { ok: data.ok, message: data.message, latencyMs: data.latencyMs });
    } catch {
      setTest({ ok: false, message: "Test request failed" });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06]">
            <Cpu className="text-primary" size={18} />
          </span>
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary">Active setup</p>
            <p className="text-sm font-semibold text-foreground truncate">
              {activePreset?.name ?? "Custom endpoint"}
            </p>
          </div>
        </div>
        <div className="text-right min-w-0">
          <p className="text-[10px] text-muted-foreground">Model</p>
          <p className="text-sm font-mono font-semibold text-primary truncate max-w-[16rem]" title={llm.model}>
            {llm.model || "—"}
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Model</Label>
          <ModelPicker
            value={llm.model}
            options={modelOptions}
            windowKnown={windowKnown}
            windowLabel={window_ ? `${window_.toLocaleString()}-token context window` : null}
            onChange={(m) => updateLlm({ model: m }, 0)}
            providerId={activePreset?.id ?? (llm.provider !== "auto" && llm.provider !== "mock" ? llm.provider : undefined)}
            baseUrl={llm.baseUrl}
            apiKey={llm.apiKey}
            canDiscover={Boolean(catalogProvider?.dynamicDiscovery)}
            onDiscovered={() => void loadModelCatalog(true)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Base URL</Label>
          <div className="relative">
            <Server className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5" />
            <Input
              value={llm.baseUrl}
              onChange={(e) => updateLlm({ baseUrl: e.target.value })}
              placeholder="https://api.openai.com/v1"
              className="pl-8 font-mono"
            />
          </div>
        </div>
      </div>

      {!windowKnown && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">Context window (optional)</Label>
          <Input
            type="number"
            min={1}
            value={llm.contextWindow ?? ""}
            onChange={(e) => {
              const raw = e.target.value.trim();
              const parsed = raw ? Number(raw) : undefined;
              updateLlm({
                contextWindow: parsed && Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null,
              });
            }}
            placeholder="Leave blank if unknown — the runtime uses a safe bound"
            className="font-mono !border-white/12"
          />
        </div>
      )}

      {isLocalBaseUrl(llm.baseUrl) ? (
        <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
          <Server size={12} className="text-primary shrink-0" />
          No API key needed — local endpoints ignore it.
        </p>
      ) : activeKeyEnvVar ? (
        <ProviderKeyEditor envVar={activeKeyEnvVar} label={activePreset?.name} />
      ) : (
        <p className="text-[10px] text-muted-foreground">
          Custom endpoint — connect a preset above to manage its key in the vault.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button
          variant="outline"
          size="sm"
          className="cursor-pointer rounded-xl"
          disabled={testing}
          onClick={() => void runTest()}
        >
          {testing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Activity className="w-3.5 h-3.5 mr-1" />}
          Test Connection
        </Button>
        {test && (
          <span className={cn("text-[11px] flex items-center gap-1.5", test.ok ? "text-emerald-400" : "text-rose-400")}>
            {test.ok ? <Check size={12} /> : <CircleDashed size={12} />}
            {test.message}
            {test.latencyMs !== undefined && <span className="text-muted-foreground/60">· {test.latencyMs} ms</span>}
          </span>
        )}
      </div>
    </div>
  );
}

function ProviderCard({
  preset,
  state,
  expanded,
  busy,
  onConnect,
  onSelect,
  onDisconnect,
  onCollapse,
  onKeyChanged,
}: {
  preset: LLMPreset;
  state: ProviderState;
  expanded: boolean;
  busy: boolean;
  onConnect: () => void;
  onSelect: () => void;
  onDisconnect: () => void;
  onCollapse: () => void;
  onKeyChanged: () => void;
}) {
  const connectable = state === "needs-key";
  return (
    <div
      className={cn(
        "rounded-xl border px-3.5 py-3 flex flex-col gap-2.5 transition-colors",
        state === "active"
          ? "border-white/15 bg-white/[0.04]"
          : "border-white/10 dark:border-white/5 glass-card-subtle",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] font-semibold text-foreground flex items-center gap-1.5 flex-wrap">
            {preset.name}
            {preset.recommended && (
              <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold border border-white/10 bg-white/[0.06] text-foreground">
                RECOMMENDED
              </span>
            )}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{preset.description}</p>
        </div>
        <StatusChip state={state} />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {connectable ? (
          <Button size="sm" className="cursor-pointer rounded-lg text-[10px] h-7 px-2.5" onClick={onConnect}>
            <Plug className="w-3 h-3 mr-1" /> Connect
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-lg text-[10px] h-7 px-2.5"
            disabled={state === "active"}
            onClick={onSelect}
          >
            {state === "active" ? "In use" : "Use"}
          </Button>
        )}
        {(state === "available" || state === "connected") && !preset.keyless && (
          <Button
            variant="ghost"
            size="sm"
            className="cursor-pointer rounded-lg text-[10px] h-7 px-2 text-muted-foreground hover:text-rose-400"
            disabled={busy}
            onClick={onDisconnect}
          >
            <Trash2 className="w-3 h-3 mr-1" /> Disconnect
          </Button>
        )}
        {state === "active" && isLocalBaseUrl(preset.baseUrl) && (
          <span className="text-[9px] text-emerald-400/80 flex items-center gap-1">
            <Check size={10} /> local server
          </span>
        )}
        {preset.docsUrl && connectable && (
          <a
            href={preset.docsUrl}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-[10px] text-primary/90 hover:text-primary"
          >
            Get key <ExternalLink size={10} />
          </a>
        )}
      </div>

      {expanded && state === "needs-key" && preset.envVar && (
        <div className="space-y-2">
          <ProviderKeyEditor envVar={preset.envVar} label={preset.name} onChanged={() => { onKeyChanged(); onCollapse(); }} />
        </div>
      )}
    </div>
  );
}

export function AIProviderSettings({
  llm,
  updateLlm,
  modelCatalog,
}: {
  llm: LLMConfig;
  updateLlm: (patch: Partial<LLMConfig>, debounce?: number) => void;
  modelCatalog: ModelCatalog;
}) {
  const { keys, reload } = useKeyStatuses();
  const [showAll, setShowAll] = useState(false);
  const [connectId, setConnectId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const activePreset = presetForBaseUrl(llm.baseUrl);
  const activeId = activePreset?.id;

  const states = useMemo(
    () => new Map(LLM_PRESETS.map((p) => [p.id, providerState(p, keys, activeId)])),
    [keys, activeId],
  );

  const connected = useMemo(
    () => LLM_PRESETS.filter((p) => { const s = states.get(p.id); return s === "active" || s === "connected" || s === "available"; }),
    [states],
  );
  const popular = useMemo(
    () => POPULAR_IDS.map((id) => LLM_PRESETS.find((p) => p.id === id)).filter((p): p is LLMPreset => Boolean(p)),
    [],
  );
  const more = useMemo(() => LLM_PRESETS.filter((p) => !POPULAR_IDS.includes(p.id)), []);

  const selectProvider = (preset: LLMPreset) => {
    // Selecting sets provider id + base URL + default model together so the
    // runtime construction and the model picker resolve correctly.
    updateLlm(
      { provider: preset.id as LLMConfig["provider"], baseUrl: preset.baseUrl, model: preset.model, contextWindow: null },
      0,
    );
  };

  const connect = (preset: LLMPreset) => {
    if (preset.keyless) {
      selectProvider(preset);
      return;
    }
    setConnectId((id) => (id === preset.id ? null : preset.id));
  };

  const disconnect = async (preset: LLMPreset) => {
    if (!preset.envVar) return;
    setBusyId(preset.id);
    try {
      await fetch(`/api/provider-keys?envVar=${encodeURIComponent(preset.envVar)}`, { method: "DELETE" });
      reload();
    } finally {
      setBusyId(null);
    }
  };

  const renderCard = (preset: LLMPreset) => {
    const state = states.get(preset.id) ?? "needs-key";
    return (
      <ProviderCard
        key={preset.id}
        preset={preset}
        state={state}
        expanded={connectId === preset.id}
        busy={busyId === preset.id}
        onConnect={() => connect(preset)}
        onSelect={() => selectProvider(preset)}
        onDisconnect={() => void disconnect(preset)}
        onCollapse={() => setConnectId(null)}
        onKeyChanged={reload}
      />
    );
  };

  return (
    <div className="space-y-6">
      <ActiveSetup llm={llm} updateLlm={updateLlm} modelCatalog={modelCatalog} />

      {connected.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-2.5">
            <Plug size={14} className="text-emerald-400" />
            <h3 className="text-xs font-semibold text-foreground">Connected providers</h3>
            <span className="text-[10px] text-muted-foreground">{connected.length}</span>
          </div>
          <div className="grid gap-2.5 grid-cols-1">{connected.map((p) => renderCard(p))}</div>
        </section>
      )}

      <section>
        <div className="flex items-center gap-2 mb-2.5">
          <KeyRound size={14} className="text-primary" />
          <h3 className="text-xs font-semibold text-foreground">Popular providers</h3>
        </div>
        <div className="grid gap-2.5 grid-cols-1">
          {popular.filter((p) => !connected.includes(p)).map((p) => renderCard(p))}
        </div>
      </section>

      <section>
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-primary hover:text-primary/80 cursor-pointer"
        >
          <ChevronDown size={14} className={cn("transition-transform", showAll && "rotate-180")} />
          {showAll ? "Hide additional providers" : `Show more providers (${more.length})`}
        </button>
        {showAll && (
          <div className="grid gap-2.5 grid-cols-1 mt-3">{more.map((p) => renderCard(p))}</div>
        )}
      </section>
    </div>
  );
}
