"use client";

// ── Provider registry ───────────────────────────────────────────────────────
// The single provider surface for a Settings section. One row per provider,
// answering in one place:
//   Provider → Purpose → Features using it → Status → API key → Test
//
// WHY THIS IS THE ONLY LIST: each provider has EXACTLY ONE home section (see
// `lib/providers/directory`), so a given API appears once in Settings. Keys are
// edited inline here instead of in a second "API Keys" list, which is what used
// to make the same providers show up twice in one section.
//
// It is a READ/EDIT view over existing systems, not a new store:
//   - provider list + status   ← GET /api/providers  (catalog, env-aware)
//   - key configured/testable  ← GET/POST/DELETE /api/provider-keys (vault)
//   - configure target         ← catalog `configure` (routes to a real screen)
//
// Honesty: "Connected" requires the catalog to report connected/builtin AND,
// when the provider is key-gated, the vault to report a resolvable key. Test
// runs the real endpoint and reports the real result. The key is NEVER rendered
// back — the field starts empty and shows only a masked hint.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, Check, ExternalLink, Eye, EyeOff, KeyRound, Loader2, Plug, Save, Search, Trash2, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useCommandStore } from "@/lib/search/store";
import {
  providerMeta,
  providerLabel,
  providerHome,
  providerHomeForLabel,
  consumingPage,
  TIER_LABEL,
  INVESTOR_EYE_FEATURES,
  type SettingsHome,
} from "@/lib/providers/directory";
import { useProviderCatalog } from "./provider-list";
import type { CatalogProvider } from "@/lib/connectors/catalog";
import { SOURCE_CATALOG } from "@/lib/investor-eye/source-catalog";

interface KeyStatus {
  envVar: string;
  label: string;
  configured: boolean;
  testable: boolean;
  publicValue: boolean;
  fromEnv: boolean;
  stored: boolean;
  hint?: string;
}

type TestResult = { ok: boolean; message: string; latencyMs?: number };

