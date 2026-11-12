'use client';

// ── Task actions (Phase 5) ──────────────────────────────────────────────────
// Resume / stop / remove the task's work area. At plan_only the write
// affordances are NOT rendered (the tools do not exist), not merely disabled.

import { useT } from '@/lib/i18n/use-t';
import type { Autonomy } from '@/lib/harness/clients/code-browser';

export interface WorktreeActionsProps {
  autonomy: Autonomy;
  onResume?: () => void;
  onCancel?: () => void;
  onDiscard?: () => void;
}

export function WorktreeActions({ autonomy, onResume, onCancel, onDiscard }: WorktreeActionsProps) {
  const t = useT();
  // A plan_only task has no write capability: no resume-edit, no remove-work-area
  // affordance is rendered (the model cannot write, so there is nothing to run).
  const canWrite = autonomy !== 'plan_only';
  return (
    <div className="flex flex-wrap gap-2 text-[12px]">
      {canWrite && (
        <button type="button" onClick={onResume} className="glass-card-subtle rounded-lg border border-border/40 px-3 py-1 text-foreground">
          {t('code.task.undoChange')}
        </button>
      )}
      <button type="button" onClick={onCancel} className="glass-card-subtle rounded-lg border border-border/40 px-3 py-1 text-muted-foreground">
        {t('code.task.cancel')}
      </button>
      {canWrite && (
        <button type="button" onClick={onDiscard} className="glass-card-subtle rounded-lg border border-border/40 px-3 py-1 text-muted-foreground">
          {t('code.task.discard')}
        </button>
      )}
    </div>
  );
}
