"use client";

// ── Skill Control Room — the Phase-3 screen ─────────────────────────────────
// Tabs come from SKILLS_TABS (src/lib/app-screens.ts) — the same list the
// agent's surface map reads. Skill Detail and Draft Review are drill-down
// views inside the Library tab. All data comes from the Python runtime through
// the front door; every mutating action is re-checked server-side.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Boxes, FlaskConical, FolderGit2, GitBranch, GraduationCap, Library, Lightbulb, Sparkles, Wrench, type LucideIcon } from "@/lib/icons";
import {
  SKILLS_GROUPS, SKILLS_TABS, screenGroupForTab, screenTab, visibleGroupTabs,
  type SkillsTabId,
} from "@/lib/app-screens";
import { TabBar } from "@/components/ui/tab-bar";
import { useSubroute } from "@/hooks/use-subroute";
import { destinationToQuery } from "@/lib/search/deep-link";
import { libraryViewQuery, parseLibraryView } from "@/lib/skills/library-view";
import {
  listSkills, getSkill, listCandidates, generateDraft, rejectCandidate,
  listSkillExecutions, learnFromRun, evaluateSkill, setSkillLifecycle,
  executeSkill, approveDraft, rejectDraft, submitDraftReview, deleteUserSkill,
} from "@/lib/harness/skills-browser";
import type {
  LearningCandidate, SkillDetail, SkillExecutionRecord, SkillSummary,
} from "@/lib/harness/skills-types";
import { SkillLibrary } from "./skill-library";
import { SkillDetailPanel } from "./skill-detail";
import { LearningQueue } from "./learning-queue";
import { EvaluationCenter } from "./evaluation-center";
import { ExecutionActivity, type ExecutionWithSkill } from "./execution-activity";
import { DraftReview } from "./draft-review";
import { SkillAuthorForm } from "./skill-author-form";
import { ProjectSkills } from "./project-skills";
import { SkillBundles } from "./skill-bundles";
import { GuidedLearn } from "./guided-learn";
import { LearningJourneyPanel } from "./learning-journey";
import { OnboardingPanel } from "./onboarding";
import { SkillMaintenancePanel } from "./skill-maintenance";
import { RslExperimentsPanel } from "./rsl-experiments-panel";

type Tab = SkillsTabId;

// Labels + ids come from `SKILLS_TABS`/`SKILLS_GROUPS` (the same list the
// agent's surface map reads); only the icons/badges are screen-local
// presentation.
const TAB_ICONS: Record<Tab, LucideIcon> = {
  library: Library, start: Sparkles, project: FolderGit2, bundles: Boxes,
  learn: GraduationCap, learning: Lightbulb, journey: GitBranch, maintenance: Wrench,
  evaluation: FlaskConical, activity: Activity, experiments: FlaskConical,
};

const GROUP_ICONS: Record<string, LucideIcon> = {
  library: Library,
  learning: GraduationCap,
  journey: GitBranch,
  collections: Boxes,
  operations: Activity,
};

/** Replace the URL without adding a history entry. */
function replaceSkillsUrl(search: string) {
  if (typeof window === "undefined") return;
  const href = `${window.location.pathname}?${search}`;
  if (`${window.location.pathname}${window.location.search}` !== href) {
    window.history.replaceState(null, "", href);
  }
}

/** Push a URL so browser Back closes the drill-down. */
function pushSkillsUrl(search: string) {
  if (typeof window === "undefined") return;
  const href = `${window.location.pathname}?${search}`;
  if (`${window.location.pathname}${window.location.search}` !== href) {
    window.history.pushState(null, "", href);
  }
}

function currentLibraryView() {
  return parseLibraryView(typeof window === "undefined" ? "" : window.location.search);
}

