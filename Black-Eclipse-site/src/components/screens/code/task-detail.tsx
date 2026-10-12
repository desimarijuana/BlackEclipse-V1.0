'use client';

// ── Task detail (Phase 5) ───────────────────────────────────────────────────
// The run: a plain progress line, the change in everyday words, the proof it
// works, and the audit timeline. The mechanism never leads.

import { useT } from '@/lib/i18n/use-t';
import type { CodeTask } from '@/lib/harness/code-browser';
import { CheckResults } from './check-results';
import { DiffViewer } from './diff-viewer';
import { PlanReview } from './plan-review';
import { WorktreeActions } from './worktree-actions';
import { PromoteChange } from '@/components/chat/promote-change';

export interface TaskDetailProps {
  task: CodeTask;
  diffFiles?: string[];
  diffUnified?: string;
  diffDigest?: string | null;
  onAcceptPlan?: () => void;
  onRejectPlan?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onDiscard?: () => void;
}

export function TaskDetail({
  task, diffFiles = [], diffUnified, diffDigest,
  onAcceptPlan, onRejectPlan, onResume, onCancel, onDiscard,
}: TaskDetailProps) {
  const t = useT();
  const progressKey = task.status === 'failed' ? 'code.task.resultFailed'
    : task.status === 'completed' ? 'code.task.resultDone'
    : 'code.task.working';
  return (
    <div className="space-y-2.5">
      <div className="glass-card rounded-xl border border-border/40 p-3 text-[12px]">
        <div className="text-foreground">{task.query}</div>
        <div className="mt-1 text-muted-foreground">{t(progressKey)}</div>
      </div>
      {task.status === 'plan_review' && task.plan && (
        <PlanReview plan={task.plan} onAccept={onAcceptPlan} onReject={onRejectPlan} />
      )}
      {diffFiles.length > 0 && (
        <DiffViewer files={diffFiles} unified={diffUnified} digest={diffDigest} />
      )}
      <CheckResults verification={task.verification} />
      {task.autonomy !== 'plan_only' && <PromoteChange runId={task.id} />}
      <WorktreeActions autonomy={task.autonomy} onResume={onResume} onCancel={onCancel} onDiscard={onDiscard} />
    </div>
  );
}
