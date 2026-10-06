"use client";

// ── useChatModel — the composer's model/provider choice ─────────────────────
// A real, working model selector for the chat composer. It lists the models the
// operator can actually use (across providers), and selecting one PERSISTS it to
// the server settings vault — the single source of truth the runtime reads — so
// the very next message uses it. A picked model is also sent per-turn as an
// override (belt-and-suspenders). It NEVER fabricates a model list: options come
// from the server route (real env/vault availability + the runtime catalog), the
// active model is always present, and a free-text entry types any id.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  /** The subset the provider is known to actually serve (may be empty). */
  served?: string[];
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
  /** Provider id whose Manage-models dialog is open (null = closed). */
  manageProvider: string | null;
  /** Open the Manage-models dialog for a provider (defaults to the active one). */
  openManageModels: (providerId?: string) => void;
  closeManageModels: () => void;
  /** The provider the Manage dialog should curate (resolved). */
  manageTarget: ChatModelProvider | null;
  /** Discover the given provider (or the active one) into its model list. */
  discoverProvider: (providerId?: string) => Promise<boolean>;
}

interface Choice {
  provider: string;
  model: string;
}

/**
 * The model to adopt so a default actually works.
 *
 * A keyless local provider (Ollama, LM Studio) declares PLACEHOLDER model ids
 * (`llama3.1`, `local-model`) that the installed server may not serve at all.
 * The static catalog cannot know what is installed, so the shipped default can
 * be a model that does not exist — every run then fails with a raw provider 404
 * ("model 'llama3.1' not found"). Once we know the models the provider ACTUALLY
 * serves, this returns the first one to use as the default.
 *
 * Returns `null` when no change is needed: nothing is served (we cannot know
 * better), or the current model is already served — a user's explicit choice is
 * never overridden.
 */
export function pickServableModel(served: string[], current: string): string | null {
  const available = served.filter((m) => typeof m === "string" && m.length > 0);
  if (available.length === 0) return null;
  if (current && available.includes(current)) return null;
  return available[0];
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

  // ── Default-model reconciliation ─────────────────────────────────────────
  // A keyless local provider's declared default can be a placeholder the server
  // does not serve (Ollama's `llama3.1` on a box that only has cloud models),
  // which makes every Ask AI / Analyze run fail with a raw 404. Once we know
  // what the provider ACTUALLY serves, adopt a served model as the default —
  // visibly (the composer selector updates) and persisted to the vault, so the
  // next run works. A user's explicit choice is NEVER overridden, and nothing is
  // invented when the provider serves nothing we can see.
  const reconciledRef = useRef(false);
  useEffect(() => {
    if (loading || reconciledRef.current) return;
    if (choice) return; // an explicit user pick stands
    const pid = savedProvider;
    if (!pid || pid === "auto" || pid === "mock") return;
    const provider = providers.find((p) => p.id === pid);
    // Only a keyless local server whose installed set we can actually probe.
    if (!provider || !provider.keyless || !provider.available) return;
    reconciledRef.current = true;

    void (async () => {
      let served = provider.served ?? [];
      if (served.length === 0 && provider.dynamicDiscovery) {
        // No known served set yet — probe the live server so the default is
        // grounded in what is installed rather than left to 404.
        try {
          const res = await discoverRuntimeModels(pid, {
            baseUrl: provider.baseUrl,
            model: savedModel,
          });
          if (res.ok) {
            served = res.served;
            setProviders((prev) => prev.map((p) => (p.id === pid ? { ...p, served } : p)));
          }
        } catch {
          // A failed probe leaves the current default untouched — never a guess.
        }
      }
      const next = pickServableModel(served, savedModel);
      if (next) {
        void persist(pid, next, provider.baseUrl).catch(() => undefined);
      }
    })();
  }, [loading, choice, savedProvider, savedModel, providers, persist]);

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

  // Manage-models state: which provider's model list is open for curation.
  const [manageProvider, setManageProvider] = useState<string | null>(null);

  const openManageModels = useCallback(
    (providerId?: string) => {
      // Resolve the provider to curate. An explicit id (the per-provider Manage
      // button) always wins. With none, prefer the active provider — but fall
      // back to the first usable provider so the menu item works even when the
      // saved provider is `auto`/`mock` (which has no registry entry and used to
      // resolve to `undefined`, silently rendering no dialog).
      const fallback =
        activeProvider ??
        providers.find((p) => p.keyless || p.available) ??
        providers[0];
      const pid =
        providerId ??
        (selectedProvider === "auto" || selectedProvider === "mock"
          ? fallback?.id
          : selectedProvider);
      setManageProvider(pid ?? null);
    },
    [selectedProvider, activeProvider, providers],
  );

  // The provider whose models the Manage dialog should curate.
  const manageTarget = useMemo(
    () => providers.find((p) => p.id === manageProvider) ?? null,
    [manageProvider, providers],
  );

  /** Discover the given provider (or the active one) into its model list. */
  const discoverProvider = useCallback(
    async (providerId?: string) => {
      const pid = providerId
        ?? (selectedProvider === "auto" || selectedProvider === "mock" ? activeProvider?.id : selectedProvider);
      if (!pid) return false;
      const p = providers.find((x) => x.id === pid);
      try {
        const res = await discoverRuntimeModels(pid, {
          baseUrl: p?.baseUrl ?? null,
          model: selectedModel,
        });
        if (!res.ok) return false;
        const ids = res.models.map((m) => m.id).filter(Boolean);
        setProviders((prev) =>
          prev.map((x) => (x.id === pid ? { ...x, models: Array.from(new Set([...x.models, ...ids])) } : x)),
        );
        return true;
      } catch {
        return false;
      }
    },
    [selectedProvider, activeProvider, providers, selectedModel],
  );

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
    // Manage-models flow (curate which of a provider's models reach the picker).
    manageProvider,
    openManageModels,
    closeManageModels: () => setManageProvider(null),
    manageTarget,
    discoverProvider,
  };
}
