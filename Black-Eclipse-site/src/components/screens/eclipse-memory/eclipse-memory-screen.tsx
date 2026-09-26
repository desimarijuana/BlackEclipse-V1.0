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
import { useSubroute } from "@/hooks/use-subroute";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  memoryHealth, memoryOverview, listMemories, getMemory, createMemory,
  archiveMemory, reviewMemory, restoreMemory, renewMemory, memoryLifecycle, memoryRetention,
  memorySemanticStatus, listCorrections,
  rebuildSemanticIndex,
  listMistakes, retrieveMemories,
  getPolicies, updatePolicies, clientIsOperator,
  exportMemory, importMemory, backupMemory, memoryDatabaseHealth, resetMemory,
  listSuggestions, acceptSuggestion, dismissSuggestion, type MemorySuggestion,
  memoryProfile, rebuildProfile,
  sessionSearch, sessionSearchHealth, sessionOpen, sessionDelete,
  learningReviewHealth, listLearningReviews, runLearningReview, decideLearningReview,
  getMemoryFiles, regenerateMemoryFiles, previewMarkdownImport, importMarkdown, restoreMemoryFiles,
} from "@/lib/harness/eclipse-memory-browser";
import type {
  CorrectionRecord, EclipseMemoryHealth, MemoryDatabaseHealth, MemoryDetail,
  MemoryExportDocument, MemoryLifecycleView,
  MemoryLifecycleResponse, MemoryOverview,
  MemoryProfileResponse,
  MemoryRetentionStatus, MemorySemanticStatus,
  MemoryRecord, MemoryRetrievalDiagnostics, MistakeRecord,
  SessionSearchHealth, SessionSearchHit,
  LearningReviewHealth, LearningReviewRecord,
} from "@/lib/harness/eclipse-memory-types";

type Tab = "overview" | "memories" | "profile" | "history" | "reviews" | "lifecycle" | "suggestions" | "activity" | "policies" | "health";

const MEMORY_TYPES = ["all", "preference", "semantic", "procedural", "episodic", "correction", "constraint", "observation", "summary"];
const STATUSES = ["all", "active", "proposed", "archived", "superseded", "rejected"];

/** Confidence as a percentage, tolerant of a null/undefined value.
 *
 * A memory row can lack confidence (a partial/suggestion-shaped object), and the
 * previous `(confidence * 100)` threw "Cannot read properties of null" when the
 * user typed in the memory search box (the reported `None` conversion error).
 * Render an honest placeholder instead of crashing the screen. */
function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

