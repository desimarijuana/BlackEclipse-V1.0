"use client";

// ── Eclipse Memory — the Memory Control Room (Phase 3-M) ────────────────────
// Tabs: Overview · Memories · Corrections/Mistakes · Health. Reuses the Skills
// Control Room primitives (frosted glass, tab bar, badges) — no new visual
// language. All counts are real; no fabricated activity.

import { useCallback, useEffect, useState } from "react";
import {
  Activity, AlertCircle, Brain, Database, FileText, Lightbulb, Loader2, Lock, MessageSquare, Plug, Plus,
  RefreshCcw, Search, Settings2, ShieldCheck, Trash2, Wrench, X,
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
  memoryConflictReview, resolveMemoryConflict,
  listCompaction, detectCompaction, acceptCompaction, rejectCompaction,
  memoryProfile, rebuildProfile,
  sessionSearch, sessionSearchHealth, sessionOpen, sessionDelete,
  listChatSessions, getChatSession, updateChatSession, forkChatSession, deleteChatSession, exportChatSession, getSessionSummary,
  listProfiles, createProfile, deleteProfile,
  memoryProviderStatus, memoryProviderSearch, memoryProviderTest,
  learningReviewHealth, listLearningReviews, runLearningReview, decideLearningReview,
  getMemoryFiles, regenerateMemoryFiles, previewMarkdownImport, importMarkdown, restoreMemoryFiles,
  editMemoryFile, listFileHistory, rollbackMemoryFile, type FileEditOperation, type FileRevision,
} from "@/lib/harness/eclipse-memory-browser";
import { listSkills } from "@/lib/harness/skills-browser";
import type { SkillSummary } from "@/lib/harness/skills-types";
import {
  EmptyBox, ErrorBox, FilterRow, Header, MemoryModelLegend, Meta, Muted,
  OriginBadge, Section, Spinner, StatusPill, TypeBadge,
} from "./memory-ui";
import type {
  CorrectionRecord, EclipseMemoryHealth, MemoryDatabaseHealth, MemoryDetail,
  MemoryExportDocument, MemoryLifecycleView,
  MemoryLifecycleResponse, MemoryOverview,
  MemoryProfileResponse,
  MemoryRetentionStatus, MemorySemanticStatus,
  MemoryRecord, MemoryRetrievalDiagnostics, MistakeRecord, MemoryConflictReview, CompactionProposal,
  SessionSearchHealth, SessionSearchHit, SessionOpenResult,
  ChatSessionRecord, MemoryProfileRecord, MemoryProviderStatus,
  LearningReviewHealth, LearningReviewRecord,
} from "@/lib/harness/eclipse-memory-types";

type Tab = "overview" | "memories" | "profile" | "profiles" | "history" | "sessions" | "reviews" | "lifecycle" | "suggestions" | "activity" | "providers" | "files" | "skills" | "policies" | "health";

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
          { id: "memories", label: "Facts", icon: Database },
          { id: "sessions", label: "Session History", icon: MessageSquare },
          { id: "skills", label: "Skills", icon: Wrench },
          { id: "suggestions", label: "Suggestions", icon: Lightbulb },
          { id: "lifecycle", label: "Lifecycle", icon: RefreshCcw },
          { id: "reviews", label: "Reviews", icon: Activity },
          { id: "activity", label: "Activity", icon: Activity },
          { id: "profile", label: "Profile", icon: Lock },
          { id: "profiles", label: "Profiles", icon: ShieldCheck },
          { id: "providers", label: "Providers", icon: Plug },
          { id: "files", label: "Files", icon: FileText },
          { id: "policies", label: "Policies", icon: Settings2 },
          { id: "health", label: "Health/Export", icon: ShieldCheck },
        ]}
        activeId={tab}
        onChange={(id) => setTab(id as Tab)}
        variant="subtle"
      />
      {tab === "overview" && <Overview onNavigate={setTab} />}
      {tab === "memories" && <Memories isOperator={isOperator} />}
      {tab === "profile" && <Profile isOperator={isOperator} />}
      {tab === "profiles" && <Profiles isOperator={isOperator} />}
      {tab === "history" && <History />}
      {tab === "sessions" && <Sessions isOperator={isOperator} />}
      {tab === "reviews" && <Reviews isOperator={isOperator} />}
      {tab === "lifecycle" && <Lifecycle isOperator={isOperator} />}
      {tab === "suggestions" && <Suggestions isOperator={isOperator} />}
      {tab === "activity" && <ActivityView />}
      {tab === "providers" && <Providers />}
      {tab === "files" && <FilesTab isOperator={isOperator} />}
      {tab === "skills" && <SkillsTab />}
      {tab === "policies" && <Policies isOperator={isOperator} />}
      {tab === "health" && <Health isOperator={isOperator} />}
    </div>
  );
}

