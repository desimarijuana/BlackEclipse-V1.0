"use client";

// Settings cluster: named profiles, memory providers, and policies. Extracted
// from eclipse-memory-screen.tsx so the Control Room shell stays navigable.

import { useCallback, useEffect, useState } from "react";
import { Loader2, Lock, RefreshCcw } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  createProfile, deleteProfile, getPolicies, listProfiles,
  memoryProviderSearch, memoryProviderStatus, memoryProviderTest, updatePolicies,
} from "@/lib/harness/eclipse-memory-browser";
import type { MemoryProfileRecord, MemoryProviderStatus } from "@/lib/harness/eclipse-memory-types";
import { ErrorBox, Header, MEMORY_TYPES, Spinner } from "./memory-ui";

// ── Profiles (named + isolation + inheritance) ──────────────────────────────

export function Profiles({ isOperator }: { isOperator: boolean }) {
  const [profiles, setProfiles] = useState<MemoryProfileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [newId, setNewId] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setProfiles(await listProfiles()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 4000); };

  return (
    <div className="animate-fade-in-up">
      <Header title="Profiles" hint="Named profiles scope memory, sessions, skills and providers. A profile may read an inherited parent READ-ONLY; cross-profile memory never leaks." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      {isOperator && (
        <div className="mb-3 flex gap-2">
          <Input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="new profile id (e.g. research)" className="rounded-xl bg-background/60" />
          <Button size="sm" className="rounded-xl cursor-pointer" onClick={async () => {
            if (!newId.trim()) return;
            try { await createProfile({ id: newId.trim() }); setNewId(""); notify("Profile created"); await load(); }
            catch (err) { notify(err instanceof Error ? err.message : "create failed"); }
          }}>Create</Button>
        </div>
      )}
      {loading ? <Spinner /> : error ? <ErrorBox message={error} /> : (
        <div className="space-y-2">
          {profiles.map((profile) => (
            <div key={profile.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-foreground">{profile.name} <span className="font-mono text-[11px] text-muted-foreground">({profile.id})</span></p>
                  <p className="text-[10px] text-muted-foreground">
                    memory ns {profile.memoryNamespace} · retention {profile.retentionDays}d
                    {profile.inherits ? ` · inherits ${profile.inherits} (read-only)` : ""}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[9px] text-muted-foreground/70">{profile.directory}</p>
                </div>
                {isOperator && profile.id !== "default" && (
                  <Button size="sm" variant="outline" className="shrink-0 rounded-xl cursor-pointer text-rose-300"
                    onClick={async () => {
                      try { await deleteProfile(profile.id); notify("Profile deleted"); await load(); }
                      catch (err) { notify(err instanceof Error ? err.message : "delete failed"); }
                    }}>Delete</Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Providers (memory-provider health + fenced external search) ─────────────

export function Providers() {
  const [status, setStatus] = useState<MemoryProviderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [external, setExternal] = useState(false);
  const [results, setResults] = useState<Array<{ provider: string; content: string; verified: boolean }>>([]);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setStatus(await memoryProviderStatus()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const test = async (name: string) => {
    setTesting(name); setTestResult(null);
    try {
      const r = await memoryProviderTest(name);
      setTestResult(`${name}: ${r.state}${r.latencyMs != null ? ` · ${r.latencyMs}ms` : ""}${r.detail ? ` · ${r.detail}` : ""}${r.searchProbed ? ` · probe returned ${r.probeResultCount}` : ""}`);
    } catch (err) { setTestResult(err instanceof Error ? err.message : "test failed"); }
    finally { setTesting(null); setTimeout(() => setTestResult(null), 8000); }
  };

  const search = async () => {
    if (!query.trim()) return;
    try {
      const body = await memoryProviderSearch({ query, allowExternal: external, limit: 10 });
      const rows = [
        ...body.native.results.map((r) => ({ provider: r.provider, content: r.content, verified: r.verified })),
        ...body.external.flatMap((entry) => entry.response.results.map((r) => ({ provider: r.provider, content: r.content, verified: r.verified }))),
      ];
      setResults(rows);
    } catch (err) { setError(err instanceof Error ? err.message : "search failed"); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div className="animate-fade-in-up">
      <Header title="Memory Providers" hint="Native memory is authoritative. External providers are UNVERIFIED CONTEXT — labelled, fenced, never promoted, and never able to answer a current financial question." />
      <div className="mb-3 flex gap-2">
        <Input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void search(); }}
          placeholder="Search memory providers…" className="rounded-xl bg-background/60" />
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={external} onChange={(e) => setExternal(e.target.checked)} /> external
        </label>
        <Button size="sm" className="rounded-xl cursor-pointer" onClick={search}>Search</Button>
      </div>
      {status && (
        <div className="mb-3 grid gap-2 sm:grid-cols-2">
          {status.providers.map((p) => {
            const caps = p.capabilities;
            const capList = [
              ["search", caps.search], ["write", caps.write], ["delete", caps.delete],
              ["export", caps.export], ["read-only", caps.readOnly],
            ] as Array<[string, boolean]>;
            return (
              <div key={p.name} className="rounded-2xl border border-white/10 glass-card p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className={cn("text-[12px] font-medium", p.health.ok ? "text-emerald-300" : "text-amber-300")}>{p.name}</span>
                  <span className={cn("rounded-full border px-2 py-0.5 text-[9px] uppercase tracking-wide",
                    p.isNative ? "border-primary/40 text-primary" : "border-border/40 text-muted-foreground")}>
                    {p.isNative ? "native" : "external"}
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  {p.health.state}
                  {p.health.latencyMs != null ? ` · ${p.health.latencyMs}ms` : ""}
                  {p.health.version ? ` · v${p.health.version}` : ""}
                </p>
                {p.health.detail && <p className="mt-0.5 text-[10px] text-muted-foreground/80">{p.health.detail}</p>}
                {p.capabilitySummary && <p className="mt-1 text-[10px] text-foreground/80">{p.capabilitySummary}</p>}
                {p.dataLocation && (
                  <p className={cn("mt-1 text-[10px]", p.isNative ? "text-emerald-300/80" : "text-amber-300/90")}>
                    Data: {p.dataLocation}
                  </p>
                )}
                {p.reliability && p.reliability.state !== "closed" && (
                  <p className="mt-1 text-[10px] text-amber-300/90">
                    Reliability: {p.reliability.state}
                    {p.reliability.lastFailureCategory ? ` (${p.reliability.lastFailureCategory})` : ""}
                    {p.reliability.failureRate != null ? ` · failure rate ${(p.reliability.failureRate * 100).toFixed(0)}%` : ""}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {capList.map(([label, on]) => (
                    <span key={label} className={cn("rounded-md border px-1.5 py-0.5 text-[9px]",
                      on ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-border/30 text-muted-foreground/60")}>
                      {label}
                    </span>
                  ))}
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <Button size="sm" variant="outline" className="rounded-lg cursor-pointer text-[10px] h-6 px-2" disabled={testing === p.name}
                    onClick={() => void test(p.name)}>
                    {testing === p.name ? <Loader2 size={10} className="animate-spin" /> : "Test"}
                  </Button>
                  {!p.isNative && <span className="text-[9px] text-muted-foreground">not Eclipse-verified</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {testResult && <p className="mb-3 text-[11px] text-primary">{testResult}</p>}
      {status?.privacyNote && (
        <p className="mb-3 rounded-xl border border-white/10 glass-card-subtle p-2.5 text-[10px] text-muted-foreground">{status.privacyNote}</p>
      )}
      <div className="space-y-2">
        {results.map((r, i) => (
          <div key={`${r.provider}-${i}`} className={cn("rounded-2xl border glass-card p-3", r.verified ? "border-emerald-400/20" : "border-amber-400/20")}>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              {r.provider} · {r.verified ? "verified" : "unverified context"}
            </p>
            <p className="mt-1 text-[11px] text-foreground/90">{r.content}</p>
          </div>
        ))}
      </div>
      {!status?.externalEnabled && (
        <p className="mt-3 text-[10px] text-amber-300/90">
          External search is disabled by policy. Enable it in Policies to search configured MCP memory providers; results stay labelled and are never promoted to native memory.
        </p>
      )}
    </div>
  );
}


// ── Policies ────────────────────────────────────────────────────────────────

const POLICY_LABELS: Record<string, string> = {
  memory_mode: "Automatic memory learning",
  skill_learning_mode: "Automatic skill learning",
  candidate_confidence_threshold: "Candidate confidence threshold",
  context_budget_chars: "Retrieval context budget (chars)",
  retrieval_limit: "Max memories per retrieval",
  max_memories: "Max active memories (0 = unlimited)",
  retention_days: "Retention review window (days, 0 = never)",
  include_proposed_in_retrieval: "Inject proposed memory without review",
  audit_retention_rows: "Audit rows kept (0 = unlimited)",
  auto_promote_low_risk: "Auto-promote low-risk skills (locked off)",
  memory_enabled: "Memory enabled (hard off switch)",
  memory_in_diagnostics: "Show memory in diagnostic views",
  capture_policy: "Per-category capture policy",
  recall_policy: "Per-category recall policy",
  agent_scheduling_enabled: "Let Eclipse schedule work for you",
  acquisition_enabled: "Let Eclipse collect datasets for you",
};

const LEARNING_MODE_OPTIONS: { value: string; label: string; hint: string }[] = [
  {
    value: "automatic_selective", label: "Automatic (selective)",
    hint: "Save strong, durable, low-risk facts automatically — no per-run prompt. Requires recurrence for project-specific claims.",
  },
  {
    value: "ask_before_saving", label: "Ask before saving",
    hint: "Stage candidates and request approval (an inert suggestion); never save on your behalf.",
  },
  { value: "off", label: "Off", hint: "Do not learn automatically. Explicit “remember/forget/correct” requests still work." },
];

const LEARNING_MODE_KEYS = new Set(["memory_mode", "skill_learning_mode"]);

// Legacy derived booleans are read-only projections of the learning modes; they
// are not user-editable policy keys and must not render as controls.
const DERIVED_POLICY_KEYS = new Set([
  "auto_capture_enabled",
  "auto_suggest_enabled",
  "auto_candidate_detection",
]);

// Preference controls live on the Preferences tab, not the generic policy list.
const PREFERENCE_POLICY_KEYS = new Set(["preference_learning_mode", "preference_min_observations",
  "preference_min_distinct_runs", "preference_min_consistency", "preference_confidence_threshold",
  "preference_suppression_days", "preference_dimensions"]);

const POLICY_HINTS: Record<string, string> = {
  memory_mode: "How durable user preferences and project facts are learned.",
  skill_learning_mode: "How reusable procedures become learning candidates (always inert until reviewed).",
  memory_enabled: "Hard local off switch: when off, no memory is stored at all — not even an explicit “remember this”.",
  retention_days: "Days an automatically learned memory is kept before it becomes eligible for expiry review. 0 = never. Explicit memory is never auto-expired.",
  memory_in_diagnostics: "Whether memory content appears in the Lifecycle and explanation views. Off hides it without deleting anything.",
  capture_policy: "Per-category capture rule. “deny” refuses a category; it can never widen authorization.",
  recall_policy: "Per-category recall rule. “deny” removes a category from recall; scope/privacy filtering stays authoritative.",
  agent_scheduling_enabled: "When on, Eclipse can set up recurring finance jobs from a fixed list — each one saved switched off until you turn it on under Scheduled Jobs. Off by default.",
  acquisition_enabled: "When on, Eclipse can pull whole datasets (price history, an economic series, company statements) from a fixed list of sources. Each pull is capped, saved as a file with a record of what it is, and a partial pull is always marked partial. Off by default.",
};

const CATEGORY_POLICY_KEYS = new Set(["capture_policy", "recall_policy"]);
const CATEGORY_POLICY_OPTIONS = ["", "allow", "suggest", "deny"] as const;

export function Policies({ isOperator }: { isOperator: boolean }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof getPolicies>> | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const result = await getPolicies(); setData(result); setDraft(result.policies); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!data) return;
    setSaving(true); setToast(null);
    const changed: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(draft)) {
      if (value !== data.policies[key]) changed[key] = value;
    }
    if (Object.keys(changed).length === 0) { setToast("No changes"); setSaving(false); return; }
    try {
      const result = await updatePolicies(changed);
      setData({ ...data, policies: result.policies });
      setDraft(result.policies);
      setToast("Policies saved");
    } catch (err) {
      setToast(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
      setTimeout(() => setToast(null), 4000);
    }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const lockedKeys = new Set(Object.keys(data.locked));

  return (
    <div className="animate-fade-in-up">
      <Header title="Memory Policies" hint="Configurable behaviour with hard safety floors. Automatic skill promotion is locked off regardless of setting; values are bounded and validated server-side. Learned-preference mode, dimensions and thresholds live on the Preferences tab." />
      {data.budget && !data.budget.unlimited && (
        <p className={cn("mb-3 text-[11px]", data.budget.full ? "text-amber-400" : "text-muted-foreground")}>
          {data.budget.full
            ? `Memory is full — ${data.budget.active}/${data.budget.limit} active. Archive or review memories to free space; existing memory is never deleted automatically.`
            : `Storage: ${data.budget.active}/${data.budget.limit} active memories (${data.budget.remaining} remaining).`}
        </p>
      )}
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      <div className="space-y-2">
        {Object.entries(draft)
          .filter(([key]) => !DERIVED_POLICY_KEYS.has(key) && !PREFERENCE_POLICY_KEYS.has(key))
          .map(([key, value]) => {
          const locked = lockedKeys.has(key);
          const isMode = LEARNING_MODE_KEYS.has(key);
          const isBool = typeof data.defaults[key] === "boolean";
          const numeric = typeof data.defaults[key] === "number";
          const isCategory = CATEGORY_POLICY_KEYS.has(key);
          if (isCategory) {
            const table = (value && typeof value === "object" ? value : {}) as Record<string, string>;
            return (
              <div key={key} className="rounded-2xl border border-white/10 glass-card p-3.5">
                <p className="text-[12px] text-foreground">{POLICY_LABELS[key] ?? key}</p>
                <p className="font-mono text-[9px] text-muted-foreground">{key}</p>
                {POLICY_HINTS[key] && <p className="mt-1 text-[10px] text-muted-foreground/80">{POLICY_HINTS[key]}</p>}
                <div className="mt-2 flex flex-wrap gap-2">
                  {MEMORY_TYPES.filter((t) => t !== "all").map((t) => (
                    <label key={t} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      <span>{t}</span>
                      <select
                        value={table[t] ?? ""}
                        disabled={!isOperator || saving}
                        onChange={(e) => {
                          const next = { ...table };
                          if (e.target.value) next[t] = e.target.value;
                          else delete next[t];
                          setDraft({ ...draft, [key]: next });
                        }}
                        className="rounded-lg border border-border/30 bg-background/60 px-1.5 py-0.5 text-[10px] outline-none focus:border-primary/40 disabled:opacity-60"
                      >
                        {CATEGORY_POLICY_OPTIONS.map((option) => (
                          <option key={option || "unset"} value={option}>{option || "mode default"}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              </div>
            );
          }
          return (
            <div key={key} className="rounded-2xl border border-white/10 glass-card p-3.5 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[12px] text-foreground">{POLICY_LABELS[key] ?? key}</p>
                <p className="font-mono text-[9px] text-muted-foreground">{key}{locked ? " · locked" : ""}</p>
                {POLICY_HINTS[key] && <p className="mt-1 text-[10px] text-muted-foreground/80">{POLICY_HINTS[key]}</p>}
                {isMode && (
                  <p className="mt-1 text-[10px] text-muted-foreground/80">
                    {LEARNING_MODE_OPTIONS.find((o) => o.value === value)?.hint}
                  </p>
                )}
              </div>
              {isMode ? (
                <select
                  value={String(value)}
                  disabled={!isOperator || saving}
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                  className="shrink-0 rounded-xl border border-border/30 bg-background/60 px-2 py-1 text-[11px] outline-none focus:border-primary/40 disabled:opacity-60"
                >
                  {LEARNING_MODE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              ) : isBool ? (
                <button
                  disabled={!isOperator || locked || saving}
                  onClick={() => setDraft({ ...draft, [key]: !value })}
                  className={cn(
                    "shrink-0 flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-[10px] font-bold cursor-pointer",
                    value ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-border/40 text-muted-foreground",
                    (locked || !isOperator) && "opacity-60 cursor-not-allowed"
                  )}
                >
                  {locked && <Lock size={10} />}
                  {value ? "on" : "off"}
                </button>
              ) : (
                <input
                  type="number"
                  value={String(value)}
                  step={numeric && data.defaults[key] !== undefined && !Number.isInteger(data.defaults[key] as number) ? 0.1 : 1}
                  min={data.bounds[key]?.[0]}
                  max={data.bounds[key]?.[1]}
                  disabled={!isOperator || saving}
                  onChange={(e) => setDraft({ ...draft, [key]: Number(e.target.value) })}
                  className="shrink-0 w-28 rounded-xl border border-border/30 bg-background/60 px-2 py-1 text-[11px] text-right outline-none focus:border-primary/40 disabled:opacity-60"
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || saving} onClick={save}>
          {saving ? <Loader2 size={13} className="mr-1 animate-spin" /> : null} Save changes
        </Button>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || saving} onClick={load}>
          <RefreshCcw size={13} className="mr-1" /> Reload
        </Button>
        {!isOperator && <span className="text-[10px] text-amber-300/90">Read-only session — policy changes require operator authorization.</span>}
      </div>
    </div>
  );
}
