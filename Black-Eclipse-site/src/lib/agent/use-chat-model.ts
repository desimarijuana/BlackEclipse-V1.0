"use client";

// ── useChatModel — the composer's model/provider choice ─────────────────────
// A real, working model selector for the chat composer. It lists the models the
// operator can actually use (across providers), and selecting one PERSISTS it to
// the server settings vault — the single source of truth the runtime reads — so
// the very next message uses it. A picked model is also sent per-turn as an
// override (belt-and-suspenders). It NEVER fabricates a model list: options come
// from the server route (real env/vault availability + the runtime catalog), the
// active model is always present, and a free-text entry types any id.

import { useCallback, useEffect, useMemo, useState } from "react";
import { discoverRuntimeModels } from "@/lib/harness/model-runtime-browser";

const STORAGE_KEY = "eclipse.chatModelChoice";

export interface ChatModelProvider {
  id: string;
  label: string;
  baseUrl: string;
  keyless: boolean;
  envVar: string | null;
  dynamicDiscovery: boolean;
  available: boolean;
  models: string[];
}

export interface ChatModelState {
  providers: ChatModelProvider[];
  selectedProvider: string;
  selectedModel: string;
  select: (providerId: string, model: string) => void;
  setModel: (model: string) => void;
  displayModel: string;
  providerLabel: string;
  canDiscover: boolean;
  discover: () => Promise<{ ok: boolean; detail: string | null }>;
  discovering: boolean;
  loading: boolean;
  /** The last persistence failure, shown honestly (never a silent no-op). */
  error: string | null;
}

interface Choice {
  provider: string;
  model: string;
}

function readStored(): Choice | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Choice>;
    if (typeof parsed?.provider === "string" && typeof parsed?.model === "string") {
      return { provider: parsed.provider, model: parsed.model };
    }
  } catch {
    // fall through
  }
  return null;
}

function writeStored(choice: Choice | null): void {
  if (typeof window === "undefined") return;
  try {
    if (choice) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(choice));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable — the pick still applies for this session.
  }
}

export function useChatModel(): ChatModelState {
  const [providers, setProviders] = useState<ChatModelProvider[]>([]);
  const [savedProvider, setSavedProvider] = useState<string>("auto");
  const [savedModel, setSavedModel] = useState<string>("");
  const [choice, setChoice] = useState<Choice | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setChoice(readStored());
    void fetch("/api/harness/chat/models")
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (!live || !body) return;
        if (Array.isArray(body.providers)) setProviders(body.providers as ChatModelProvider[]);
        if (body.active) {
          setSavedProvider(typeof body.active.provider === "string" ? body.active.provider : "auto");
          setSavedModel(typeof body.active.model === "string" ? body.active.model : "");
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  const selectedProvider = choice?.provider ?? savedProvider;
  const selectedModel = choice?.model ?? savedModel;

  const activeProvider = useMemo(
    () => providers.find((p) => p.id === selectedProvider),
    [providers, selectedProvider],
  );

  const displayModel = selectedModel || activeProvider?.models[0] || "";

  // Persist a choice to the settings vault (the runtime's source of truth) so
  // the next run actually uses it. On failure the previous value is restored and
  // the error is surfaced — never a silent no-op.
  const persist = useCallback(
    async (providerId: string, model: string, baseUrl?: string) => {
      const llm: Record<string, unknown> = { provider: providerId, model };
      if (baseUrl) llm.baseUrl = baseUrl;
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ llm }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `Save failed (${res.status})`);
      if (body.llm) {
        setSavedProvider(typeof body.llm.provider === "string" ? body.llm.provider : providerId);
        setSavedModel(typeof body.llm.model === "string" ? body.llm.model : model);
      }
      setError(null);
    },
    [],
  );

  const select = useCallback(
    (providerId: string, model: string) => {
      const p = providers.find((x) => x.id === providerId);
      const next: Choice = { provider: providerId, model };
      const previous = choice;
      setChoice(next);
      writeStored(next);
      void persist(providerId, model, p?.baseUrl || undefined).catch((err) => {
        setChoice(previous);
        writeStored(previous);
        setError(err instanceof Error ? err.message : "Could not switch model");
      });
    },
    [providers, choice, persist],
  );

  const setModel = useCallback(
    (model: string) => {
      const pid = choice?.provider ?? savedProvider;
      const next: Choice = { provider: pid, model };
      const previous = choice;
      setChoice(next);
      writeStored(next);
      void persist(pid, model).catch((err) => {
        setChoice(previous);
        writeStored(previous);
        setError(err instanceof Error ? err.message : "Could not change model");
      });
    },
    [choice, savedProvider, persist],
  );

  const discover = useCallback(async () => {
    const pid =
      selectedProvider === "auto" || selectedProvider === "mock"
        ? activeProvider?.id
        : selectedProvider;
    if (!pid || discovering) return { ok: false, detail: "No provider selected" };
    setDiscovering(true);
    try {
      const res = await discoverRuntimeModels(pid, {
        baseUrl: activeProvider?.baseUrl ?? null,
        model: selectedModel,
      });
      if (res.ok) {
        const ids = res.models.map((m) => m.id).filter(Boolean);
        setProviders((prev) =>
          prev.map((p) =>
            p.id === pid ? { ...p, models: Array.from(new Set([...p.models, ...ids])) } : p,
          ),
        );
        if (!selectedModel && ids.length) select(pid, ids[0]);
      }
      return { ok: res.ok, detail: res.detail };
    } catch (err) {
      return { ok: false, detail: err instanceof Error ? err.message : "Discovery failed" };
    } finally {
      setDiscovering(false);
    }
  }, [selectedProvider, activeProvider, discovering, selectedModel, select]);

  const providerLabel = useMemo(() => {
    if (selectedProvider === "auto") return activeProvider?.label ?? "Auto";
    return activeProvider?.label ?? selectedProvider;
  }, [selectedProvider, activeProvider]);

  return {
    providers,
    selectedProvider,
    selectedModel: displayModel,
    select,
    setModel,
    displayModel,
    providerLabel,
    canDiscover:
      Boolean(activeProvider?.dynamicDiscovery) ||
      (!activeProvider &&
        (selectedProvider === "ollama" ||
          selectedProvider === "lmstudio" ||
          selectedProvider === "custom")),
    discover,
    discovering,
    loading,
    error,
  };
}
