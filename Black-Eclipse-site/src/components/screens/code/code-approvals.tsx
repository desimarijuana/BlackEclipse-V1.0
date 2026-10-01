'use client';

// ── Actions waiting for you (Phase 5) ───────────────────────────────────────
// Pending external-action approvals. Each is a plain sentence; the status shows
// when an approval was already used once. The mechanism (kind, workspace) is
// behind "details" and in the trace.

import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import type { CodeApproval } from '@/lib/harness/code-client';

const ACTION_KEY: Record<string, TranslationKey> = {
  commit: 'code.approvals.action.commit',
  push: 'code.approvals.action.push',
  open_pr: 'code.approvals.action.openPr',
  deploy: 'code.approvals.action.deploy',
};

export interface CodeApprovalsProps {
  approvals: CodeApproval[];
  onDecide?: (id: string, approve: boolean) => void;
}

export function CodeApprovals({ approvals, onDecide }: CodeApprovalsProps) {
  const t = useT();
  const pending = approvals.filter((a) => a.status === 'pending');
  return (
    <div className="glass-card rounded-xl border border-border/40 p-3 text-[12px]">
      <div className="mb-2 font-medium text-foreground">{t('code.approvals.title')}</div>
      {pending.length === 0 ? (
        <div className="text-muted-foreground/70">{t('code.approvals.none')}</div>
      ) : (
        <ul className="space-y-1.5">
          {pending.map((approval) => {
            const action = approval.serverId.replace(/^code:/, '');
            return (
              <li key={approval.id} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {t(ACTION_KEY[action] ?? 'code.approvals.action.commit')}
                </span>
                <button type="button" onClick={() => onDecide?.(approval.id, true)} className="rounded-lg border border-primary/50 px-2 py-0.5 text-primary">
                  {t('code.approvals.approve')}
                </button>
                <button type="button" onClick={() => onDecide?.(approval.id, false)} className="rounded-lg border border-border/40 px-2 py-0.5 text-muted-foreground">
                  {t('code.approvals.deny')}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
