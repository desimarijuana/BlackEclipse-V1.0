'use client';

// ── Plan review (Phase 5, plan_only) ────────────────────────────────────────
// A plan_only task's deliverable: what Eclipse WOULD do, with the files it would
// touch and the checks it would run, plus Accept / Not now. It cites real files
// the runtime resolved — never invented paths.

import { useT } from '@/lib/i18n/use-t';
import type { CodePlan } from '@/lib/harness/code-browser';

export interface PlanReviewProps {
  plan: CodePlan;
  onAccept?: () => void;
  onReject?: () => void;
}

export function PlanReview({ plan, onAccept, onReject }: PlanReviewProps) {
  const t = useT();
  return (
    <div className="glass-card rounded-xl border border-border/40 p-3 text-[12px]">
      <div className="mb-2 font-medium text-foreground">{t('code.task.plan.title')}</div>
      <ol className="ml-4 list-decimal space-y-1 text-muted-foreground">
        {plan.steps.map((step) => (
          <li key={step.id}>{step.description}</li>
        ))}
      </ol>
      {plan.files.length > 0 && (
        <div className="mt-2 text-muted-foreground/70">{t('code.task.plan.willTouch', { files: plan.files.join(', ') })}</div>
      )}
      {plan.checkClasses.length > 0 && (
        <div className="text-muted-foreground/70">{t('code.task.plan.willCheck', { checks: plan.checkClasses.join(', ') })}</div>
      )}
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={onAccept} className="rounded-lg border border-primary/50 px-3 py-1 text-primary">
          {t('code.task.plan.accept')}
        </button>
        <button type="button" onClick={onReject} className="rounded-lg border border-border/40 px-3 py-1 text-muted-foreground">
          {t('code.task.plan.reject')}
        </button>
      </div>
    </div>
  );
}
