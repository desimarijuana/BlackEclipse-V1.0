"use client";

// ── Eclipse Memory — the Memory Control Room (Phase 3-M) ────────────────────
// Tabs: Overview · Memories · Corrections/Mistakes · Health. Reuses the Skills
// Control Room primitives (frosted glass, tab bar, badges) — no new visual
// language. All counts are real; no fabricated activity.

import { useCallback, useEffect, useState } from "react";
import {
  Activity, AlertCircle, Brain, Database, Loader2, Lock, Plus, RefreshCcw,
  Search, Settings2, ShieldCheck, Trash2, Wrench, X,
} from "lucide-react";
import { TabBar } from "@/components/ui/tab-bar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  memoryHealth, memoryOverview, listMemories, getMemory, createMemory,
  archiveMemory, reviewMemory, listCorrections, listMistakes, retrieveMemories,
  getPolicies, updatePolicies, clientIsOperator,
} from "@/lib/harness/eclipse-memory-browser";
import type {
  CorrectionRecord, EclipseMemoryHealth, MemoryDetail, MemoryOverview,
  MemoryRecord, MemoryRetrievalDiagnostics, MistakeRecord,
} from "@/lib/harness/eclipse-memory-types";

type Tab = "overview" | "memories" | "activity" | "policies" | "health";

const MEMORY_TYPES = ["all", "preference", "semantic", "procedural", "episodic", "correction", "constraint", "observation", "summary"];
const STATUSES = ["all", "active", "proposed", "archived", "superseded", "rejected"];

export function EclipseMemoryScreen({ isOperator = clientIsOperator() }: { isOperator?: boolean }) {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="w-full px-4 py-6 md:px-8">
      <TabBar
        items={[
          { id: "overview", label: "Overview", icon: Brain },
          { id: "memories", label: "Memories", icon: Database },
          { id: "activity", label: "Activity", icon: Activity },
          { id: "policies", label: "Policies", icon: Settings2 },
          { id: "health", label: "Health", icon: ShieldCheck },
        ]}
        activeId={tab}
        onChange={(id) => setTab(id as Tab)}
        variant="subtle"
      />
      {tab === "overview" && <Overview />}
      {tab === "memories" && <Memories isOperator={isOperator} />}
      {tab === "activity" && <ActivityView />}
      {tab === "policies" && <Policies isOperator={isOperator} />}
      {tab === "health" && <Health />}
    </div>
  );
}

// ── Overview ────────────────────────────────────────────────────────────────