function useKeyStatuses(): { keys: Record<string, KeyStatus>; reload: () => void } {
  const [map, setMap] = useState<Record<string, KeyStatus>>({});
  const reload = useCallback(() => {
    fetch("/api/provider-keys")
      .then((r) => r.json())
      .then((data: { keys?: KeyStatus[] }) => {
        if (!Array.isArray(data.keys)) return;
        setMap(Object.fromEntries(data.keys.map((k) => [k.envVar, k])));
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    let live = true;
    fetch("/api/provider-keys")
      .then((r) => r.json())
      .then((data: { keys?: KeyStatus[] }) => {
        if (!live || !Array.isArray(data.keys)) return;
        setMap(Object.fromEntries(data.keys.map((k) => [k.envVar, k])));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  return { keys: map, reload };
}

/**
 * Per-home provider health, for the Settings status header and the rail's
 * attention dots. A provider is "available" when it is built-in or its key
 * resolves; "needsKey" when it is key-gated and unresolved.
 */
export interface HomeHealth {
  available: number;
  needsKey: number;
  total: number;
  /** Key-gated providers whose key is missing, by name (for the header). */
  missing: string[];
}

export function useProviderHealth(): { health: Record<SettingsHome, HomeHealth>; loading: boolean } {
  const catalog = useProviderCatalog();
  const { keys } = useKeyStatuses();

  const health = useMemo(() => {
    const empty: HomeHealth = { available: 0, needsKey: 0, total: 0, missing: [] };
    const out = {
      ai: { ...empty, missing: [] as string[] },
      "investor-eye": { ...empty, missing: [] as string[] },
      economics: { ...empty, missing: [] as string[] },
      news: { ...empty, missing: [] as string[] },
      market: { ...empty, missing: [] as string[] },
    } as Record<SettingsHome, HomeHealth>;
    if (!catalog) return out;
    for (const cat of catalog.categories) {
      for (const p of cat.providers) {
        const home = providerHome(p.id, p.envVar, p.category);
        out[home].total++;
        const keyOk = p.envVar ? Boolean(keys[p.envVar]?.configured) : true;
        const up = p.status === "builtin" || p.status === "connected";
        if (up && keyOk) out[home].available++;
        else if (p.envVar) {
          out[home].needsKey++;
          out[home].missing.push(p.name);
        }
      }
    }
    return out;
  }, [catalog, keys]);

  return { health, loading: !catalog };
}

function goConfigure(provider: CatalogProvider, onOpenWizard?: () => void) {
  if (provider.configure.target === "wizard") {
    onOpenWizard?.();
    return;
  }
  if (provider.configure.target === "ai" || provider.configure.target === "investor-eye") {
    useCommandStore.getState().dispatch({
      tab: "settings",
      subroute: `settings.${provider.configure.target}`,
    });
  }
}

function ProviderRegistryRow({
  provider,
  keyStatus,
  onKeyChanged,
  onOpenWizard,
}: {
  provider: CatalogProvider;
  keyStatus?: KeyStatus;
  onKeyChanged: () => void;
  onOpenWizard?: () => void;
}) {
  const meta = providerMeta(provider.id, provider.category);
  const keyGated = Boolean(provider.envVar);
  const connected = keyGated
    ? Boolean(keyStatus?.configured) && provider.status === "connected"
    : provider.status === "builtin" || provider.status === "connected";

  const envOwned = Boolean(keyStatus?.fromEnv);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const saveKey = async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar: provider.envVar, value: draft.trim() }),
      });
      const data = (await res.json()) as { ok?: boolean; error?: string };
      if (!res.ok) {
        setNote(data.error ?? "Failed to save the key");
        return;
      }
      setDraft("");
      setEditing(false);
      setNote(draft.trim() === "" ? "Cleared." : "Saved.");
      onKeyChanged();
    } catch {
      setNote("Failed to save the key");
    } finally {
      setBusy(false);
    }
  };

  const removeKey = async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/provider-keys?envVar=${encodeURIComponent(provider.envVar!)}`, { method: "DELETE" });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        setNote(data.error ?? "Failed to remove the key");
        return;
      }
      setNote("Removed.");
      onKeyChanged();
    } catch {
      setNote("Failed to remove the key");
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar: provider.envVar, action: "test" }),
      });
      const data = (await res.json()) as TestResult & { error?: string };
      setResult(data.error ? { ok: false, message: data.error } : { ok: data.ok, message: data.message, latencyMs: data.latencyMs });
    } catch {
      setResult({ ok: false, message: "Test request failed" });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="px-4 py-3 hover:bg-accent/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-foreground flex items-center gap-1.5 flex-wrap">
            {provider.name}
            <span className="text-[8px] font-bold uppercase tracking-wider text-muted-foreground/70">{TIER_LABEL[meta.tier]}</span>
          </p>
          <p className="text-[10px] text-primary/90 mt-0.5">{meta.purpose}</p>
          {meta.usedBy.length > 0 && (
            <p className="text-[9px] text-muted-foreground/80 mt-0.5 flex items-center gap-1 flex-wrap">
              <span>Used by:</span>
              {meta.usedBy.map((label, i) => {
                const dest = consumingPage(label);
                return (
                  <span key={label} className="flex items-center gap-1">
                    {i > 0 && <span className="text-muted-foreground/40">,</span>}
                    {dest ? (
                      <button
                        onClick={() => useCommandStore.getState().dispatch({ tab: dest.tab, ...(dest.params ? { params: dest.params } : {}) })}
                        className="underline decoration-dotted underline-offset-2 hover:text-primary cursor-pointer"
                        title={`Open ${label}`}
                      >
                        {label}
                      </button>
                    ) : (
                      <span>{label}</span>
                    )}
                  </span>
                );
              })}
            </p>
          )}
          {provider.envVar && (
            <p className="text-[9px] font-mono text-muted-foreground/60 mt-0.5">
              {provider.envVar}
              {keyStatus?.hint && <span className="ml-1.5">{keyStatus.hint}</span>}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <span className="flex items-center gap-1.5">
            <span className={cn("w-1.5 h-1.5 rounded-full", connected ? "bg-emerald-400" : "bg-muted-foreground/40")} />
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
              {connected ? (envOwned ? "Env" : keyStatus?.stored ? "Stored" : "Connected") : "Not configured"}
            </span>
          </span>
          <div className="flex items-center gap-1.5">
            {provider.docsUrl && (
              <a
                href={provider.docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 rounded-lg border border-border/30 px-1.5 py-0.5 text-[9px] text-muted-foreground hover:text-foreground"
              >
                Key <ExternalLink size={9} />
              </a>
            )}
            {keyGated && !envOwned && (
              <Button
                variant="outline"
                size="sm"
                className="cursor-pointer rounded-lg text-[9px] h-6 px-2"
                onClick={() => setEditing((v) => !v)}
              >
                <KeyRound className="w-3 h-3 mr-1" /> {keyStatus?.configured ? "Replace" : "Add key"}
              </Button>
            )}
            {keyStatus?.testable && keyStatus.configured && (
              <Button
                variant="outline"
                size="sm"
                className="cursor-pointer rounded-lg text-[9px] h-6 px-2"
                disabled={testing}
                onClick={runTest}
              >
                {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : "Test"}
              </Button>
            )}
            {!connected && provider.configure.target !== "none" && (
              <Button
                variant="outline"
                size="sm"
                className="cursor-pointer rounded-lg text-[9px] h-6 px-2"
                onClick={() => goConfigure(provider, onOpenWizard)}
              >
                <Wrench className="w-3 h-3 mr-1" /> Configure
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Inline key editor — value is never rendered back. */}
      {editing && !envOwned && provider.envVar && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <KeyRound className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              type={reveal || keyStatus?.publicValue ? "text" : "password"}
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void saveKey();
                if (e.key === "Escape") setEditing(false);
              }}
              placeholder={keyStatus?.publicValue ? "http://localhost:11434/v1" : "Paste the key…"}
              className="pl-8 pr-9 font-mono text-xs"
            />
            {!keyStatus?.publicValue && (
              <button
                type="button"
                onClick={() => setReveal((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-muted-foreground hover:text-primary cursor-pointer"
              >
                {reveal ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            )}
          </div>
          <Button size="sm" className="cursor-pointer rounded-xl text-[11px]" disabled={busy} onClick={() => void saveKey()}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Save className="w-3.5 h-3.5 mr-1" />}
            Save
          </Button>
          {keyStatus?.stored && (
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl text-[11px] text-rose-400 hover:text-rose-300"
              disabled={busy}
              onClick={() => void removeKey()}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" /> Remove
            </Button>
          )}
          <span className="text-[10px] text-muted-foreground">Encrypted at rest · never returned</span>
        </div>
      )}

      {envOwned && (
        <p className="mt-2 text-[10px] text-muted-foreground/80 flex items-center gap-1.5">
          <Check size={11} className="text-emerald-400 shrink-0" />
          Set by the {provider.envVar} environment variable — authoritative; the browser cannot change it.
        </p>
      )}

      {(result || note) && (
        <p
          className={cn(
            "mt-2 text-[10px] flex items-center gap-1.5",
            result ? (result.ok ? "text-emerald-400" : "text-rose-400") : "text-muted-foreground"
          )}
        >
          {result ? (result.ok ? <Check size={10} /> : <AlertCircle size={10} />) : <Check size={10} className="text-primary" />}
          {result?.message ?? note}
          {result?.latencyMs !== undefined && <span className="text-muted-foreground/60">· {result.latencyMs} ms</span>}
        </p>
      )}
    </div>
  );
}

/**
 * Provider Registry — shows only the providers whose home is `home`.
 *
 * @param home       The single Settings section this list belongs to.
 * @param title      Heading label.
 * @param onOpenWizard Called when a provider is added via the custom-source wizard.
 */
export function ProviderRegistry({
  home,
  title = "Providers",
  onOpenWizard,
}: {
  home: SettingsHome;
  title?: string;
  onOpenWizard?: () => void;
}) {
  const catalog = useProviderCatalog();
  const { keys, reload } = useKeyStatuses();
  const [filter, setFilter] = useState("");
  const [showAll, setShowAll] = useState(false);

  if (!catalog) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] text-muted-foreground">
        <Loader2 className="w-3 h-3 animate-spin" /> Loading providers…
      </div>
    );
  }

  const all = catalog.categories
    .flatMap((c) => c.providers)
    .filter((p) => providerHome(p.id, p.envVar, p.category) === home);

  if (all.length === 0) return null;

  // Configured/available providers float to the top so the list opens on what
  // is working, not on a wall of "not configured".
  const isUp = (p: CatalogProvider) => p.status === "builtin" || p.status === "connected";
  const needle = filter.trim().toLowerCase();
  const matches = (p: CatalogProvider) => {
    if (!needle) return true;
    const meta = providerMeta(p.id, p.category);
    return [p.name, meta.purpose, p.envVar ?? "", ...meta.usedBy].join(" ").toLowerCase().includes(needle);
  };
  const filtered = all
    .filter(matches)
    .sort((a, b) => Number(isUp(b)) - Number(isUp(a)) || a.name.localeCompare(b.name));

  const available = all.filter(isUp).length;
  const COLLAPSE_AT = 8;
  const collapsible = !needle && filtered.length > COLLAPSE_AT;
  const shown = collapsible && !showAll ? filtered.slice(0, COLLAPSE_AT) : filtered;

  return (
    <div className="rounded-2xl border border-border/20 glass-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border/10 flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary flex items-center gap-1.5">
            <Plug size={11} /> {title}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {available} of {all.length} available · keys encrypted in JDDS, never returned
          </p>
        </div>
        {all.length > COLLAPSE_AT && (
          <div className="relative shrink-0">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter…"
              className="w-36 h-7 rounded-lg border border-border/30 bg-transparent pl-7 pr-2 text-[10px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/40"
            />
          </div>
        )}
      </div>
      <div className="divide-y divide-border/10">
        {shown.map((p) => (
          <ProviderRegistryRow
            key={p.id}
            provider={p}
            keyStatus={p.envVar ? keys[p.envVar] : undefined}
            onKeyChanged={reload}
            onOpenWizard={onOpenWizard}
          />
        ))}
        {filtered.length === 0 && (
          <p className="px-4 py-4 text-[10px] text-muted-foreground">No providers match “{filter}”.</p>
        )}
      </div>
      {collapsible && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="w-full px-4 py-2.5 border-t border-border/10 text-[10px] font-semibold text-primary hover:bg-accent/20 transition-colors cursor-pointer"
        >
          {showAll ? "Show fewer" : `Show all ${filtered.length} providers`}
        </button>
      )}
    </div>
  );
}

/**
 * Compact vault-backed key editor for one env var. Used by the AI section so
 * the selected provider's key lives in the provider-key vault (a single source
 * of truth) rather than a second `llm.apiKey` field. The value is never
 * returned; the field starts empty and only a masked hint is shown.
 */
export function ProviderKeyEditor({ envVar, label }: { envVar: string; label?: string }) {
  const { keys, reload } = useKeyStatuses();
  const status = keys[envVar];
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar, value: draft.trim() }),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) {
        setNote(data.error ?? "Failed to save the key");
        return;
      }
      setDraft("");
      setEditing(false);
      setNote(draft.trim() === "" ? "Cleared." : "Saved.");
      reload();
    } catch {
      setNote("Failed to save the key");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar, action: "test" }),
      });
      const data = (await res.json()) as TestResult & { error?: string };
      setResult(data.error ? { ok: false, message: data.error } : { ok: data.ok, message: data.message, latencyMs: data.latencyMs });
    } catch {
      setResult({ ok: false, message: "Test request failed" });
    } finally {
      setTesting(false);
    }
  };

  const envOwned = Boolean(status?.fromEnv);
  const configured = Boolean(status?.configured);

  return (
    <div className="rounded-xl border border-border/25 glass-card-subtle px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-foreground flex items-center gap-1.5 flex-wrap">
            {label ?? envVar} key
            <span className="text-[9px] font-mono text-muted-foreground/60">{envVar}</span>
            <span
              className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] font-bold border",
                configured
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-border/40 text-muted-foreground"
              )}
            >
              {configured ? (envOwned ? "ENV" : "STORED") : "NOT SET"}
            </span>
          </p>
          {status?.hint && <p className="text-[9px] font-mono text-muted-foreground/60 mt-0.5">{status.hint}</p>}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!envOwned && (
            <Button variant="outline" size="sm" className="cursor-pointer rounded-lg text-[9px] h-6 px-2" onClick={() => setEditing((v) => !v)}>
              <KeyRound className="w-3 h-3 mr-1" /> {configured ? "Replace" : "Add key"}
            </Button>
          )}
          {status?.testable && configured && (
            <Button variant="outline" size="sm" className="cursor-pointer rounded-lg text-[9px] h-6 px-2" disabled={testing} onClick={test}>
              {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : "Test"}
            </Button>
          )}
        </div>
      </div>

      {editing && !envOwned && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Input
              type={reveal || status?.publicValue ? "text" : "password"}
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void save();
                if (e.key === "Escape") setEditing(false);
              }}
              placeholder={status?.publicValue ? "http://localhost:11434/v1" : "Paste the key…"}
              className="h-8 text-xs font-mono pr-9"
            />
            {!status?.publicValue && (
              <button
                type="button"
                onClick={() => setReveal((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-muted-foreground hover:text-primary cursor-pointer"
              >
                {reveal ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            )}
          </div>
          <Button size="sm" className="cursor-pointer rounded-xl text-[11px]" disabled={busy} onClick={() => void save()}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Save className="w-3.5 h-3.5 mr-1" />}
            Save
          </Button>
          <span className="text-[9px] text-muted-foreground">Encrypted at rest · never returned</span>
        </div>
      )}

      {envOwned && (
        <p className="mt-2 text-[10px] text-muted-foreground/80 flex items-center gap-1.5">
          <Check size={11} className="text-emerald-400 shrink-0" />
          Set by the {envVar} environment variable — authoritative; the browser cannot change it.
        </p>
      )}

      {(result || note) && (
        <p className={cn("mt-2 text-[10px] flex items-center gap-1.5", (result ?? note === "Saved.") ? (result?.ok ? "text-emerald-400" : result ? "text-rose-400" : "text-muted-foreground") : "text-muted-foreground")}>
          {result ? (result.ok ? <Check size={10} /> : <AlertCircle size={10} />) : <Check size={10} className="text-primary" />}
          {result?.message ?? note}
          {result?.latencyMs !== undefined && <span className="text-muted-foreground/60">· {result.latencyMs} ms</span>}
        </p>
      )}
    </div>
  );
}

/**
 * Settings status header — a one-line control-center summary so the user can
 * tell at a glance whether the app is wired up, without opening every section.
 */
export function SettingsStatusHeader() {
  const { health, loading } = useProviderHealth();
  const homes: SettingsHome[] = ["ai", "investor-eye", "economics", "news", "market"];
  const total = homes.reduce((n, h) => n + health[h].total, 0);
  const available = homes.reduce((n, h) => n + health[h].available, 0);
  const needsKey = homes.reduce((n, h) => n + health[h].needsKey, 0);

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2 rounded-2xl border border-border/20 glass-card px-4 py-3">
      <span className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary flex items-center gap-1.5">
        <Activity size={11} /> Status
      </span>
      {loading ? (
        <span className="text-[11px] text-muted-foreground flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" /> Checking providers…
        </span>
      ) : (
        <>
          <span className="text-[11px] text-foreground/80">
            <span className="font-semibold text-emerald-400">{available}</span> provider{available === 1 ? "" : "s"} ready
          </span>
          <span className="text-muted-foreground/40">·</span>
          <span className="text-[11px] text-foreground/80">
            <span className={cn("font-semibold", needsKey > 0 ? "text-amber-400" : "text-muted-foreground")}>{needsKey}</span> need a key
          </span>
          <span className="text-muted-foreground/40">·</span>
          <span className="text-[11px] text-foreground/80">{total} total</span>
        </>
      )}
    </div>
  );
}

/**
 * Investor Eye's own event sources (GDELT, USGS, NASA FIRMS). These power the
 * world-state map specifically and are keyless. Macro, market and news
 * providers are configured in their own sections and are NOT listed here.
 */
export function InvestorEyeSources() {
  const external = SOURCE_CATALOG.filter((s) => !s.local);
  if (external.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border/20 glass-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border/10">
        <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary flex items-center gap-1.5">
          <Plug size={11} /> Investor Eye event sources
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          {external.length} source{external.length === 1 ? "" : "s"} · all keyless
        </p>
      </div>
      <div className="divide-y divide-border/10">
        {external.map((source) => (
          <div key={source.id} className="px-4 py-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-foreground">{source.name}</p>
              <p className="text-[10px] text-primary/90 mt-0.5">{source.provider}</p>
              <p className="text-[10px] text-muted-foreground">{source.note}</p>
              <p className="text-[9px] text-muted-foreground/70 mt-0.5 font-mono">
                {source.license} · {source.dataFreshness}
              </p>
            </div>
            <span className="flex items-center gap-1.5 shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground">Built-in</span>
            </span>
          </div>
        ))}
      </div>
      <p className="px-4 py-2.5 border-t border-border/10 text-[9px] text-muted-foreground">
        Keyless public sources — no configuration required. Attribution is shown on the map.
      </p>
    </div>
  );
}

/**
 * Investor Eye feature → provider map ("which provider powers each feature").
 * Informational only — clicking a chip jumps to that provider's home section,
 * which is where it is configured.
 */
export function InvestorEyeFeatureMap() {
  const catalog = useProviderCatalog();
  const { keys } = useKeyStatuses();

  const providerConnected = (id: string): boolean | undefined => {
    const keyStatus = keys[id];
    if (keyStatus) return keyStatus.configured;
    const found = catalog?.categories.flatMap((c) => c.providers).find((p) => p.id === id);
    if (!found) return undefined;
    return found.status === "builtin" || found.status === "connected";
  };

  return (
    <div className="rounded-2xl border border-border/20 glass-card overflow-hidden divide-y divide-border/10">
      {INVESTOR_EYE_FEATURES.map((feature) => (
        <div key={feature.id} className="px-4 py-3">
          <p className="text-[11px] font-semibold text-foreground">{feature.label}</p>
          <p className="text-[10px] text-muted-foreground">{feature.description}</p>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {feature.providers.map((pid) => {
              const ok = providerConnected(pid);
              const home = providerHomeForLabel(pid);
              return (
                <button
                  key={pid}
                  onClick={() =>
                    useCommandStore.getState().dispatch({ tab: "settings", subroute: `settings.${home}` })
                  }
                  title={`Configure in ${home}`}
                  className={cn(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] border cursor-pointer transition-colors hover:border-primary/50",
                    ok === false
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                      : "border-primary/25 bg-primary/10 text-primary/90"
                  )}
                >
                  <span className={cn("w-1 h-1 rounded-full", ok === false ? "bg-amber-400" : "bg-emerald-400")} />
                  {providerLabel(pid)}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <p className="px-4 py-2.5 text-[9px] text-muted-foreground">
        Providers are configured in their own section — tap a chip to jump there.
      </p>
    </div>
  );
}