export function SkillsScreen({ isOperator = false }: { isOperator?: boolean }) {
  const [tab, setTab] = useState<Tab>("library");
  /** Run opened from a deep link or the Learning Queue's "View run". */
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [duplicates, setDuplicates] = useState<string[]>([]);
  const [projectNotices, setProjectNotices] = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<LearningCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);

  const [executions, setExecutions] = useState<ExecutionWithSkill[]>([]);
  const [executionsLoading, setExecutionsLoading] = useState(false);
  const [executionsError, setExecutionsError] = useState<string | null>(null);

  const [toast, setToast] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  // Authoring: null = closed; "new" = create; a SkillDetail = edit that skill.
  const [authoring, setAuthoring] = useState<"new" | SkillDetail | null>(null);

  const flash = useCallback((tone: "ok" | "error", text: string) => {
    setToast({ tone, text });
    setTimeout(() => setToast(null), 5000);
  }, []);

  const loadSkills = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listSkills();
      setSkills(data.skills);
      setLoadErrors(data.loadErrors);
      setDuplicates(data.duplicates);
      setProjectNotices(data.projectNotices ?? []);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "failed to load skills");
    } finally {
      setListLoading(false);
    }
  }, []);

  // `push` is only set for a deliberate drill-down from the Library. Refresh
  // calls (after run/evaluate/lifecycle) must not add history entries.
  const openSkill = useCallback(async (skillId: string, opts?: { push?: boolean }) => {
    setTab("library");
    setDetailLoading(true);
    setDetailError(null);
    try {
      const skill = await getSkill(skillId);
      if (!skill) throw new Error("Skill not found");
      setDetail(skill);
      if (opts?.push) {
        pushSkillsUrl(libraryViewQuery(currentLibraryView(), {
          subroute: "skills.detail",
          focus: skillId,
        }));
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "failed to load skill");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openSkillFromLibrary = useCallback(
    (skillId: string) => { void openSkill(skillId, { push: true }); },
    [openSkill],
  );

  const closeDetail = useCallback(() => {
    setDetail(null);
    replaceSkillsUrl(libraryViewQuery(currentLibraryView(), { subroute: "skills.library" }));
    void loadSkills();
  }, [loadSkills]);

  const changeTab = useCallback((id: Tab) => {
    setDetail(null);
    setFocusedRunId(null);
    setTab(id);
    replaceSkillsUrl(
      id === "library"
        ? libraryViewQuery(currentLibraryView(), { subroute: "skills.library" })
        : destinationToQuery({ tab: "skills", subroute: `skills.${id}` }),
    );
  }, []);

  // "View run" from the Learning Queue: open the run inside Activity and push
  // a URL so Back returns to where the user came from.
  const openRun = useCallback((runId: string) => {
    setDetail(null);
    setTab("activity");
    setFocusedRunId(runId);
    pushSkillsUrl(destinationToQuery({
      tab: "skills",
      subroute: "skills.activity",
      params: { focus: runId },
    }));
  }, []);

  const clearRunFocus = useCallback(() => {
    setFocusedRunId(null);
    replaceSkillsUrl(destinationToQuery({ tab: "skills", subroute: "skills.activity" }));
  }, []);

  // Deep links land on the matching sub-tab. `detail` is not a tab: it is the
  // drill-down inside Library, carrying the skill id in `focus`.
  useSubroute("skills", (req) => {
    if (req.subroute === "detail") {
      setTab("library");
      if (req.focus) void openSkill(req.focus);
      else setDetail(null);
      return;
    }
    const def = screenTab(SKILLS_TABS, req.subroute);
    if (def) {
      setTab(def.id);
      setDetail(null);
      setFocusedRunId(def.id === "activity" ? (req.focus ?? null) : null);
    }
  });

  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    setCandidatesError(null);
    try {
      setCandidates(await listCandidates());
    } catch (err) {
      setCandidatesError(err instanceof Error ? err.message : "failed to load candidates");
    } finally {
      setCandidatesLoading(false);
    }
  }, []);

  const loadExecutions = useCallback(async () => {
    setExecutionsLoading(true);
    setExecutionsError(null);
    try {
      const records = await listSkillExecutions();
      const nameById = new Map(skills.map((s) => [s.id, s.name]));
      setExecutions(records.map((record) => ({ ...record, skillName: nameById.get(record.skillId) })));
    } catch (err) {
      setExecutionsError(err instanceof Error ? err.message : "failed to load executions");
    } finally {
      setExecutionsLoading(false);
    }
  }, [skills]);

  useEffect(() => { void loadSkills(); }, [loadSkills]);
  // Candidates load once on mount so the Learning badge is accurate before the
  // tab is ever opened.
  useEffect(() => { void loadCandidates(); }, [loadCandidates]);
  useEffect(() => {
    if (tab === "learning") void loadCandidates();
    if (tab === "activity") void loadExecutions();
  }, [tab, loadCandidates, loadExecutions]);

  const handleRun = useCallback(async (skillId: string, input: Record<string, unknown>, mode: string) => {
    flash("ok", "Skill run started…");
    try {
      const result = await executeSkill({
        skillId,
        input,
        executionMode: mode as SkillExecutionRecord["executionMode"],
      });
      if (result.status === "completed") {
        flash("ok", `Skill completed (${result.metrics.durationMs ?? "?"}ms)${result.outputValidated ? " · output validated" : " · output not schema-validated"}`);
      } else {
        flash("error", `Skill ${result.status}: ${result.error?.message ?? "unknown"}`);
      }
      await openSkill(skillId);
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "execution failed");
    }
  }, [flash, openSkill]);

  const handleEvaluate = useCallback(async (skillId: string, version: string) => {
    flash("ok", "Running evaluation…");
    try {
      const result = await evaluateSkill(skillId, version);
      flash(result.status === "passed" ? "ok" : "error", `Evaluation: ${result.status}`);
      await openSkill(skillId);
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "evaluation failed");
    }
  }, [flash, openSkill]);

  const handleLifecycle = useCallback(async (skillId: string, action: "enable" | "disable" | "deprecate" | "rollback", version?: string) => {
    try {
      const payload =
        action === "deprecate" ? { reason: "Deprecated from the UI" }
        : action === "rollback" ? { version: version ?? "", reason: "Rollback from the UI" }
        : { version };
      const result = await setSkillLifecycle(skillId, action, payload);
      flash(result.success ? "ok" : "error", result.success ? `${skillId} ${action}d` : (result.error ?? `${action} failed`));
      await openSkill(skillId);
    } catch (err) {
      flash("error", err instanceof Error ? err.message : `${action} failed`);
    }
  }, [flash, openSkill]);

  // Bulk enable/disable: the server still owns every transition, so a partial
  // failure is reported honestly instead of being hidden behind one toast.
  const handleBulkLifecycle = useCallback(async (ids: string[], action: "enable" | "disable") => {
    if (ids.length === 0) return;
    let ok = 0;
    let failed = 0;
    const batchSize = 5;
    for (let i = 0; i < ids.length; i += batchSize) {
      const batch = ids.slice(i, i + batchSize);
      const results = await Promise.allSettled(
        batch.map(async (id) => {
          const result = await setSkillLifecycle(id, action, {});
          if (!result.success) throw new Error(result.error ?? `${action} failed`);
          return id;
        }),
      );
      for (const result of results) {
        if (result.status === "fulfilled") ok += 1;
        else failed += 1;
      }
    }
    flash(
      failed > 0 ? "error" : "ok",
      `${ok} skill(s) ${action}d${failed > 0 ? ` · ${failed} failed` : ""}`,
    );
    await loadSkills();
  }, [flash, loadSkills]);

  const handleGenerateDraft = useCallback(async (candidateId: string) => {
    try {
      const result = await generateDraft(candidateId);
      const message = result.ok
        ? result.reusable === false
          ? "Draft generated (inactive) — insufficient evidence for a reusable procedure; manual authoring required"
          : "Draft generated (inactive)"
        : (result.error ?? "draft failed");
      flash(result.ok ? "ok" : "error", message);
      await loadCandidates();
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "draft failed");
    }
  }, [flash, loadCandidates]);

  const handleRejectCandidate = useCallback(async (candidateId: string) => {
    try {
      const result = await rejectCandidate(candidateId);
      flash(result.ok ? "ok" : "error", result.ok ? "Candidate rejected" : (result.error ?? "reject failed"));
      await loadCandidates();
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "reject failed");
    }
  }, [flash, loadCandidates]);

  const handleSubmitReview = useCallback(async (skillId: string) => {
    try {
      const result = await submitDraftReview(skillId, "Submitted from the Skills UI");
      flash(result.success ? "ok" : "error", result.success ? "Submitted for review" : (result.error ?? "submit failed"));
      await openSkill(skillId);
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "submit failed");
    }
  }, [flash, openSkill]);

  const handleApproveDraft = useCallback(async (skillId: string, requestId: string) => {
    try {
      const result = await approveDraft(skillId, requestId);
      flash(result.success ? "ok" : "error", result.success ? "Draft approved and enabled" : (result.error ?? "approve failed"));
      await openSkill(skillId);
      await loadSkills();
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "approve failed");
    }
  }, [flash, openSkill, loadSkills]);

  const handleRejectDraft = useCallback(async (skillId: string, requestId: string) => {
    try {
      const result = await rejectDraft(skillId, requestId, "Rejected from the Skills UI");
      flash(result.success ? "ok" : "error", result.success ? "Draft rejected" : (result.error ?? "reject failed"));
      await openSkill(skillId);
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "reject failed");
    }
  }, [flash, openSkill]);

  const handleLearn = useCallback(async (runId: string) => {
    try {
      const result = await learnFromRun(runId);
      if (result.ok && result.created.length > 0) flash("ok", `Captured ${result.created.length} learning candidate(s)`);
      else if (result.ok) flash("ok", "No new reusable lesson detected for this run");
      else flash("error", result.error ?? "learning failed");
      await loadCandidates();
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "learning failed");
    }
  }, [flash, loadCandidates]);

  const handleDeleteSkill = useCallback(async (skillId: string) => {
    try {
      const result = await deleteUserSkill(skillId);
      if (result.deleted) {
        flash("ok", `${skillId} deleted`);
      } else {
        flash("ok", result.reason ?? `${skillId} deprecated (retained for history)`);
      }
      setDetail(null);
      await loadSkills();
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "delete failed");
    }
  }, [flash, loadSkills]);

  const activeGroup = screenGroupForTab(SKILLS_GROUPS, tab);
  const subTabs = visibleGroupTabs(activeGroup, SKILLS_TABS);

  const primaryTabs = useMemo(() => SKILLS_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    icon: GROUP_ICONS[group.id],
    badge:
      group.id === "learning" && candidates.length > 0
        ? <Badge>{candidates.length}</Badge>
        : undefined,
  })), [candidates.length]);

  const secondaryTabs = useMemo(() => subTabs.map((def) => ({
    id: def.id,
    label: def.label,
    icon: TAB_ICONS[def.id],
    badge: def.id === "learning" && candidates.length > 0 ? <Badge>{candidates.length}</Badge> : undefined,
  })), [subTabs, candidates.length]);

  return (
    // Full-width screen container matching the app convention (`w-full`,
    // `px-4 md:px-8`); `#main-content` owns the scroll. `pb-24` keeps the last
    // row clear of the floating chat dock at the bottom.
    <div className="w-full px-4 py-6 md:px-8 pb-24">
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className={`fixed bottom-6 right-6 z-[110] rounded-xl border px-4 py-3 text-xs font-semibold shadow-lg glass-card-strong ${
            toast.tone === "ok" ? "border-emerald-400/30 text-emerald-200" : "border-rose-400/30 text-rose-200"
          }`}
        >
          {toast.text}
        </div>
      )}

      <TabBar
        items={primaryTabs}
        activeId={activeGroup.id}
        onChange={(groupId) => {
          const next = SKILLS_GROUPS.find((group) => group.id === groupId);
          const first = next ? visibleGroupTabs(next, SKILLS_TABS)[0] : undefined;
          if (first) changeTab(first.id);
        }}
        variant="subtle"
        wrap
      />
      {subTabs.length > 1 && (
        <TabBar
          items={secondaryTabs}
          activeId={tab}
          onChange={(id) => changeTab(id as Tab)}
          variant="subtle"
          wrap
          className="mb-5"
        />
      )}

      {detail ? (
        <>
          {detail.origin === "learning" && detail.storedStatus === "draft" && !detailLoading && (
            <DraftReview
              skill={detail}
              isOperator={isOperator}
              onEvaluate={handleEvaluate}
              onSubmitReview={handleSubmitReview}
              onApprove={handleApproveDraft}
              onReject={handleRejectDraft}
            />
          )}
          <SkillDetailPanel
            skill={detail}
            loading={detailLoading}
            error={detailError}
            isOperator={isOperator}
            onBack={closeDetail}
            onRun={handleRun}
            onEvaluate={handleEvaluate}
            onLifecycle={handleLifecycle}
            onEdit={(skill) => setAuthoring(skill)}
            onDelete={handleDeleteSkill}
          />
        </>
      ) : (
        <>
          {tab === "library" && (
            <SkillLibrary
              skills={skills}
              loading={listLoading}
              error={listError}
              loadErrors={loadErrors}
              duplicates={duplicates}
              projectNotices={projectNotices}
              isOperator={isOperator}
              onOpen={openSkillFromLibrary}
              onRefresh={loadSkills}
              onAdd={() => setAuthoring("new")}
              onStartHere={() => changeTab("start")}
              onBulkLifecycle={handleBulkLifecycle}
            />
          )}
          {tab === "start" && <OnboardingPanel onClose={() => changeTab("library")} />}
          {tab === "project" && <ProjectSkills isOperator={isOperator} />}
          {tab === "bundles" && <SkillBundles isOperator={isOperator} />}
          {tab === "learn" && <GuidedLearn isOperator={isOperator} onOpenDraft={openSkillFromLibrary} />}
          {tab === "journey" && <LearningJourneyPanel />}
          {tab === "maintenance" && <SkillMaintenancePanel isOperator={isOperator} />}
          {tab === "experiments" && <RslExperimentsPanel />}
          {tab === "learning" && (
            <LearningQueue
              candidates={candidates}
              loading={candidatesLoading}
              error={candidatesError}
              isOperator={isOperator}
              onRefresh={loadCandidates}
              onGenerateDraft={handleGenerateDraft}
              onReject={handleRejectCandidate}
              onOpenRun={openRun}
              onOpenDraft={openSkillFromLibrary}
            />
          )}
          {tab === "evaluation" && (
            <EvaluationCenter skills={skills} onOpenSkill={openSkillFromLibrary} />
          )}
          {tab === "activity" && (
            <ExecutionActivity
              executions={executions}
              loading={executionsLoading}
              error={executionsError}
              isOperator={isOperator}
              onRefresh={loadExecutions}
              onOpenSkill={openSkillFromLibrary}
              onLearn={handleLearn}
              focusRunId={focusedRunId}
              onClearFocus={clearRunFocus}
            />
          )}
        </>
      )}

      {authoring && (
        <SkillAuthorForm
          editing={authoring === "new" ? null : authoring}
          onClose={() => setAuthoring(null)}
          onSaved={async (skillId) => {
            setAuthoring(null);
            flash("ok", authoring === "new" ? "Skill created" : "New skill version saved");
            await loadSkills();
            await openSkill(skillId);
          }}
        />
      )}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="ml-1 rounded-full bg-primary/20 px-1.5 py-0.5 text-[9px] font-bold text-primary">{children}</span>
  );
}
