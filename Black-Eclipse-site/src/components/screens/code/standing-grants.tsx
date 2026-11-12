'use client';

// ── Standing permissions ("always allow") ───────────────────────────────────
// The revocable counterpart to the single-use approval. Every grant here is one
// program/tool in one workspace: matching a command stops the approval prompt,
// but a denied/destructive command is still refused. Revoking is immediate and
// idempotent. Nothing is granted except through an explicit "Always allow"
// choice on a real pending approval — this panel only lists and revokes.

import { useCallback, useEffect, useState } from 'react';
import { Shield, Trash2, Loader2 } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { listStandingGrants, revokeStandingGrant, type StandingGrant } from '@/lib/harness/clients/grants-browser';

function kindLabel(kind: string): string {
  if (kind === 'command') return 'Command';
  if (kind === 'mcp_tool') return 'MCP tool';
  if (kind === 'git_operation') return 'Git';
  return kind;
}

export function StandingGrantsPanel() {
  const t = useT();
  const [grants, setGrants] = useState<StandingGrant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setGrants(await listStandingGrants());
      setError(null);
    } catch {
      setError(t('code.approvals.loadFailed'));
    }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const revoke = async (id: string) => {
    setBusyId(id);
    try {
      await revokeStandingGrant(id);
      setGrants((prev) => prev.filter((g) => g.id !== id));
    } catch {
      setError(t('code.approvals.loadFailed'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="glass-card rounded-xl border border-border/40 p-3 text-[12px]">
      <div className="mb-1 flex items-center gap-2">
        <Shield className="h-3.5 w-3.5 text-primary" />
        <span className="font-medium text-foreground">Always-allowed permissions</span>
      </div>
      <p className="mb-2 text-[10px] leading-relaxed text-muted-foreground">
        A grant stops Eclipse asking again for the same program or tool in this
        workspace. Destructive commands are still refused. Revoke anytime.
      </p>
      {error && <div className="mb-2 text-[11px] text-rose-300">{error}</div>}
      {grants.length === 0 ? (
        <div className="text-muted-foreground/70">No standing permissions.</div>
      ) : (
        <ul className="space-y-1.5">
          {grants.map((g) => (
            <li key={g.id} className="flex items-center gap-2">
              <span className="rounded-md border border-border/40 px-1.5 py-0.5 text-[9px] font-mono uppercase text-muted-foreground">
                {kindLabel(g.kind)}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-foreground">{g.pattern}</span>
              {g.risk && <span className="text-[9px] uppercase text-muted-foreground">{g.risk} risk</span>}
              <button
                type="button"
                onClick={() => void revoke(g.id)}
                disabled={busyId === g.id}
                className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-rose-500/30 px-2 py-0.5 text-[11px] text-rose-300 hover:bg-rose-500/10 disabled:opacity-50"
              >
                {busyId === g.id ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                Revoke
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