function Overview() {
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await memoryOverview()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const tiles = [
    { label: "Memories", value: data.memories.total, sub: `${Object.keys(data.memories.byType).length} types` },
    { label: "Active", value: data.memories.byStatus.active ?? 0, sub: "usable now" },
    { label: "Proposed", value: data.memories.byStatus.proposed ?? 0, sub: "awaiting review" },
    { label: "Skills", value: data.skills.installed, sub: "installed" },
    { label: "Learning candidates", value: data.candidates, sub: "in queue" },
    { label: "Corrections", value: data.corrections, sub: "recorded" },
    { label: "Mistakes", value: data.mistakes, sub: "captured" },
    { label: "Retrievals", value: data.retrievals, sub: "audited" },
  ];

  return (
    <div className="animate-fade-in-up">
      <Header
        title="Eclipse Memory"
        hint="Dedicated persistence for agent memory, skills, learning and audit. Real counts only — nothing is fabricated."
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-2xl border border-white/10 dark:border-white/5 glass-card p-4">
            <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{tile.label}</p>
            <p className="mt-1.5 font-serif text-2xl font-semibold text-foreground tabular-nums">{tile.value}</p>
            <p className="text-[10px] text-muted-foreground">{tile.sub}</p>
          </div>
        ))}
      </div>

      {data.memories.total === 0 && (
        <div className="mt-6 rounded-2xl border border-border/20 glass-card-subtle p-8 text-center">
          <Brain size={26} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">No memory yet</p>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-md mx-auto">
            Memory is captured when you ask the agent to remember something, when you correct it, or when a
            run produces a reusable lesson. Nothing is stored automatically.
          </p>
        </div>
      )}

      {Object.keys(data.memories.byType).length > 0 && (
        <div className="mt-6 rounded-2xl border border-white/10 glass-card p-4">
          <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-3">Memory by type</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.memories.byType).map(([type, count]) => (
              <span key={type} className="rounded-lg border border-border/30 bg-accent/30 px-2 py-1 text-[11px] text-foreground">
                {type} <span className="text-muted-foreground">×{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <Button variant="outline" size="sm" className="mt-6 rounded-xl cursor-pointer" onClick={load}>
        <RefreshCcw size={13} className="mr-1" /> Refresh
      </Button>
    </div>
  );
}

// ── Memories (explorer) ─────────────────────────────────────────────────────

function Memories({ isOperator }: { isOperator: boolean }) {
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showSave, setShowSave] = useState(false);
  const [draft, setDraft] = useState({ content: "", memoryType: "semantic", scope: "general", subject: "" });

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setMemories(await listMemories({
        memoryType: type === "all" ? undefined : type,
        status: status === "all" ? undefined : status,
      }));
    } catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, [type, status]);
  useEffect(() => { void load(); }, [load]);

  const filtered = query
    ? memories.filter((m) => `${m.content} ${m.subject ?? ""}`.toLowerCase().includes(query.toLowerCase()))
    : memories;

  const open = async (id: string) => { setDetail(await getMemory(id)); };

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(); if (detail) await open(detail.memory.id); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  const save = async () => {
    if (!draft.content.trim()) return;
    await act(
      () => createMemory({
        memoryType: draft.memoryType,
        content: draft.content,
        source: "manual",
        scope: draft.scope,
        subject: draft.subject || undefined,
      }),
      "Memory saved"
    );
    setShowSave(false);
    setDraft({ content: "", memoryType: "semantic", scope: "general", subject: "" });
  };

  return (
    <div className="animate-fade-in-up">
      <div className="mb-5 flex items-start justify-between gap-4">
        <Header
          title="Memory Explorer"
          hint="Proposed memory is inert until reviewed. Archived and superseded memory are retained for audit, never deleted."
        />
        <Button size="sm" className="rounded-xl cursor-pointer shrink-0" disabled={!isOperator} onClick={() => setShowSave((v) => !v)}>
          {showSave ? <X size={13} className="mr-1" /> : <Plus size={13} className="mr-1" />}
          {showSave ? "Cancel" : "Save memory"}
        </Button>
      </div>
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      {showSave && (
        <div className="mb-4 rounded-2xl border border-primary/20 glass-card p-4 space-y-2">
          <textarea
            value={draft.content}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
            rows={2}
            placeholder="A durable fact to remember (declarative, not an instruction)…"
            className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40"
          />
          <div className="flex flex-wrap gap-2">
            <select value={draft.memoryType} onChange={(e) => setDraft({ ...draft, memoryType: e.target.value })}
              className="rounded-xl border border-border/30 bg-background/60 px-2 py-1.5 text-[11px] outline-none">
              {MEMORY_TYPES.filter((t) => t !== "all").map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={draft.scope} onChange={(e) => setDraft({ ...draft, scope: e.target.value })}
              className="rounded-xl border border-border/30 bg-background/60 px-2 py-1.5 text-[11px] outline-none">
              {["general", "user", "market", "task"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <Input value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
              placeholder="subject (optional)" className="w-40 rounded-xl bg-background/60" />
            <Button size="sm" className="rounded-xl cursor-pointer" disabled={busy || !draft.content.trim()} onClick={save}>Save</Button>
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search memory…" className="pl-9 rounded-xl bg-background/60" />
        </div>
        <FilterRow label="Type" options={MEMORY_TYPES} value={type} onChange={setType} />
        <FilterRow label="Status" options={STATUSES} value={status} onChange={setStatus} />
      </div>

      {loading ? <Spinner /> : error ? <ErrorBox message={error} /> : filtered.length === 0 ? (
        <EmptyBox title="No memories match" hint="Memory is only stored from explicit saves, corrections and validated lessons." />
      ) : (
        <div className="space-y-2">
          {filtered.map((memory) => (
            <button
              key={memory.id}
              onClick={() => open(memory.id)}
              className="w-full text-left rounded-2xl border border-white/10 dark:border-white/5 glass-card p-3.5 hover:border-primary/30 cursor-pointer"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <TypeBadge type={memory.memoryType} />
                    <StatusPill status={memory.status} />
                    <span className="text-[9px] text-muted-foreground">{memory.scope}{memory.scopeId ? `:${memory.scopeId}` : ""}</span>
                    {memory.subject && <span className="text-[9px] text-primary">#{memory.subject}</span>}
                  </div>
                  <p className="mt-1.5 text-[12px] text-foreground leading-relaxed line-clamp-2">{memory.content}</p>
                </div>
                <span className="shrink-0 text-[9px] text-muted-foreground">
                  {(memory.confidence * 100).toFixed(0)}% · {memory.verification}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end" role="dialog">
          <div className="fixed inset-0 bg-black/40" onClick={() => setDetail(null)} />
          <div className="relative w-full max-w-md h-full glass-card-strong border-l border-white/10 overflow-y-auto p-5">
            <button onClick={() => setDetail(null)} className="mb-3 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">← Close</button>
            <div className="flex items-center gap-2 flex-wrap">
              <TypeBadge type={detail.memory.memoryType} />
              <StatusPill status={detail.memory.status} />
            </div>
            <p className="mt-3 text-[12px] text-foreground leading-relaxed">{detail.memory.content}</p>
            <dl className="mt-4 text-[11px]">
              <Meta label="Scope" value={`${detail.memory.scope}${detail.memory.scopeId ? `:${detail.memory.scopeId}` : ""}`} />
              <Meta label="Subject" value={detail.memory.subject ?? "—"} />
              <Meta label="Source" value={detail.memory.source ?? "—"} />
              <Meta label="Run" value={detail.memory.sourceRunId ?? "—"} />
              <Meta label="Confidence" value={`${(detail.memory.confidence * 100).toFixed(0)}%`} />
              <Meta label="Verification" value={detail.memory.verification} />
              <Meta label="Accesses" value={String(detail.memory.accessCount)} />
              <Meta label="Created" value={detail.memory.createdAt} />
            </dl>

            {detail.evidence.length > 0 && (
              <div className="mt-4">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Evidence</p>
                <ul className="mt-1 space-y-1">
                  {detail.evidence.map((ev) => (
                    <li key={ev.id} className="text-[10px] text-muted-foreground">
                      [{ev.sourceType}/{ev.verificationStatus}] {ev.sourceUrl ?? ev.sourceRef ?? "—"}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.links.length > 0 && (
              <div className="mt-4">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Links</p>
                <ul className="mt-1 space-y-1">
                  {detail.links.map((link) => (
                    <li key={link.id} className="text-[10px] text-muted-foreground">{link.relation}: {link.toId === detail.memory.id ? link.fromId : link.toId}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              {detail.memory.status === "proposed" && (
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => reviewMemory(detail.memory.id, true), "Memory approved")}>
                  Approve
                </Button>
              )}
              {detail.memory.status !== "archived" && (
                <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300" disabled={!isOperator || busy}
                  onClick={() => act(() => archiveMemory(detail.memory.id), "Memory archived")}>
                  <Trash2 size={12} className="mr-1" /> Archive
                </Button>
              )}
            </div>
            {!isOperator && <p className="mt-2 text-[10px] text-amber-300/90">Read-only session — review/archive require operator authorization.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Activity (retrieval / corrections / mistakes) ───────────────────────────

function ActivityView() {
  const [corrections, setCorrections] = useState<CorrectionRecord[]>([]);
  const [mistakes, setMistakes] = useState<MistakeRecord[]>([]);
  const [diag, setDiag] = useState<MemoryRetrievalDiagnostics | null>(null);
  const [probe, setProbe] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [c, m] = await Promise.all([listCorrections(), listMistakes()]);
      setCorrections(c); setMistakes(m);
    } catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const runProbe = async () => {
    if (!probe.trim()) return;
    try { setDiag((await retrieveMemories({ query: probe, limit: 8 })).diagnostics); }
    catch (err) { setError(err instanceof Error ? err.message : "retrieval failed"); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div className="animate-fade-in-up">
      <Header title="Activity & Diagnostics" hint="Corrections and mistakes are captured records. The retriever probe shows exactly what would be recalled and why." />

      <div className="rounded-2xl border border-white/10 glass-card p-4 mb-3">
        <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Retrieval probe</p>
        <div className="flex gap-2">
          <Input value={probe} onChange={(e) => setProbe(e.target.value)} placeholder="What would be recalled for…" className="rounded-xl bg-background/60" />
          <Button size="sm" className="rounded-xl cursor-pointer" onClick={runProbe}>Run</Button>
        </div>
        {diag && (
          <div className="mt-3 text-[11px] text-muted-foreground">
            <p>{diag.selected} selected of {diag.candidates} candidates · {diag.usedChars}/{diag.budgetChars} chars · {diag.durationMs}ms</p>
            <ul className="mt-1 list-disc list-inside space-y-0.5">
              {diag.selectionReasons.slice(0, 6).map((reason, i) => <li key={i}>{reason}</li>)}
              {diag.excluded.slice(0, 4).map((item, i) => <li key={`x${i}`}>excluded {item.id}: {item.reason}</li>)}
            </ul>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Section title={`Corrections (${corrections.length})`} icon={Wrench}>
          {corrections.length === 0 ? <Muted>None recorded.</Muted> : corrections.map((c) => (
            <div key={c.id} className="rounded-xl border border-border/20 bg-background/30 p-2.5 mb-2">
              <p className="text-[11px] text-foreground">{c.subject ?? "general"}: {c.wrong} → {c.correction}</p>
              <p className="mt-1 text-[9px] text-muted-foreground">{c.providedBy} · {c.scope} · generalizable: {c.generalizable ? "yes" : "no"}</p>
            </div>
          ))}
        </Section>
        <Section title={`Mistakes (${mistakes.length})`} icon={AlertCircle}>
          {mistakes.length === 0 ? <Muted>None captured.</Muted> : mistakes.map((m) => (
            <div key={m.id} className="rounded-xl border border-border/20 bg-background/30 p-2.5 mb-2">
              <p className="text-[11px] text-foreground">{m.category} · {m.severity}</p>
              <p className="mt-1 text-[9px] text-muted-foreground">{m.expected} → {m.actual} · reusable: {m.reusable ? "yes" : "no"}</p>
            </div>
          ))}
        </Section>
      </div>
    </div>
  );
}

// ── Policies ────────────────────────────────────────────────────────────────

const POLICY_LABELS: Record<string, string> = {
  auto_capture_enabled: "Automatic memory capture",
  auto_candidate_detection: "Automatic learning-candidate detection",
  candidate_confidence_threshold: "Candidate confidence threshold",
  context_budget_chars: "Retrieval context budget (chars)",
  retrieval_limit: "Max memories per retrieval",
  retention_days: "Retention review window (days, 0 = never)",
  include_proposed_in_retrieval: "Inject proposed memory without review",
  audit_retention_rows: "Audit rows kept (0 = unlimited)",
  auto_promote_low_risk: "Auto-promote low-risk skills (locked off)",
};

function Policies({ isOperator }: { isOperator: boolean }) {
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
      <Header title="Memory Policies" hint="Configurable behaviour with hard safety floors. Automatic skill promotion is locked off regardless of setting; values are bounded and validated server-side." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      <div className="space-y-2">
        {Object.entries(draft).map(([key, value]) => {
          const locked = lockedKeys.has(key);
          const isBool = typeof data.defaults[key] === "boolean";
          const numeric = typeof data.defaults[key] === "number";
          return (
            <div key={key} className="rounded-2xl border border-white/10 glass-card p-3.5 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[12px] text-foreground">{POLICY_LABELS[key] ?? key}</p>
                <p className="font-mono text-[9px] text-muted-foreground">{key}{locked ? " · locked" : ""}</p>
              </div>
              {isBool ? (
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

// ── Health ──────────────────────────────────────────────────────────────────

function Health() {
  const [health, setHealth] = useState<EclipseMemoryHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setHealth(await memoryHealth()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!health) return null;

  return (
    <div className="animate-fade-in-up">
      <Header title="Database Health" hint="eclipse-memory is a separate SQLite database with its own schema and migrations." />
      <div className="rounded-2xl border border-white/10 glass-card p-4">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", health.ok ? "bg-emerald-400" : "bg-rose-400")} />
          <span className="text-sm font-semibold text-foreground">{health.ok ? "Healthy" : "Unhealthy"}</span>
        </div>
        <dl className="mt-3 text-[11px]">
          <Meta label="Path" value={health.path} />
          <Meta label="Integrity" value={health.integrity ?? "—"} />
          <Meta label="Schema version" value={String(health.schemaVersion ?? "—")} />
          <Meta label="Up to date" value={health.upToDate ? "yes" : "no"} />
          <Meta label="Tables" value={String(health.tables ?? "—")} />
          {health.counts && Object.entries(health.counts).map(([k, v]) => <Meta key={k} label={k} value={String(v)} />)}
        </dl>
      </div>
      <Button variant="outline" size="sm" className="mt-4 rounded-xl cursor-pointer" onClick={load}>
        <RefreshCcw size={13} className="mr-1" /> Refresh
      </Button>
    </div>
  );
}

// ── Shared atoms ────────────────────────────────────────────────────────────

function Header({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
        <Brain className="text-primary" size={22} />
      </span>
      <div>
        <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-2xl">{hint}</p>
      </div>
    </div>
  );
}

function FilterRow({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      {options.map((option) => (
        <button key={option} onClick={() => onChange(option)}
          className={cn("rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer",
            value === option ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")}>
          {option}
        </button>
      ))}
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    preference: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    semantic: "border-violet-400/30 bg-violet-400/10 text-violet-300",
    procedural: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    episodic: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    correction: "border-rose-400/30 bg-rose-400/10 text-rose-300",
    constraint: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  };
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", colors[type] ?? "border-border/40 text-muted-foreground")}>
      {type}
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    proposed: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    superseded: "border-border/40 text-muted-foreground",
    archived: "border-border/40 text-muted-foreground",
    rejected: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  };
  return <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", colors[status] ?? "border-border/40 text-muted-foreground")}>{status}</span>;
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1 border-b border-border/10 last:border-0">
      <dt className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-[11px] text-foreground text-right break-words min-w-0">{value}</dd>
    </div>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 glass-card p-4">
      <div className="flex items-center gap-2 mb-3"><Icon size={13} className="text-primary" /><span className="text-[11px] font-semibold text-foreground">{title}</span></div>
      {children}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] text-muted-foreground">{children}</p>;
}

function Spinner() {
  return <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" size={16} /> Loading…</div>;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center">
      <AlertCircle size={22} className="mx-auto text-rose-400" />
      <p className="mt-2 text-sm text-foreground">{message}</p>
    </div>
  );
}

function EmptyBox({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-border/20 glass-card-subtle p-10 text-center">
      <Database size={24} className="mx-auto text-muted-foreground/60" />
      <p className="mt-3 text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
