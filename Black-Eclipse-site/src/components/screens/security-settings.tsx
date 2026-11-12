"use client";

// ── Security settings panel ──────────────────────────────────────────────────
// The operator surface for the Security subsystem. It is a UI for the ONE
// decision path, never the authority itself: approvals decided here POST to
// `/api/security/approvals/{id}/decide`, which the Python gateway enforces. It
// never shows a secret value.

import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, Lock, Trash2 } from "@/lib/icons";
import { SectionHeader } from "./settings-ui";
import {
  decideSecurityApproval,
  getSecurityStatus,
  listSecurityApprovals,
  listSecurityCapabilities,
  revokeSecurityCapability,
  verifySecurityAudit,
  type SecurityCapability,
  type SecurityStatus,
} from "@/lib/harness/clients/security-browser";

const RISK_TONE: Record<string, string> = {
  critical: "text-rose-300 border-rose-400/30 bg-rose-500/10",
  high: "text-rose-300 border-rose-400/30 bg-rose-500/10",
  medium: "text-amber-300 border-amber-400/30 bg-amber-500/10",
  low: "text-emerald-300 border-emerald-400/30 bg-emerald-500/10",
};

export function SecuritySettingsPanel() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([]);
  const [capabilities, setCapabilities] = useState<SecurityCapability[]>([]);
  const [chain, setChain] = useState<{ valid: boolean; checked: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextStatus, nextApprovals, nextCaps, nextChain] = await Promise.all([
        getSecurityStatus(),
        listSecurityApprovals(),
        listSecurityCapabilities(),
        verifySecurityAudit(),
      ]);
      setStatus(nextStatus);
      setApprovals(nextApprovals);
      setCapabilities(nextCaps);
      setChain(nextChain);
    } catch (err) {
      setError(err instanceof Error ? err.message : "security layer unavailable");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (id: string, approve: boolean, remember = false) => {
    setBusy(true);
    try {
      await decideSecurityApproval(id, approve, { remember });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    setBusy(true);
    try {
      await revokeSecurityCapability(id);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const floorCount = status?.floor?.length ?? 0;
  const networkRules = status?.network?.rules?.length ?? 0;
  const counters = status?.audit?.counters ?? {};

  return (
    <div className="space-y-4">
      <SectionHeader
        icon={ShieldCheck}
        title="Security"
        description="Approvals, capabilities and audit — what the agent is allowed to do, and the record of what it actually did. No secrets are ever shown."
      />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-emerald-400" />
          <span className="text-sm font-medium">Security posture</span>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy}
          className="rounded-lg border border-border/30 px-3 py-1.5 text-[12px] hover:bg-white/[0.04] disabled:opacity-50"
        >
          {busy ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Profile" value={status?.profile ?? "—"} />
        <Stat label="Floor rules" value={String(floorCount)} />
        <Stat label="Network rules" value={String(networkRules)} />
        <Stat
          label="Audit chain"
          value={chain ? (chain.valid ? "valid" : "BROKEN") : "—"}
          tone={chain && !chain.valid ? "text-rose-300" : "text-emerald-300"}
        />
      </div>

      {Object.keys(counters).length > 0 && (
        <div className="rounded-xl border border-border/20 glass-card-subtle p-3">
          <div className="mb-1 text-[12px] font-medium text-muted-foreground">Security counters</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(counters).map(([key, value]) => (
              <span key={key} className="rounded-md border border-border/20 px-2 py-0.5 text-[11px]">
                {key}: {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-border/20 glass-card-subtle">
        <div className="flex items-center gap-2 border-b border-border/20 px-3 py-2 text-[12px] font-medium">
          <ShieldAlert size={14} className="text-amber-400" />
          Pending approvals ({approvals.length})
        </div>
        {approvals.length === 0 ? (
          <p className="px-3 py-3 text-[12px] text-muted-foreground/60">No approvals waiting.</p>
        ) : (
          <ul className="divide-y divide-border/10">
            {approvals.map((a) => {
              const id = String(a.id ?? "");
              const risk = String(a.risk ?? "").toLowerCase();
              return (
                <li key={id} className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-start sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12px]">{String(a.actionSummary ?? a.tool ?? id)}</div>
                    {risk && (
                      <span className={`mt-1 inline-block rounded border px-1.5 py-0.5 text-[10px] uppercase ${RISK_TONE[risk] ?? RISK_TONE.medium}`}>
                        {risk}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-1.5 sm:justify-end">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void decide(id, true)}
                      className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
                    >
                      Approve once
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void decide(id, true, true)}
                      className="rounded-lg border border-border/30 px-2.5 py-1 text-[11px] hover:bg-white/[0.04] disabled:opacity-50"
                    >
                      Always allow
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void decide(id, false)}
                      className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-200 hover:bg-rose-500/20 disabled:opacity-50"
                    >
                      Deny
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-border/20 glass-card-subtle">
        <div className="flex items-center gap-2 border-b border-border/20 px-3 py-2 text-[12px] font-medium">
          <Lock size={14} />
          Active capabilities ({capabilities.filter((c) => c.active).length})
        </div>
        {capabilities.length === 0 ? (
          <p className="px-3 py-3 text-[12px] text-muted-foreground/60">No capabilities issued.</p>
        ) : (
          <ul className="divide-y divide-border/10">
            {capabilities.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1 text-[12px]">
                  <span className="font-mono">{c.action}</span>
                  <span className="text-muted-foreground"> · {c.resource}</span>
                  {!c.active && <span className="ml-2 text-[10px] text-muted-foreground/60">(inactive)</span>}
                </div>
                {c.active && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void revoke(c.id)}
                    className="flex items-center gap-1 rounded-lg border border-border/30 px-2 py-1 text-[11px] hover:bg-white/[0.04] disabled:opacity-50"
                  >
                    <Trash2 size={12} /> Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border/20 glass-card-subtle px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{label}</div>
      <div className={`mt-0.5 text-[13px] font-medium ${tone ?? ""}`}>{value}</div>
    </div>
  );
}
