"use client";

// ── Skill Control Room — the Phase-3 screen ─────────────────────────────────
// Tabs: Skills Library · Learning Queue · Evaluation Center · Execution
// Activity. Skill Detail and Draft Review are drill-down views inside the
// Library tab. All data comes from the Python runtime through the front door;
// every mutating action is re-checked server-side.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, FlaskConical, Library, Lightbulb } from "lucide-react";
import { TabBar } from "@/components/ui/tab-bar";
import { useSubroute } from "@/hooks/use-subroute";
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

type Tab = "library" | "learning" | "evaluation" | "activity";

export function SkillsScreen({ isOperator = false }: { isOperator?: boolean }) {
  const [tab, setTab] = useState<Tab>("library");
  // Deep links (e.g. "Learning Queue" from an originating chat run) land on the
  // matching sub-tab: skills.library/learning/evaluation/activity.
  useSubroute("skills", (req) => {
    const next = req.subroute.split(".")[1] as Tab | undefined;
    if (next && ["library", "learning", "evaluation", "activity"].includes(next)) setTab(next);
  });
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [duplicates, setDuplicates] = useState<string[]>([]);
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
    } catch (err) {
      setListError(err instanceof Error ? err.message : "failed to load skills");
    } finally {
      setListLoading(false);
    }
  }, []);

  const openSkill = useCallback(async (skillId: string) => {
    setTab("library");
    setDetailLoading(true);
    setDetailError(null);
    try {
      const skill = await getSkill(skillId);
      if (!skill) throw new Error("Skill not found");
      setDetail(skill);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "failed to load skill");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetail = useCallback(() => { setDetail(null); void loadSkills(); }, [loadSkills]);

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

  const tabs = useMemo(() => [
    { id: "library", label: "Skills Library", icon: Library },
    { id: "learning", label: "Learning Queue", icon: Lightbulb, badge: candidates.length > 0 ? <Badge>{candidates.length}</Badge> : undefined },
    { id: "evaluation", label: "Evaluation Center", icon: FlaskConical },
    { id: "activity", label: "Execution Activity", icon: Activity },
  ], [candidates.length]);

  return (
    <div className="w-full px-4 py-6 md:px-8">
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 rounded-xl border px-4 py-3 text-xs font-semibold shadow-lg glass-card-strong ${
          toast.tone === "ok" ? "border-emerald-400/30 text-emerald-200" : "border-rose-400/30 text-rose-200"
        }`}>
          {toast.text}
        </div>
      )}

      {detail && tab === "library" ? (
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
          <TabBar items={tabs} activeId={tab} onChange={(id) => setTab(id as Tab)} variant="subtle" />
          {tab === "library" && (
            <SkillLibrary
              skills={skills}
              loading={listLoading}
              error={listError}
              loadErrors={loadErrors}
              duplicates={duplicates}
              isOperator={isOperator}
              onOpen={openSkill}
              onRefresh={loadSkills}
              onAdd={() => setAuthoring("new")}
            />
          )}
          {tab === "learning" && (
            <LearningQueue
              candidates={candidates}
              loading={candidatesLoading}
              error={candidatesError}
              isOperator={isOperator}
              onRefresh={loadCandidates}
              onGenerateDraft={handleGenerateDraft}
              onReject={handleRejectCandidate}
              onOpenRun={(runId) => flash("ok", `Source run: ${runId}`)}
              onOpenDraft={(skillId) => void openSkill(skillId)}
            />
          )}
          {tab === "evaluation" && (
            <EvaluationCenter skills={skills} isOperator={isOperator} onOpenSkill={openSkill} />
          )}
          {tab === "activity" && (
            <ExecutionActivity
              executions={executions}
              loading={executionsLoading}
              error={executionsError}
              isOperator={isOperator}
              onRefresh={loadExecutions}
              onOpenSkill={openSkill}
              onLearn={handleLearn}
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