// ── Lifecycle (active / suggestions / expired / superseded / conflicts) ──────

const LIFECYCLE_VIEWS: Array<{ id: MemoryLifecycleView; label: string; hint: string }> = [
  { id: "active", label: "Active", hint: "Usable and eligible for recall." },
  { id: "stale", label: "Stale", hint: "Active but not confirmed/used in a long time — still recalled; review or renew." },
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
          {retention.nextMaintenanceAction && (
            <p className="mt-1 text-[10px] text-foreground/80">Next: {retention.nextMaintenanceAction}</p>
          )}
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

      <CompactionPanel isOperator={isOperator} onChanged={() => void load(view)} />

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

// ── Conservative compaction (near-duplicate proposals) ──────────────────────

function CompactionPanel({ isOperator, onChanged }: { isOperator: boolean; onChanged: () => void }) {
  const [proposals, setProposals] = useState<CompactionProposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setProposals(await listCompaction("proposed")); } catch { setProposals([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true); setToast(null);
    try { await fn(); setToast(message); await load(); onChanged(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  return (
    <div className="mb-4 rounded-2xl border border-white/10 glass-card p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-foreground">Memory compaction</p>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
          onClick={() => act(() => detectCompaction(), "Checked for near-duplicates")}>
          Find duplicates
        </Button>
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        Near-duplicate facts in the same scope/subject can be merged. Nothing changes until you accept a
        proposal; originals are superseded (retained) and the merge is reversible.
      </p>
      {toast && <p className="mt-1 text-[10px] text-primary">{toast}</p>}
      {proposals.length > 0 && (
        <div className="mt-2 space-y-2">
          {proposals.map((p) => (
            <div key={p.id} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
              <p className="text-[10px] text-muted-foreground">{p.scope}{p.scopeId ? `:${p.scopeId}` : ""} · {p.subject ?? "no subject"} · {p.memberIds.length} memories</p>
              <p className="mt-1 text-[11px] text-foreground">{p.mergedContent}</p>
              {p.rationale && <p className="mt-1 text-[10px] text-muted-foreground/80">{p.rationale}</p>}
              <div className="mt-2 flex gap-2">
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => acceptCompaction(p.id), "Merged")}>Accept merge</Button>
                <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => rejectCompaction(p.id), "Proposal dismissed")}>Dismiss</Button>
              </div>
            </div>
          ))}
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

function Overview({ onNavigate }: { onNavigate?: (tab: Tab) => void }) {
  const [data, setData] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<MemoryProviderStatus | null>(null);
  const [sessions, setSessions] = useState<ChatSessionRecord[]>([]);
  const [reviews, setReviews] = useState<LearningReviewRecord[]>([]);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await memoryOverview()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
    // Default-view extras — each is best-effort so one failure cannot blank the page.
    memoryProviderStatus().then(setProvider).catch(() => setProvider(null));
    listChatSessions({ limit: 5 }).then(setSessions).catch(() => setSessions([]));
    listLearningReviews(undefined, 5).then(setReviews).catch(() => setReviews([]));
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const pendingReviews = reviews.filter((r) => r.status === "queued" || r.status === "running");
  const rollbackAvailable = sessions.some((s) => s.sourceSessionId);

  const tiles = [
    { label: "Facts", value: data.memories.total, sub: `${Object.keys(data.memories.byType).length} types` },
    { label: "Active facts", value: data.memories.byStatus.active ?? 0, sub: "recallable now" },
    { label: "Skills", value: data.skills.installed, sub: "installed" },
    { label: "Pending reviews", value: pendingReviews.length, sub: "learning queue" },
    { label: "Recent sessions", value: sessions.length, sub: "session history" },
    { label: "Providers", value: provider?.available?.length ?? 0, sub: `of ${provider?.providerCount ?? 0} available` },
    { label: "Learning changes", value: data.candidates, sub: "candidates in queue" },
    { label: "Rollback availability", value: rollbackAvailable ? "yes" : "—", sub: rollbackAvailable ? "forked sessions" : "none" },
  ];

  return (
    <div className="animate-fade-in-up">
      <Header
        title="Eclipse Memory"
        hint="Dedicated persistence for agent memory, sessions, skills, learning and providers. Real counts only — nothing is fabricated."
      />
      <MemoryModelLegend />
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

// ── Sessions (named, with lifecycle + export/fork) ──────────────────────────

function Sessions({ isOperator }: { isOperator: boolean }) {
  const [sessions, setSessions] = useState<ChatSessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SessionSearchHit[]>([]);
  const [detail, setDetail] = useState<{ session: ChatSessionRecord; runs: string[]; summary: Record<string, unknown> | null; messages: SessionSearchHit[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSessions(await listChatSessions({ limit: 100 })); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const notify = (message: string) => { setToast(message); setTimeout(() => setToast(null), 4000); };

  const act = async (fn: () => Promise<unknown>, message: string) => {
    try { await fn(); notify(message); await load(); }
    catch (err) { notify(err instanceof Error ? err.message : "action failed"); }
  };

  const search = async () => {
    if (!query.trim()) return;
    try { setResults((await sessionSearch({ q: query, limit: 20 })).results); }
    catch (err) { notify(err instanceof Error ? err.message : "search failed"); }
  };

  const openDetail = async (session: ChatSessionRecord) => {
    try {
      const [full, summary, exported] = await Promise.all([
        getChatSession(session.id),
        getSessionSummary(session.id).catch(() => ({ summary: null })),
        exportChatSession(session.id).catch(() => ({ messages: [] as SessionSearchHit[] })),
      ]);
      setDetail({
        session: full.session,
        runs: full.runs,
        summary: (summary.summary as Record<string, unknown>) ?? full.session.summary,
        messages: exported.messages ?? [],
      });
    } catch (err) { notify(err instanceof Error ? err.message : "open failed"); }
  };

  return (
    <div className="animate-fade-in-up">
      <Header title="Sessions" hint="Long-lived named sessions. A run belongs to one session; a session belongs to one profile. Historical content is context, never current financial evidence." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      <div className="mb-3 flex gap-2">
        <Input value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void search(); }}
          placeholder="Search across all sessions…" className="rounded-xl bg-background/60" />
        <Button size="sm" className="rounded-xl cursor-pointer" onClick={search}>Search</Button>
      </div>
      {results.length > 0 && (
        <div className="mb-4 rounded-2xl border border-white/10 glass-card p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{results.length} result(s)</p>
            <button className="text-[10px] text-muted-foreground hover:text-foreground cursor-pointer" onClick={() => setResults([])}>Clear</button>
          </div>
          <div className="space-y-1.5">
            {results.map((hit) => (
              <p key={hit.messageId} className="text-[11px] text-foreground/90">
                <span className="text-muted-foreground">[{hit.role}/{hit.kind}]</span> {hit.snippet}
              </p>
            ))}
          </div>
        </div>
      )}
      {loading ? <Spinner /> : error ? <ErrorBox message={error} /> : (
        <div className="space-y-2">
          {sessions.length === 0 && <p className="text-[11px] text-muted-foreground">No sessions recorded yet.</p>}
          {sessions.map((session) => (
            <div key={session.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
              <div className="flex items-start justify-between gap-3">
                <button className="min-w-0 text-left cursor-pointer" onClick={() => void openDetail(session)}>
                  <p className="truncate text-[13px] font-medium text-foreground hover:text-primary">{session.title || session.id}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {session.status} · profile {session.profileId ?? "default"} · {session.lastActivityAt?.slice(0, 16) ?? session.createdAt.slice(0, 16)}
                    {session.sourceSessionId ? ` · forked from ${session.sourceSessionId.slice(0, 12)}…` : ""}
                  </p>
                </button>
                <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                  <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => void openDetail(session)}>Open</Button>
                  {isOperator && (
                    <>
                      <Button size="sm" variant="outline" className="rounded-xl cursor-pointer"
                        onClick={() => {
                          const title = window.prompt("Rename session", session.title ?? "");
                          if (title !== null) void act(() => updateChatSession(session.id, { title }), "Renamed");
                        }}>Rename</Button>
                      <Button size="sm" variant="outline" className="rounded-xl cursor-pointer"
                        onClick={() => void act(() => updateChatSession(session.id, { status: session.status === "archived" ? "active" : "archived", archivedAt: session.status === "archived" ? null : new Date().toISOString() }), "Updated")}>
                        {session.status === "archived" ? "Restore" : "Archive"}
                      </Button>
                      <Button size="sm" variant="outline" className="rounded-xl cursor-pointer"
                        onClick={() => void act(() => forkChatSession(session.id), "Forked")}>Fork</Button>
                      <Button size="sm" variant="outline" className="rounded-xl cursor-pointer"
                        onClick={async () => {
                          try {
                            const body = await exportChatSession(session.id);
                            const blob = new Blob([JSON.stringify(body, null, 2)], { type: "application/json" });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url; a.download = `${session.id}.json`; a.click();
                            URL.revokeObjectURL(url);
                          } catch (err) { notify(err instanceof Error ? err.message : "export failed"); }
                        }}>Export</Button>
                      <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300"
                        onClick={() => void act(() => deleteChatSession(session.id, true), "Deleted")}>Delete</Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setDetail(null)}>
          <div className="max-h-[85vh] w-full max-w-3xl overflow-auto rounded-2xl border border-white/10 glass-card-strong p-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">{detail.session.title || detail.session.id}</p>
              <button onClick={() => setDetail(null)} className="cursor-pointer text-muted-foreground hover:text-foreground"><X size={16} /></button>
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {detail.runs.length} run(s) · {detail.messages.length} indexed message(s) · profile {detail.session.profileId ?? "default"}
            </p>

            {detail.summary && (
              <div className="mt-3 rounded-xl border border-border/20 bg-background/30 p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Summary</p>
                {detail.summary.objective ? <p className="mt-1 text-[11px] text-foreground/90">Objective: {String(detail.summary.objective)}</p> : null}
                {Array.isArray(detail.summary.nextActions) && detail.summary.nextActions.length > 0 && (
                  <p className="mt-1 text-[11px] text-foreground/90">Next: {(detail.summary.nextActions as string[]).join("; ")}</p>
                )}
                {Array.isArray(detail.summary.instruments) && detail.summary.instruments.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {(detail.summary.instruments as string[]).map((t) => (
                      <span key={t} className="rounded-md border border-border/30 bg-accent/30 px-1.5 py-0.5 font-mono text-[9px] text-foreground">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="mt-3 space-y-1.5">
              {detail.messages.slice(0, 60).map((m) => (
                <div key={m.messageId} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{m.role}/{m.kind} · {m.createdAt?.slice(0, 16)}</p>
                  <p className="mt-1 text-[11px] text-foreground/90 whitespace-pre-wrap">{m.content ?? m.snippet}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Profiles (named + isolation + inheritance) ──────────────────────────────

function Profiles({ isOperator }: { isOperator: boolean }) {
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

function Providers() {
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

// ── Files (Markdown projection + edit history) ──────────────────────────────

// Client-safe parser for the visible entry markers (the server owns the
// authoritative parse; this only renders the preview). Matches memory-files.ts.
function parseClientEntries(text: string): Array<{ id: string | null; version: string | null; content: string }> {
  const marker = /<!--\s*eclipse:id=([^;\s]+);type=([^;\s]+);scope=([^;\s]+)(?:;version=([^;\s]+))?\s*-->/i;
  const lines = text.split(/\r?\n/);
  const entries: Array<{ id: string | null; version: string | null; content: string }> = [];
  for (let i = 0; i < lines.length; i += 1) {
    const m = /^\s*-\s+(.*\S)\s*$/.exec(lines[i]);
    if (!m) continue;
    const content = m[1];
    if (!content || content === "_None._" || content.startsWith("#")) continue;
    const found = marker.exec(lines[i + 1] ?? "");
    if (!found) continue;
    entries.push({ id: found[1], version: found[4] ?? null, content });
  }
  return entries;
}

function FilesTab({ isOperator }: { isOperator: boolean }) {
  const [files, setFiles] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ entries: number; ignored: number } | null>(null);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<FileRevision[]>([]);
  const [diff, setDiff] = useState<Array<{ type: "add" | "remove" | "same"; line: string }> | null>(null);
  const [editing, setEditing] = useState<{ memoryId: string; expectedVersion: string; content: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const body = await getMemoryFiles(); setFiles(body.files ?? {}); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const notify = (m: string) => { setToast(m); setTimeout(() => setToast(null), 4000); };

  const openHistory = async (file: string, revision?: string) => {
    setActiveFile(file); setDiff(null);
    try {
      const body = await listFileHistory(file, revision);
      setRevisions(body.revisions ?? []);
      if (body.diff) setDiff(body.diff);
    } catch (err) { notify(err instanceof Error ? err.message : "history failed"); }
  };

  const applyEdit = async (op: FileEditOperation, memoryId?: string, content?: string, expectedVersion?: string) => {
    if (!activeFile) return;
    try {
      const result = await editMemoryFile({ operation: op, file: activeFile, memoryId, content, expectedVersion });
      if (!result.ok) { notify(`Edit refused: ${result.error}`); return; }
      notify(`${op} applied — import to persist`);
      await load(); await openHistory(activeFile);
    } catch (err) { notify(err instanceof Error ? err.message : "edit failed"); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;

  const fileNames = Object.keys(files);
  const current = activeFile ? files[activeFile] ?? "" : "";
  const parsed = activeFile ? parseClientEntries(current) : [];

  return (
    <div className="animate-fade-in-up">
      <Header title="Memory Files" hint="A human-readable Markdown projection of structured memory. SQLite stays canonical; edits are atomic, versioned and reversible, then imported through the gated pipeline." />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}
      {isOperator && (
        <div className="mb-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={async () => {
            try { const r = await regenerateMemoryFiles(); notify(`Wrote ${r.files.length} file(s)`); await load(); }
            catch (err) { notify(err instanceof Error ? err.message : "regenerate failed"); }
          }}>Regenerate (atomic + backup)</Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={async () => {
            try { const p = await previewMarkdownImport(); setPreview({ entries: p.entries.length, ignored: p.ignored.length }); notify(`Preview: ${p.entries.length} entr(ies)`); }
            catch (err) { notify(err instanceof Error ? err.message : "preview failed"); }
          }}>Preview import</Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={async () => {
            try { const r = await importMarkdown(false); notify(`Imported ${r.imported}, skipped ${r.skipped}`); await load(); }
            catch (err) { notify(err instanceof Error ? err.message : "import failed"); }
          }}>Apply import</Button>
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={async () => {
            try { await restoreMemoryFiles(); notify("Restored previous files"); await load(); }
            catch (err) { notify(err instanceof Error ? err.message : "restore failed"); }
          }}>Restore backup</Button>
        </div>
      )}
      {preview && <p className="mb-3 text-[11px] text-muted-foreground">Preview: {preview.entries} importable entr(ies), {preview.ignored} ignored.</p>}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* File content */}
        <div className="space-y-3">
          {fileNames.map((name) => (
            <div key={name} className={cn("rounded-2xl border glass-card p-3", activeFile === name ? "border-primary/40" : "border-white/10")}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="font-mono text-[11px] font-semibold text-foreground">{name}</p>
                <button onClick={() => void openHistory(name)} className="text-[10px] text-primary hover:underline cursor-pointer">History &amp; edit</button>
              </div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[10px] text-muted-foreground">{files[name]}</pre>
            </div>
          ))}
        </div>

        {/* Detail / history / edit */}
        <div className="space-y-3">
          {!activeFile && (
            <div className="rounded-2xl border border-white/10 glass-card-subtle p-4 text-center">
              <FileText size={20} className="mx-auto text-muted-foreground/60" />
              <p className="mt-2 text-[11px] text-muted-foreground">Select “History &amp; edit” on a file to review revisions, diff a change and edit an entry.</p>
            </div>
          )}
          {activeFile && (
            <div className="rounded-2xl border border-white/10 glass-card p-3.5">
              <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Entries · {activeFile}</p>
              <div className="mt-2 max-h-60 space-y-1.5 overflow-auto">
                {parsed.length === 0 && <p className="text-[11px] text-muted-foreground">No marked entries.</p>}
                {parsed.map((entry, i) => (
                  <div key={`${entry.id}-${i}`} className="rounded-xl border border-border/20 bg-background/30 p-2">
                    <p className="text-[11px] text-foreground/90">{entry.content}</p>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <span className="font-mono text-[9px] text-muted-foreground">{entry.id ?? "(new)"} · {entry.version ?? "no version"}</span>
                      {isOperator && entry.id && (
                        <div className="flex gap-1.5">
                          <button className="text-[10px] text-primary hover:underline cursor-pointer"
                            onClick={() => { setEditing({ memoryId: entry.id!, expectedVersion: entry.version ?? "", content: entry.content }); }}>Edit</button>
                          <button className="text-[10px] text-rose-300 hover:underline cursor-pointer"
                            onClick={() => void applyEdit("replace", entry.id!, entry.content + " ", entry.version ?? undefined)}>Touch</button>
                        </div>
                      )}
                    </div>                  </div>
                ))}
              </div>

              {editing && (
                <div className="mt-3 rounded-xl border border-border/20 bg-background/30 p-2.5">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Edit {editing.memoryId} (v {editing.expectedVersion || "—"})</p>
                  <textarea value={editing.content} onChange={(e) => setEditing({ ...editing, content: e.target.value })}
                    className="mt-2 w-full rounded-lg border border-border/30 bg-background/60 p-2 text-[11px] text-foreground" rows={3} />
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" className="rounded-xl cursor-pointer"
                      onClick={async () => { await applyEdit("replace", editing.memoryId, editing.content, editing.expectedVersion); setEditing(null); }}>
                      Save (stale-safe)
                    </Button>
                    <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => setEditing(null)}>Cancel</Button>
                  </div>
                  <p className="mt-1 text-[9px] text-muted-foreground">Rejected if the entry changed since it was loaded (expectedVersion guard).</p>
                </div>
              )}

              <div className="mt-3 border-t border-border/20 pt-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Revision history ({revisions.length})</p>
                  {isOperator && revisions.length > 0 && (
                    <button className="text-[10px] text-primary hover:underline cursor-pointer"
                      onClick={async () => {
                        try { await rollbackMemoryFile(activeFile, revisions[revisions.length - 1].revision); notify("Rolled back"); await load(); await openHistory(activeFile); }
                        catch (err) { notify(err instanceof Error ? err.message : "rollback failed"); }
                      }}>Roll back latest</button>
                  )}
                </div>
                <div className="mt-1.5 space-y-1">
                  {revisions.length === 0 && <p className="text-[11px] text-muted-foreground">No revisions recorded.</p>}
                  {revisions.map((rev) => (
                    <button key={rev.revision} onClick={() => void openHistory(activeFile, rev.revision)}
                      className="block w-full rounded-lg border border-border/20 bg-background/20 px-2 py-1 text-left text-[10px] hover:bg-accent/20 cursor-pointer">
                      <span className="text-foreground/90">{rev.reason}</span>
                      <span className="text-muted-foreground"> · {rev.actor} · {rev.at.slice(0, 16)}</span>
                    </button>
                  ))}
                </div>
                {diff && (
                  <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-border/20 bg-background/30 p-2 font-mono text-[10px]">
                    {diff.map((line, i) => (
                      <p key={i} className={cn(line.type === "add" ? "text-emerald-300" : line.type === "remove" ? "text-rose-300" : "text-muted-foreground")}>
                        {line.type === "add" ? "+ " : line.type === "remove" ? "- " : "  "}{line.line}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Skills (read-only index; full lifecycle lives in the Skills Control Room) ─

function SkillsTab() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills()
      .then((body) => setSkills(body.skills ?? []))
      .catch((err) => setError(err instanceof Error ? err.message : "failed"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  return (
    <div className="animate-fade-in-up">
      <Header title="Skills" hint="The installed skill index. Versioned patches, evaluation, canary and rollback live in the Skills Control Room." />
      {skills.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">No skills installed.</p>
      ) : (
        <div className="space-y-2">
          {skills.map((skill) => (
            <div key={skill.id} className="rounded-2xl border border-white/10 glass-card p-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-medium text-foreground">{skill.name}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{skill.id}</span>
                <span className="rounded-full border border-border/40 px-2 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">{skill.status}</span>
                {skill.version && <span className="text-[10px] text-muted-foreground">v{skill.version}</span>}
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">{skill.description}</p>
            </div>
          ))}
        </div>
      )}
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
  const [conflictId, setConflictId] = useState<string | null>(null);
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
          title="Facts"
          hint="Durable, declarative facts recalled on relevant turns. A proposed fact is inert until you approve it; archived and superseded facts are retained for audit, never deleted. Task procedures belong in Skills; old conversations belong in Session History."
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
                    <OriginBadge memory={memory} />
                    <span className="text-[9px] text-muted-foreground">scope: {memory.scope}{memory.scopeId ? `:${memory.scopeId}` : ""}</span>
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
              <OriginBadge memory={detail.memory} />
            </div>
            <p className="mt-3 text-[12px] text-foreground leading-relaxed">{detail.memory.content}</p>
            {detail.explanation && (
              <div className="mt-3 rounded-2xl border border-white/10 glass-card-subtle p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Why this memory exists</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.saveReason}</p>
                <p className="mt-1 text-[11px] text-foreground/90">{detail.explanation.recallDisposition}</p>
                {detail.explanation.statusReason && (
                  <p className="mt-1 text-[11px] text-amber-300/90">
                    Status: {detail.memory.status} — {detail.explanation.statusReason}
                  </p>
                )}
                {detail.memory.expiresAt && detail.memory.status === "expired" && (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Expired {detail.memory.expiresAt}: automatic memories retire after the retention window; explicit memories never expire silently.
                  </p>
                )}
                {detail.memory.supersededBy && (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Superseded by a later record ({detail.memory.supersededBy}) and excluded from recall; retained for audit.
                  </p>
                )}
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
              <Meta label="Last confirmed" value={detail.memory.lastConfirmedAt ?? "—"} />
              <Meta label="Expires" value={detail.memory.expiresAt ?? "never"} />
              <Meta label="Created" value={detail.memory.createdAt} />
            </dl>
            {detail.explanation?.conflict && (
              <div className="mt-3 rounded-2xl border border-amber-400/25 bg-amber-400/5 p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-amber-300">Competing memory</p>
                <p className="mt-1 text-[11px] text-foreground/90">
                  {detail.explanation.conflict.reason}
                </p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Detector: {detail.explanation.conflict.detector}
                  {detail.explanation.conflict.similarity != null ? ` · similarity ${detail.explanation.conflict.similarity.toFixed(2)}` : ""}
                  {detail.explanation.conflict.requiresConfirmation ? " · needs your review" : ""}
                </p>
                <Button size="sm" variant="outline" className="mt-2 rounded-xl cursor-pointer"
                  onClick={() => setConflictId(detail.memory.id)}>
                  Review conflict
                </Button>
              </div>
            )}

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

      {conflictId && (
        <ConflictReview
          memoryId={conflictId}
          isOperator={isOperator}
          onClose={() => setConflictId(null)}
          onResolved={async (message) => {
            setToast(message);
            await load();
            if (detail) await open(detail.memory.id);
          }}
        />
      )}
    </div>
  );
}

// ── Conflict review (side-by-side competing memories + safe actions) ────────

function ConflictReview({
  memoryId, isOperator, onClose, onResolved,
}: {
  memoryId: string;
  isOperator: boolean;
  onClose: () => void;
  onResolved: (message: string) => void | Promise<void>;
}) {
  const [review, setReview] = useState<MemoryConflictReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [mergeText, setMergeText] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    memoryConflictReview(memoryId).then((r) => { if (!cancelled) { setReview(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [memoryId]);

  const act = async (action: string, targetId?: string, mergedContent?: string) => {
    setBusy(true); setMessage(null);
    try {
      const result = await resolveMemoryConflict(memoryId, action, { targetId, mergedContent, reason: "resolved in conflict review" });
      if (!result.ok) { setMessage(result.error ?? "action failed"); return; }
      await onResolved(`Conflict ${action} recorded`);
      onClose();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "action failed");
    } finally { setBusy(false); }
  };

  const Row = ({ record, label }: { record: MemoryConflictReview["self"]; label: string }) => (
    <div className="rounded-2xl border border-white/10 glass-card-subtle p-3">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[9px] font-bold uppercase tracking-wide text-primary">{label}</span>
        <TypeBadge type={record.memoryType} />
        <StatusPill status={record.status} />
        <span className="text-[9px] text-muted-foreground">{record.authority}</span>
      </div>
      <p className="mt-1.5 text-[12px] text-foreground leading-relaxed">{record.content}</p>
      <p className="mt-1 text-[10px] text-muted-foreground">
        {record.scope}{record.scopeId ? `:${record.scopeId}` : ""} · {record.provenance ?? "—"} ·
        conf {formatConfidence(record.confidence)} · confirmed {record.lastConfirmedAt ?? "—"} ·
        used {record.accessCount ?? 0}×
      </p>
      {record.status === "active" && record.id !== memoryId && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button onClick={() => act("supersede", record.id)} disabled={!isOperator || busy}
            className="rounded-lg border border-border/40 px-2 py-0.5 text-[10px] cursor-pointer disabled:opacity-50">Supersede</button>
          <button onClick={() => act("dismiss", record.id)} disabled={!isOperator || busy}
            className="rounded-lg border border-border/40 px-2 py-0.5 text-[10px] cursor-pointer text-rose-300 disabled:opacity-50">Dismiss</button>
          <button onClick={() => act("confirm_both", record.id)} disabled={!isOperator || busy}
            className="rounded-lg border border-border/40 px-2 py-0.5 text-[10px] cursor-pointer text-emerald-300 disabled:opacity-50">Confirm both</button>
          <button onClick={() => { setMergeText(record.content); }} disabled={!isOperator || busy}
            className="rounded-lg border border-border/40 px-2 py-0.5 text-[10px] cursor-pointer disabled:opacity-50">Merge…</button>
        </div>
      )}
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full glass-card-strong border-l border-white/10 overflow-y-auto p-5">
        <button onClick={onClose} className="mb-3 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">← Close</button>
        <h3 className="font-serif text-sm font-semibold text-foreground">Conflict review</h3>
        {loading ? <Spinner /> : !review ? (
          <p className="mt-2 text-[11px] text-muted-foreground">No conflict review available for this memory.</p>
        ) : (
          <>
            <p className="mt-1 text-[11px] text-muted-foreground">{review.recommendation}</p>
            {message && <p className="mt-2 text-[11px] text-rose-300">{message}</p>}
            <div className="mt-3 space-y-2">
              <Row record={review.self} label="This memory" />
              {review.peers.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">No competing record is linked.</p>
              ) : review.peers.map((peer) => <Row key={peer.id} record={peer} label="Competing" />)}
            </div>
            {mergeText && (
              <div className="mt-3 rounded-2xl border border-primary/20 glass-card p-3">
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Merge into a new fact</p>
                <textarea value={mergeText} onChange={(e) => setMergeText(e.target.value)} rows={3}
                  className="mt-1 w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40" />
                <div className="mt-2 flex gap-2">
                  <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                    onClick={() => act("merge", review.peers.find((p) => p.status === "active")?.id ?? review.peers[0]?.id, mergeText)}>
                    Create merged fact
                  </Button>
                  <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => setMergeText("")}>Cancel</Button>
                </div>
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                onClick={() => act("keep")}>Keep as-is</Button>
              <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                onClick={() => act("defer")}>Defer review</Button>
            </div>
            <p className="mt-3 text-[10px] text-muted-foreground">
              Every action is audited and reversible; no record is hard-deleted. Semantic
              similarity never resolves a conflict automatically.
            </p>
          </>
        )}
      </div>
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
  const [pendingImport, setPendingImport] = useState<MemoryExportDocument | null>(null);
  const [importPreview, setImportPreview] = useState<{
    imported?: number; importable?: number; skipped?: number;
    rejected?: unknown[]; checksumOk?: boolean | null;
  } | null>(null);

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
                setPendingImport(document);
                setImportPreview(null);
              } catch (err) {
                setToast(err instanceof Error ? err.message : "invalid file");
              }
            }}
          />
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer pointer-events-none" disabled={!isOperator || busy}>
            Choose JSON file…
          </Button>
        </label>
        {pendingImport && (
          <div className="mt-3 rounded-xl border border-primary/20 glass-card-subtle p-2.5">
            <p className="text-[10px] text-muted-foreground">Selected file — preview before applying (dry run validates and counts, writes nothing).</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                onClick={async () => {
                  try {
                    const report = await importMemory(pendingImport, true);
                    setImportPreview(report);
                  } catch (err) { setToast(err instanceof Error ? err.message : "preview failed"); }
                }}>
                Preview (dry run)
              </Button>
              <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                onClick={async () => {
                  const result = await act(() => importMemory(pendingImport), "Import complete");
                  if (result && typeof result === "object" && "rejected" in result) {
                    const rejected = (result as { rejected: unknown[] }).rejected;
                    if (rejected.length) setToast(`Import finished — ${rejected.length} record(s) rejected`);
                  }
                  setPendingImport(null); setImportPreview(null);
                }}>
                Apply import
              </Button>
              <Button size="sm" variant="ghost" className="rounded-xl cursor-pointer" onClick={() => { setPendingImport(null); setImportPreview(null); }}>
                Cancel
              </Button>
            </div>
            {importPreview && (
              <p className="mt-2 text-[10px] text-foreground/80">
                Would import {importPreview.importable ?? importPreview.imported ?? 0}
                {(importPreview.skipped ?? 0) > 0 ? `, skip ${importPreview.skipped} duplicate(s)` : ""}
                {(importPreview.rejected?.length ?? 0) > 0 ? `, reject ${importPreview.rejected?.length}` : ""}
                {importPreview.checksumOk === false ? " · checksum mismatch" : importPreview.checksumOk ? " · checksum ok" : ""}
              </p>
            )}
          </div>
        )}
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
