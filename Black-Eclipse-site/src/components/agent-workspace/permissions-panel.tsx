'use client';

// ── Agent Workspace — Permissions / approvals panel ───────────────────────────
// A UI surface for approvals, NOT the authority itself: deciding POSTs to the
// existing approvals endpoint (`/api/harness/mcp/approvals/{id}/decide`), which
// resumes the paused run in place. The runtime's `approval.resolved` event is the
// authoritative clear; a failed POST re-surfaces the card.

import { useState } from 'react';
import { Check, ShieldAlert, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { PermissionRequest } from '@/lib/agent-workspace/types';

const RISK_TONE: Record<string, string> = {
  high: 'text-rose-300 border-rose-400/30 bg-rose-500/10',
  medium: 'text-amber-300 border-amber-400/30 bg-amber-500/10',
  low: 'text-emerald-300 border-emerald-400/30 bg-emerald-500/10',
};

export function PermissionsPanel({
  permissions,
  onDecide,
}: {
  permissions: PermissionRequest[];
  onDecide: (id: string, approve: boolean) => void;
}) {
  const t = useT();
  if (permissions.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <ul className="space-y-2">
      {permissions.map((p) => (
        <PermissionCard key={p.id} permission={p} onDecide={onDecide} />
      ))}
    </ul>
  );
}

function PermissionCard({
  permission,
  onDecide,
}: {
  permission: PermissionRequest;
  onDecide: (id: string, approve: boolean) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const pending = permission.status === 'pending';
  const risk = (permission.risk ?? '').toLowerCase();

  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      await onDecide(permission.id, approve);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      role={pending ? 'alertdialog' : undefined}
      aria-label={t('workspace.permission.title')}
      className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
    >
      <div className="flex items-start gap-2">
        <ShieldAlert size={15} className={pending ? 'mt-0.5 shrink-0 text-amber-400' : 'mt-0.5 shrink-0 text-muted-foreground/50'} />
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-foreground">{permission.title}</p>
          {permission.summary && <p className="mt-0.5 text-[11px] text-muted-foreground/70">{permission.summary}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {risk && (
              <span className={cn('rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wide', RISK_TONE[risk] ?? 'border-white/10 text-muted-foreground')}>
                {t('workspace.permission.risk')}: {permission.risk}
              </span>
            )}
            {permission.effect && (
              <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {t('workspace.permission.scope')}: {permission.effect}
              </span>
            )}
          </div>

          {pending ? (
            <div className="mt-2.5 flex items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => decide(true)}
                className="flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-200 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
              >
                <Check size={12} /> {t('workspace.permission.approve')}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => decide(false)}
                className="flex items-center gap-1.5 rounded-lg border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-200 transition-colors hover:bg-rose-500/20 disabled:opacity-50"
              >
                <X size={12} /> {t('workspace.permission.deny')}
              </button>
              <span className="text-[10px] text-muted-foreground/50">{t('workspace.permission.pending')}</span>
            </div>
          ) : (
            <p className={cn('mt-2 text-[11px]', permission.status === 'approved' ? 'text-emerald-300/80' : 'text-rose-300/80')}>
              {permission.status === 'approved' ? t('workspace.permission.approved') : t('workspace.permission.denied')}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}