export function EclipseMemoryScreen({ isOperator = clientIsOperator() }: { isOperator?: boolean }) {
  const [tab, setTab] = useState<Tab>("overview");
  // Deep links land on the matching sub-page:
  // memory.explorer/activity/health → Memories/Activity/Health.
  useSubroute("memory", (req) => {
    const slug = req.subroute.split(".")[1];
    const map: Record<string, Tab> = {
      explorer: "memories", activity: "activity", health: "health",
      memories: "memories", overview: "overview", policies: "policies",
      suggestions: "suggestions", lifecycle: "lifecycle", profile: "profile",
      history: "history", sessions: "history",
      reviews: "reviews", learning: "reviews",
    };
    if (slug && map[slug]) setTab(map[slug]);
  });

  return (
    <div className="w-full px-4 py-6 md:px-8">
      <TabBar
        items={[
          { id: "overview", label: "Overview", icon: Brain },
          { id: "memories", label: "Memories", icon: Database },
          { id: "profile", label: "Profile", icon: Lock },
          { id: "history", label: "History", icon: Search },
          { id: "reviews", label: "Reviews", icon: Activity },
          { id: "lifecycle", label: "Lifecycle", icon: RefreshCcw },
          { id: "suggestions", label: "Suggestions", icon: Plus },
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
      {tab === "profile" && <Profile isOperator={isOperator} />}
      {tab === "history" && <History />}
      {tab === "reviews" && <Reviews isOperator={isOperator} />}
      {tab === "lifecycle" && <Lifecycle isOperator={isOperator} />}
      {tab === "suggestions" && <Suggestions isOperator={isOperator} />}
      {tab === "activity" && <ActivityView />}
      {tab === "policies" && <Policies isOperator={isOperator} />}
      {tab === "health" && <Health isOperator={isOperator} />}
    </div>
  );
}

// ── Lifecycle (active / suggestions / expired / superseded / conflicts) ──────

const LIFECYCLE_VIEWS: Array<{ id: MemoryLifecycleView; label: string; hint: string }> = [
  { id: "active", label: "Active", hint: "Usable and eligible for recall." },
  { id: "never-used", label: "Never used", hint: "Active but never recalled — candidates for review." },
  { id: "frequently-recalled", label: "Frequently recalled", hint: "Recalled 3+ times — likely useful." },
  { id: "automatic", label: "Automatically learned", hint: "Learned from runs/conventions, not stated by the user." },
  { id: "expired", label: "Expired", hint: "Retention elapsed — inert, retained for audit." },
  { id: "superseded", label: "Superseded / conflicts", hint: "Replaced by a later memory; excluded from recall." },
  { id: "rejected", label: "Rejected", hint: "Refused at review; never recalled." },
  { id: "archived", label: "Archived", hint: "Deliberately retired; retained for audit." },
];

function Lifecycle({ isOperator }: { isOperator: boolean }) {
  const [overview, setOverview] = useState<MemoryLifecycleResponse | null>(null);
  const [view, setView] = useState<MemoryLifecycleView>("active");
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [retention, setRetention] = useState<MemoryRetentionStatus | null>(null);
  const [semantic, setSemantic] = useState<MemorySemanticStatus | null>(null);

  const load = useCallback(async (target: MemoryLifecycleView) => {
    setLoading(true); setError(null);
    try {
      const body = await memoryLifecycle(target);
      setOverview(body);
      setMemories(body.memories ?? []);
      setRetention(await memoryRetention());
      setSemantic(await memorySemanticStatus());
    } catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(view); }, [load, view]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(view); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  const active = LIFECYCLE_VIEWS.find((v) => v.id === view);

  return (
    <div className="animate-fade-in-up">
      <Header
        title="Memory Lifecycle"
        hint="Every memory has an explicit state. Expired, superseded, rejected and archived memory is never recalled; conflicts do not coexist as active truth."
      />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      {retention && (
        <div className="mb-4 rounded-2xl border border-white/10 glass-card p-3.5">
          <p className="text-[11px] font-semibold text-foreground">Retention</p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {retention.automaticExpiryEnabled
              ? `Automatically learned memory expires after ${retention.retentionDays} day(s); explicit memory is never silently expired.`
              : "Automatic retention is off (0 days) — automatic memory never expires by policy. Explicit memory is never silently expired."}
          </p>
          {retention.lastSweep ? (
            <p className={cn("mt-1 text-[10px]", retention.lastSweep.ok ? "text-muted-foreground" : "text-amber-400")}>
              Last sweep {retention.lastSweep.ranAt}: inspected {retention.lastSweep.inspected}, expired {retention.lastSweep.expired}, skipped {retention.lastSweep.skipped}
              {!retention.lastSweep.ok && retention.lastSweep.error ? ` — failed: ${retention.lastSweep.error}` : ""}
            </p>
          ) : (
            <p className="mt-1 text-[10px] text-muted-foreground">No sweep recorded yet.</p>
          )}
        </div>
      )}

      {semantic && (
        <div className="mb-4 rounded-2xl border border-white/10 glass-card p-3.5">
          <p className="text-[11px] font-semibold text-foreground">Contradiction detection</p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {semantic.mode === "lexical+semantic"
              ? "Lexical + local semantic candidates. Semantic similarity can only suggest a possible contradiction for review — it never supersedes or activates memory."
              : semantic.mode === "lexical+semantic-unavailable"
                ? "Semantic detection is enabled but no local backend is available — detection is lexical-only (safe fallback)."
                : "Lexical detection only. No network, no model, no embeddings."}
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground/80">
            backend: {semantic.backend} · detector {semantic.detectorVersion}
          </p>
          {semantic.controls && (
            <p className="mt-1 text-[10px] text-muted-foreground/80">
              threshold {String(semantic.controls.threshold ?? "—")} ·
              {" "}candidates ≤ {String(semantic.controls.candidateLimit ?? "—")} ·
              {" "}index ≤ {String(semantic.controls.indexLimit ?? "—")} ·
              {" "}timeout {String(semantic.controls.timeoutMs ?? "—")}ms
            </p>
          )}
          {semantic.stats?.available && (
            <p className="mt-1 text-[10px] text-muted-foreground/80">
              semantic proposals: {semantic.stats.proposedBySemantics ?? 0} ·
              {" "}actionable {semantic.stats.actionableCandidates ?? 0} ·
              {" "}confirmed {semantic.stats.confirmedAfterReview ?? 0} ·
              {" "}kept/dismissed {semantic.stats.keptExistingOrDismissed ?? 0}
            </p>
          )}
          {semantic.backends && semantic.backends.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground/60">
              backends: {semantic.backends.map((b) => `${b.backend}${b.available ? "" : " (unavailable)"}`).join(", ")}
            </p>
          )}
          <button
            type="button"
            disabled={!isOperator || busy}
            onClick={() => act(async () => {
              const result = await rebuildSemanticIndex();
              return result.reason;
            }, "Semantic index: no persistent index to rebuild (computed per write)")}
            className="mt-2 rounded-lg border border-white/10 px-2 py-0.5 text-[9px] text-muted-foreground hover:text-foreground disabled:opacity-50 cursor-pointer"
          >
            Clear / rebuild optional index
          </button>
        </div>
      )}

      {overview && (
        <div className="mb-4 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Active", value: overview.counts.active },
            { label: "Explicit", value: overview.counts.explicit },
            { label: "Automatic", value: overview.counts.automatic },
            { label: "Never used", value: overview.counts.neverUsed },
            { label: "Frequently recalled", value: overview.counts.frequentlyRecalled },
            { label: "Superseded", value: overview.counts.superseded },
            { label: "Expired", value: overview.counts.expired },
            { label: "Rejected", value: overview.counts.rejected },
          ].map((tile) => (
            <div key={tile.label} className="rounded-2xl border border-white/10 glass-card p-3">
              <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{tile.label}</p>
              <p className="mt-1 text-[18px] font-semibold text-foreground">{tile.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-1.5">
        {LIFECYCLE_VIEWS.map((v) => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className={cn(
              "rounded-xl px-2.5 py-1 text-[10px] border cursor-pointer",
              view === v.id
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-white/10 text-muted-foreground hover:text-foreground"
            )}
          >
            {v.label}
          </button>
        ))}
      </div>
      {active && <p className="mb-3 text-[10px] text-muted-foreground">{active.hint}</p>}

      {loading ? <Spinner /> : error ? <ErrorBox message={error} /> : memories.length === 0 ? (
        <EmptyBox title="Nothing in this view" hint="Memory only appears here once it exists in that lifecycle state." />
      ) : (
        <div className="space-y-2">
          {memories.map((memory) => (
            <button
              key={memory.id}
              onClick={async () => setDetail(await getMemory(memory.id))}
              className="w-full text-left rounded-2xl border border-white/10 glass-card p-3.5 hover:border-primary/30 cursor-pointer"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <TypeBadge type={memory.memoryType} />
                    <StatusPill status={memory.status} />
                    <span className="text-[9px] text-muted-foreground">
                      {memory.authority === "automatic" ? "automatic" : "explicit"}
                    </span>
                    {memory.subject && <span className="text-[9px] text-primary">#{memory.subject}</span>}
                  </div>
                  <p className="mt-1.5 text-[12px] text-foreground leading-relaxed line-clamp-2">{memory.content}</p>
                  {memory.statusReason && (
                    <p className="mt-0.5 text-[9px] text-muted-foreground/80">{memory.statusReason}</p>
                  )}
                </div>
                <span className="shrink-0 text-[9px] text-muted-foreground">
                  {memory.lastUsedAt ? `used ${memory.lastUsedAt.slice(0, 10)}` : "never used"}
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
            <p className="text-[12px] text-foreground leading-relaxed">{detail.memory.content}</p>
            {detail.explanation && (
              <div className="mt-4 rounded-2xl border border-white/10 glass-card-subtle p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Why this memory exists</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.saveReason}</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.recallDisposition}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  authority: {detail.explanation.authority}
                  {detail.explanation.statusReason ? ` · ${detail.explanation.statusReason}` : ""}
                </p>
              </div>
            )}
            <dl className="mt-4 text-[11px]">
              <Meta label="Status" value={detail.memory.status} />
              <Meta label="Authority" value={detail.memory.authority ?? "explicit"} />
              <Meta label="Expires" value={detail.memory.expiresAt ?? "never"} />
              <Meta label="Last confirmed" value={detail.memory.lastConfirmedAt ?? "—"} />
              <Meta label="Last used" value={detail.memory.lastUsedAt ?? "never"} />
              <Meta label="Last reviewed" value={detail.memory.lastReviewedAt ?? detail.memory.reviewedAt ?? "—"} />
              {detail.memory.supersededBy && <Meta label="Superseded by" value={detail.memory.supersededBy} />}
            </dl>
            {detail.explanation?.conflict && (
              <div className="mt-3 rounded-2xl border border-amber-400/20 glass-card-subtle p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-amber-400">Possible contradiction</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.conflict.reason}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  detector: {detail.explanation.conflict.detector ?? "lexical"}
                  {detail.explanation.conflict.similarity != null ? ` · similarity ${detail.explanation.conflict.similarity}` : ""}
                  {detail.explanation.conflict.authority ? ` · authority ${detail.explanation.conflict.authority}` : ""}
                </p>
                <p className="mt-1 text-[10px] text-muted-foreground/80">
                  {detail.explanation.conflict.requiresConfirmation
                    ? "This is NOT active truth until you confirm. The existing memory stays authoritative."
                    : "Both records are retained for audit; the authoritative one is the active memory."}
                </p>
              </div>
            )}
            {detail.links.filter((l) => l.relation === "superseded").length > 0 && (
              <div className="mt-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Conflict history</p>
                <ul className="mt-1 space-y-1">
                  {detail.links.filter((l) => l.relation === "superseded").map((link) => (
                    <li key={link.id} className="text-[10px] text-muted-foreground">
                      superseded {link.toId === detail.memory.id ? link.fromId : link.toId}
                      {link.note ? ` — ${link.note}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-5 flex flex-wrap gap-2">
              {detail.memory.status === "active" && (
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => renewMemory(detail.memory.id), "Memory confirmed / renewed")}>
                  Confirm & renew
                </Button>
              )}
              {(detail.memory.status === "archived" || detail.memory.status === "expired" || detail.memory.status === "superseded") && (
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => restoreMemory(detail.memory.id), "Memory restored")}>
                  Restore
                </Button>
              )}
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
            {!isOperator && <p className="mt-2 text-[10px] text-amber-300/90">Read-only session — changes require operator authorization.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Overview ────────────────────────────────────────────────────────────────

// ── Profile (always-available compact prompt context) ───────────────────────

function Profile({ isOperator }: { isOperator: boolean }) {
  const [data, setData] = useState<MemoryProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await memoryProfile()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const rebuild = async () => {
    setBusy(true);
    try { await rebuildProfile(); setToast("Profile snapshot rebuilt"); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "rebuild failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const snap = data.snapshot;

  return (
    <div className="animate-fade-in-up">
      <Header title="Persistent Profile" hint="A bounded, deterministic snapshot injected into every run as personalization context — never financial evidence and never an instruction channel. Memory saved during a run appears in later runs only." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      <div className="rounded-2xl border border-white/10 glass-card p-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[11px] text-muted-foreground">
          <span>{snap.selectedIds.length} selected</span>
          <span>{snap.charCount} chars</span>
          <span>~{snap.tokenEstimate} tokens</span>
          <span>{snap.excluded.length} excluded</span>
          <span>schema v{snap.memoryVersion}</span>
          {snap.snapshotId && <span>snapshot {snap.snapshotId.slice(0, 18)}…</span>}
        </div>
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <ProfileSection title="User profile" entries={snap.userEntries} budget={snap.limits.userChars} />
          <ProfileSection title="Project context" entries={snap.projectEntries} budget={snap.limits.projectChars} />
        </div>
      </div>

      {snap.excluded.length > 0 && (
        <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
          <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Excluded ({snap.excluded.length})</p>
          <ul className="space-y-0.5 max-h-48 overflow-auto">
            {snap.excluded.slice(0, 40).map((item, i) => (
              <li key={`${item.id}-${i}`} className="text-[10px] text-muted-foreground">
                {item.id ? `${item.id.slice(0, 16)}…` : "entry"} — {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
        <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Prompt preview</p>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-border/20 bg-background/40 p-3 text-[10px] text-foreground/80">
          {data.prompt || "(empty — no eligible memory yet)"}
        </pre>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={load}>
          <RefreshCcw size={13} className="mr-1" /> Refresh
        </Button>
        <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy} onClick={rebuild}>
          Rebuild snapshot
        </Button>
      </div>
      {!isOperator && <p className="mt-3 text-[10px] text-amber-300/90">Read-only session — rebuilding requires operator authorization.</p>}
    </div>
  );
}

function ProfileSection({ title, entries, budget }: { title: string; entries: MemoryProfileResponse["snapshot"]["userEntries"]; budget?: number }) {
  return (
    <div className="rounded-2xl border border-white/10 glass-card-subtle p-3">
      <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
        {title} <span className="font-normal normal-case tracking-normal">({entries.length}{budget ? ` · ≤${budget} chars` : ""})</span>
      </p>
      {entries.length === 0 ? <Muted>None selected.</Muted> : (
        <ul className="space-y-1.5">
          {entries.map((entry) => (
            <li key={entry.id} className="text-[11px] text-foreground/90">
              <span className="text-foreground/95">{entry.content}</span>
              <span className="ml-1 text-[9px] text-muted-foreground">
                [{entry.memoryType} · {entry.provenance} · {Math.round(entry.confidence * 100)}%]
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Reviews (automatic learning review queue) ───────────────────────────────

function Reviews({ isOperator }: { isOperator: boolean }) {
  const [health, setHealth] = useState<LearningReviewHealth | null>(null);
  const [reviews, setReviews] = useState<LearningReviewRecord[]>([]);
  const [runId, setRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [h, list] = await Promise.all([learningReviewHealth(), listLearningReviews(undefined, 30)]);
      setHealth(h); setReviews(list);
    } catch (err) { setError(err instanceof Error ? err.message : "failed"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  return (
    <div className="animate-fade-in-up">
      <Header title="Automatic Learning Review" hint="A bounded, safe post-run review proposes inert outcomes only. Nothing here enables a skill automatically, and every durable write passes the shared decision gate." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      {error && <ErrorBox message={error} />}

      {health && (
        <div className="rounded-2xl border border-white/10 glass-card p-4">
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted-foreground">
            <span>{health.total} review(s)</span>
            <span>queued: {health.queue.queued}</span>
            <span>running: {health.queue.running}</span>
            <span>max concurrent: {health.queue.maxConcurrent}</span>
            <span>timeout: {health.queue.timeoutMs}ms</span>
          </div>
        </div>
      )}

      <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
        <p className="text-[11px] font-semibold text-foreground">Run a review for a completed run</p>
        <div className="mt-2 flex gap-2">
          <Input value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="run id…" className="rounded-xl bg-background/60" />
          <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy || !runId.trim()}
            onClick={() => act(() => runLearningReview(runId.trim()), "Review complete")}>Deterministic</Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy || !runId.trim()}
            onClick={() => act(() => runLearningReview(runId.trim(), true), "Review complete (model)")}>+ Model</Button>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">The model variant adds an optional bounded review; its output is inert and re-checked by the gate.</p>
      </div>

      <div className="mt-4 space-y-2">
        {reviews.length === 0 ? (
          <EmptyBox title="No reviews yet" hint="Completed runs are reviewed automatically after they finish." />
        ) : reviews.map((review) => (
          <div key={review.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                review.status === "completed" ? "border-emerald-400/30 text-emerald-300" :
                review.status === "failed" ? "border-rose-400/30 text-rose-300" : "border-border/40 text-muted-foreground")}>
                {review.status}
              </span>
              <span className="text-[9px] text-muted-foreground">{review.mode}</span>
              <span className="text-[9px] text-muted-foreground/70">run {review.runId.slice(0, 16)}…</span>
              <span className="text-[9px] text-muted-foreground">{review.createdAt.slice(0, 19)}</span>
              {review.model && <span className="text-[9px] text-muted-foreground">model: {review.model}</span>}
            </div>
            {review.error && <p className="mt-1 text-[10px] text-rose-300">{review.error}</p>}
            {review.result?.outcomes?.length ? (
              <ul className="mt-2 space-y-1">
                {review.result.outcomes.map((outcome, index) => (
                  <li key={index} className="flex items-start justify-between gap-2 rounded-xl border border-border/20 bg-background/30 p-2">
                    <div className="min-w-0">
                      <span className="rounded-full border border-border/40 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{outcome.category}</span>
                      <span className="ml-2 text-[10px] text-muted-foreground">{outcome.inert ? "inert" : "active"}{outcome.created ? " · created" : ""}</span>
                      {outcome.reason && <p className="mt-0.5 text-[10px] text-foreground/80">{outcome.reason}</p>}
                    </div>
                    {isOperator && (outcome.category === "durable_memory_proposal" || outcome.category === "memory_suggestion") && (
                      <div className="flex shrink-0 gap-1">
                        <Button size="sm" className="rounded-lg h-6 px-2 text-[10px] cursor-pointer" disabled={busy}
                          onClick={() => act(() => decideLearningReview(review.id, index, "accept"), "Outcome accepted")}>Accept</Button>
                        <Button size="sm" variant="outline" className="rounded-lg h-6 px-2 text-[10px] cursor-pointer" disabled={busy}
                          onClick={() => act(() => decideLearningReview(review.id, index, "reject"), "Outcome rejected")}>Reject</Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[10px] text-muted-foreground">No outcomes recorded.</p>
            )}
          </div>
        ))}
      </div>

      {!isOperator && <p className="mt-3 text-[10px] text-amber-300/90">Read-only session — running or deciding a review requires operator authorization.</p>}
    </div>
  );
}

// ── History (full-session search) ───────────────────────────────────────────

function History() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SessionSearchHit[]>([]);
  const [health, setHealth] = useState<SessionSearchHealth | null>(null);
  const [engine, setEngine] = useState<string>("");
  const [hasMore, setHasMore] = useState(false);
  const [open, setOpen] = useState<{ runId: string; messages: SessionSearchHit[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    sessionSearchHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  const run = async () => {
    if (!query.trim()) return;
    setBusy(true); setError(null);
    try {
      const result = await sessionSearch({ q: query, limit: 20 });
      setResults(result.results); setEngine(result.engine); setHasMore(result.hasMore);
    } catch (err) { setError(err instanceof Error ? err.message : "search failed"); }
    finally { setBusy(false); }
  };

  const openRun = async (runId: string) => {
    try {
      const window = await sessionOpen(runId);
      setOpen({ runId, messages: window.messages });
    } catch (err) { setToast(err instanceof Error ? err.message : "open failed"); setTimeout(() => setToast(null), 4000); }
  };

  return (
    <div className="animate-fade-in-up">
      <Header title="Session History" hint="Search what was discussed, decided, corrected or discovered in prior sessions. Historical content is CONTEXT — never current market evidence; re-retrieve current facts separately." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      <div className="rounded-2xl border border-white/10 glass-card p-4">
        <div className="flex gap-2">
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void run(); }}
            placeholder="Search prior sessions…" className="rounded-xl bg-background/60" />
          <Button size="sm" className="rounded-xl cursor-pointer" disabled={busy} onClick={run}>Search</Button>
        </div>
        {health && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            {health.indexed} message(s) indexed · FTS5: {health.fts5 ? "available" : "unavailable"} ·
            indexing: {health.indexingEnabled ? "on" : "off"} · retention {health.retentionDays}d
          </p>
        )}
      </div>

      {error && <ErrorBox message={error} />}

      {engine && (
        <p className="mt-3 text-[10px] text-muted-foreground">
          {results.length} result(s) via {engine}{hasMore ? " · more available" : ""}
        </p>
      )}

      <div className="mt-3 space-y-2">
        {results.map((hit) => (
          <div key={hit.messageId} className="rounded-2xl border border-white/10 glass-card p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="rounded-full border border-border/40 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{hit.role}/{hit.kind}</span>
                  <span className="text-[9px] text-muted-foreground">{hit.createdAt.slice(0, 10)}</span>
                  <span className="text-[9px] text-muted-foreground/70">run {hit.runId.slice(0, 14)}…</span>
                </div>
                <p className="mt-1 text-[12px] text-foreground/90">{hit.snippet}</p>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => openRun(hit.runId)}>Open</Button>
                <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300"
                  onClick={async () => {
                    try { await sessionDelete(hit.runId); setToast(`Removed index for ${hit.runId.slice(0, 12)}…`); setTimeout(() => setToast(null), 4000); }
                    catch (err) { setToast(err instanceof Error ? err.message : "delete failed"); setTimeout(() => setToast(null), 4000); }
                  }}>Forget</Button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setOpen(null)}>
          <div className="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-2xl border border-white/10 glass-card-strong p-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">Run {open.runId}</p>
              <button onClick={() => setOpen(null)} className="cursor-pointer text-muted-foreground hover:text-foreground"><X size={16} /></button>
            </div>
            <div className="mt-3 space-y-2">
              {open.messages.map((m) => (
                <div key={m.messageId} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{m.role}/{m.kind} · {m.createdAt}</p>
                  <p className="mt-1 text-[11px] text-foreground/90 whitespace-pre-wrap">{m.content ?? m.snippet}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <p className="mt-3 text-[10px] text-amber-300/90">Historical results are context only. They can never answer a current price/fundamental question — retrieve fresh data for that.</p>
    </div>
  );
}

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
                  {formatConfidence(memory.confidence)} · {memory.verification}
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
            {detail.explanation && (
              <div className="mt-3 rounded-2xl border border-white/10 glass-card-subtle p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Why this memory exists</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.saveReason}</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.recallDisposition}</p>
              </div>
            )}
            <dl className="mt-4 text-[11px]">
              <Meta label="Scope" value={`${detail.memory.scope}${detail.memory.scopeId ? `:${detail.memory.scopeId}` : ""}`} />
              <Meta label="Subject" value={detail.memory.subject ?? "—"} />
              <Meta label="Source" value={detail.memory.source ?? "—"} />
              <Meta label="Run" value={detail.memory.sourceRunId ?? "—"} />
              <Meta label="Confidence" value={formatConfidence(detail.memory.confidence)} />
              <Meta label="Verification" value={detail.memory.verification} />
              <Meta label="Authority" value={detail.memory.authority ?? "explicit"} />
              <Meta label="Accesses" value={String(detail.memory.accessCount)} />
              <Meta label="Last used" value={detail.memory.lastUsedAt ?? "never"} />
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
              {(detail.memory.status === "archived" || detail.memory.status === "expired" || detail.memory.status === "superseded") && (
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => restoreMemory(detail.memory.id), "Memory restored")}>
                  Restore
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

// ── Suggestions (inert Save/Dismiss proposals) ──────────────────────────────

function Suggestions({ isOperator }: { isOperator: boolean }) {
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSuggestions(await listSuggestions("pending")); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  return (
    <div className="animate-fade-in-up">
      <Header
        title="Memory Suggestions"
        hint="A suggestion is NOT memory: nothing is stored or recalled until you Save it. Dismissed suggestions are remembered so the same item is not offered again."
      />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      {loading ? <Spinner /> : error ? <ErrorBox message={error} /> : suggestions.length === 0 ? (
        <EmptyBox title="No pending suggestions" hint="Suggestions appear only when automatic suggestions are enabled and a casually-stated durable preference is detected." />
      ) : (
        <div className="space-y-2">
          {suggestions.map((s) => (
            <div key={s.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <TypeBadge type={s.memoryType} />
                    <span className="text-[9px] text-muted-foreground">{s.scope}{s.scopeId ? `:${s.scopeId}` : ""}</span>
                    <span className="text-[9px] text-muted-foreground">{s.createdAt.slice(0, 10)}</span>
                  </div>
                  <p className="mt-1 text-[12px] text-foreground/90">{s.content}</p>
                  {s.reason && <p className="mt-0.5 text-[10px] text-muted-foreground/80">{s.reason}</p>}
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                    onClick={() => act(() => acceptSuggestion(s.id), "Saved to memory")}>Save</Button>
                  <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                    onClick={() => act(() => dismissSuggestion(s.id), "Suggestion dismissed")}>Dismiss</Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {!isOperator && <p className="mt-3 text-[10px] text-amber-300/90">Read-only session — saving or dismissing requires operator authorization.</p>}
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
  semantic_indexing_enabled: "Allow optional local semantic indexing (not implemented)",
  capture_policy: "Per-category capture policy",
  recall_policy: "Per-category recall policy",
  semantic_conflict_enabled: "Local semantic contradiction candidates",
  semantic_conflict_threshold: "Semantic candidate threshold",
  semantic_conflict_max_candidates: "Max semantic candidates",
  semantic_conflict_max_index: "Max semantic index size",
  semantic_conflict_timeout_ms: "Semantic search timeout (ms)",
  semantic_conflict_diagnostics: "Show conflict detector metadata",
};

const LEARNING_MODE_OPTIONS: { value: string; label: string; hint: string }[] = [
  {
    value: "automatic_selective",
    label: "Automatic (selective)",
    hint: "Save strong, durable, low-risk facts automatically — no per-run prompt. Requires recurrence for project-specific claims.",
  },
  {
    value: "ask_before_saving",
    label: "Ask before saving",
    hint: "Stage candidates and request approval (an inert suggestion); never save on your behalf.",
  },
  {
    value: "off",
    label: "Off",
    hint: "Do not learn automatically. Explicit “remember/forget/correct” requests still work.",
  },
];

const LEARNING_MODE_KEYS = new Set(["memory_mode", "skill_learning_mode"]);

// Legacy derived booleans are read-only projections of the learning modes; they
// are not user-editable policy keys and must not render as controls.
const DERIVED_POLICY_KEYS = new Set([
  "auto_capture_enabled",
  "auto_suggest_enabled",
  "auto_candidate_detection",
]);

const POLICY_HINTS: Record<string, string> = {
  memory_mode: "How durable user preferences and project facts are learned.",
  skill_learning_mode: "How reusable procedures become learning candidates (always inert until reviewed).",
  memory_enabled: "Hard local off switch: when off, no memory is stored at all — not even an explicit “remember this”.",
  retention_days: "Days an automatically learned memory is kept before it becomes eligible for expiry review. 0 = never. Explicit memory is never auto-expired.",
  memory_in_diagnostics: "Whether memory content appears in the Lifecycle and explanation views. Off hides it without deleting anything.",
  semantic_indexing_enabled: "Reserved: optional local semantic indexing. Not implemented — semantic retrieval is deliberately deferred because the labeled evaluation showed no measured need. Turning this on changes nothing today and never enables a network service.",
  capture_policy: "Per-category capture rule. “deny” refuses a category; it can never widen authorization.",
  recall_policy: "Per-category recall rule. “deny” removes a category from recall; scope/privacy filtering stays authoritative.",
  semantic_conflict_enabled: "Off by default. When on, a local, bounded similarity check may surface a possible contradiction as an inert item for review. It never supersedes, activates, archives or deletes anything, and never bypasses scope, privacy or authority rules. Lexical detection stays active either way.",
  semantic_conflict_threshold: "Minimum similarity for a semantic candidate (0–1). Higher is more conservative.",
  semantic_conflict_max_candidates: "Maximum semantic candidates considered per write.",
  semantic_conflict_max_index: "Maximum same-dimension memories compared per write.",
  semantic_conflict_timeout_ms: "Wall-clock budget for one semantic search (ms). On timeout, detection falls back to lexical-only.",
  semantic_conflict_diagnostics: "Whether the detector used, similarity and candidate ids are shown in the Control Room. Never affects a decision.",
};

const CATEGORY_POLICY_KEYS = new Set(["capture_policy", "recall_policy"]);
const CATEGORY_POLICY_OPTIONS = ["", "allow", "suggest", "deny"] as const;

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
      {data.budget && !data.budget.unlimited && (
        <p className={cn("mb-3 text-[11px]", data.budget.full ? "text-amber-400" : "text-muted-foreground")}>
          {data.budget.full
            ? `Memory is full — ${data.budget.active}/${data.budget.limit} active. Archive or review memories to free space; existing memory is never deleted automatically.`
            : `Storage: ${data.budget.active}/${data.budget.limit} active memories (${data.budget.remaining} remaining).`}
        </p>
      )}
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      <div className="space-y-2">
        {Object.entries(draft).filter(([key]) => !DERIVED_POLICY_KEYS.has(key)).map(([key, value]) => {
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

// ── Health + Transfer ───────────────────────────────────────────────────────

function Health({ isOperator }: { isOperator: boolean }) {
  const [health, setHealth] = useState<EclipseMemoryHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dbHealth, setDbHealth] = useState<MemoryDatabaseHealth | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [filePreview, setFilePreview] = useState<Record<string, string> | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setHealth(await memoryHealth());
      setDbHealth(await memoryDatabaseHealth());
    }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { const result = await fn(); setToast(message); await load(); return result; }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  const downloadExport = async () => {
    setBusy(true);
    try {
      const payload = await exportMemory();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `eclipse-memory-export-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setToast(`Exported ${payload.counts.memories} memories`);
    } catch (err) { setToast(err instanceof Error ? err.message : "export failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!health) return null;

  return (
    <div className="animate-fade-in-up">
      <Header title="Database Health & Recovery" hint="eclipse-memory is a separate SQLite database with its own schema and migrations. Export, back up, import and reset are local operator actions." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      <div className="rounded-2xl border border-white/10 glass-card p-4">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", health.ok ? "bg-emerald-400" : "bg-rose-400")} />
          <span className="text-sm font-semibold text-foreground">{health.ok ? "Healthy" : "Unhealthy"}</span>
        </div>
        <dl className="mt-3 text-[11px]">
          <Meta label="Path" value={health.path} />
          <Meta label="Integrity" value={health.integrity ?? "—"} />
          <Meta label="Foreign-key violations" value={String(dbHealth?.foreignKeyViolations ?? "—")} />
          <Meta label="Free-page ratio" value={dbHealth?.freeRatio !== undefined ? String(dbHealth.freeRatio) : "—"} />
          <Meta label="Schema version" value={String(health.schemaVersion ?? "—")} />
          <Meta label="Up to date" value={health.upToDate ? "yes" : "no"} />
          <Meta label="Tables" value={String(health.tables ?? "—")} />
          {health.counts && Object.entries(health.counts).map(([k, v]) => <Meta key={k} label={k} value={String(v)} />)}
        </dl>
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
        <p className="text-[11px] font-semibold text-foreground">Markdown files</p>
        <p className="mt-1 text-[10px] text-muted-foreground">An inspectable projection under <code>.black-eclipse/memory/</code> (USER.md, MEMORY.md, PROFILE.md, README.md). SQLite stays the source of truth; export/import is explicit and every imported entry passes the normal safety gate.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const result = await getMemoryFiles();
                setFilePreview(result.files);
                setToast(`Files generated (${result.root})`);
              } catch (err) { setToast(err instanceof Error ? err.message : "generation failed"); }
              finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
            }}>Preview files</Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
            onClick={() => act(() => regenerateMemoryFiles(), "Files regenerated (backup taken)")}>
            Regenerate files
          </Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
            onClick={async () => {
              setBusy(true);
              try {
                const preview = await previewMarkdownImport();
                setFilePreview({ "IMPORT PREVIEW": `${preview.entries.length} entries, ${preview.ignored.length} ignored\n\n` + preview.entries.map((e) => `- [${e.memoryType}/${e.scope}] ${e.content}`).join("\n") });
                setToast("Import preview loaded");
              } catch (err) { setToast(err instanceof Error ? err.message : "preview failed"); }
              finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
            }}>Preview import</Button>
          <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
            onClick={() => act(() => importMarkdown(), "Imported from Markdown (backup taken)")}>
            Apply import
          </Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
            onClick={() => act(() => restoreMemoryFiles(), "Restored previous files")}>
            Restore previous
          </Button>
        </div>
        {filePreview && (
          <div className="mt-3 space-y-2">
            {Object.entries(filePreview).map(([name, content]) => (
              <details key={name} className="rounded-xl border border-border/20 bg-background/30 p-2">
                <summary className="cursor-pointer text-[11px] font-semibold text-foreground">{name}</summary>
                <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap text-[10px] text-foreground/80">{content}</pre>
              </details>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
        <p className="text-[11px] font-semibold text-foreground">Export & Backup</p>
        <p className="mt-1 text-[10px] text-muted-foreground">A readable JSON export you own, plus a consistent copy of the database file. Backups never overwrite an existing file.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={busy} onClick={downloadExport}>
            Download JSON export
          </Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
            onClick={() => act(() => backupMemory(), "Backup created")}>
            Back up database
          </Button>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 glass-card p-4">
        <p className="text-[11px] font-semibold text-foreground">Import</p>
        <p className="mt-1 text-[10px] text-muted-foreground">Records are validated and written through the normal memory pipeline; secrets and unsafe content are rejected with reasons.</p>
        <label className="mt-3 inline-flex">
          <input type="file" accept="application/json,.json" className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              try {
                const document = JSON.parse(await file.text()) as MemoryExportDocument;
                const result = await act(() => importMemory(document), "Import complete");
                if (result && typeof result === "object" && "rejected" in result) {
                  const rejected = (result as { rejected: unknown[] }).rejected;
                  if (rejected.length) setToast(`Import finished — ${rejected.length} record(s) rejected`);
                }
              } catch (err) {
                setToast(err instanceof Error ? err.message : "invalid file");
              }
            }}
          />
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer pointer-events-none" disabled={!isOperator || busy}>
            Import JSON file…
          </Button>
        </label>
      </div>

      <div className="mt-4 rounded-2xl border border-rose-400/20 glass-card p-4">
        <p className="text-[11px] font-semibold text-rose-300">Reset all memory</p>
        <p className="mt-1 text-[10px] text-muted-foreground">Deletes memory records, suggestions, corrections and audit events only. Skills, learning candidates and unrelated application data are never touched. A backup is taken first.</p>
        {confirmReset ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300" disabled={!isOperator || busy}
              onClick={async () => { await act(() => resetMemory(true), "Memory reset (backup taken)"); setConfirmReset(false); }}>
              Confirm reset
            </Button>
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => setConfirmReset(false)}>Cancel</Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="mt-3 rounded-xl cursor-pointer text-rose-300" disabled={!isOperator || busy}
            onClick={() => setConfirmReset(true)}>
            Reset memory…
          </Button>
        )}
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
