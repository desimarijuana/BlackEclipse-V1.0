"use client";

import { useCallback, useEffect, useState } from "react";
import { Wrench } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { MCPApprovalView } from "@/lib/harness/mcp-types";
import { Panel, EffectBadge } from "./primitives";

// ── Approvals panel (5G) ────────────────────────────────────────────────────
// Extracted from `mcp-settings.tsx` so the screen stays under its size ratchet.
// An effectful-tool approval is SINGLE-USE (ADR-H92): it authorizes exactly one
// call, then moves to `consumed`.

const APPROVAL_FILTERS = ["pending", "approved", "consumed", "denied", "expired", "all"] as const;
type ApprovalFilter = (typeof APPROVAL_FILTERS)[number];

export function MCPApprovalsPanel({ busy, onError }: { busy: boolean; onError: (m: string) => void }) {
  const [approvals, setApprovals] = useState<MCPApprovalView[]>([]);
  const [working, setWorking] = useState(false);
  const [filter, setFilter] = useState<ApprovalFilter>("pending");

  const load = useCallback(async () => {
    try {
      const query = filter === "all" ? "" : `?status=${encodeURIComponent(filter)}`;
      const res = await fetch(`/api/harness/mcp/approvals${query}`);
      const body = await res.json();
      if (res.ok) setApprovals(body.approvals ?? []);
    } catch {
      /* non-fatal */
    }
  }, [filter]);
  useEffect(() => { void load(); }, [load]);

  const decide = async (id: string, approve: boolean) => {
    setWorking(true);
    try {
      const res = await fetch(`/api/harness/mcp/approvals/${encodeURIComponent(id)}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approve }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Decision failed");
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setWorking(false);
    }
  };

  return (
    <Panel className="p-5">
      <div className="flex items-center gap-2 mb-2">
        <Wrench className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">Effectful-tool approvals</h3>
      </div>
      <p className="text-[10px] text-muted-foreground mb-3 leading-relaxed">
        A write/action MCP tool is blocked until you approve the exact call. The approval is bound to the server,
        tool, and argument digest, and expires. An approval is <span className="font-semibold text-foreground">single-use</span>:
        it authorizes exactly one call, then moves to <span className="font-mono">consumed</span>. A repeat of the
        same call needs a fresh decision — there is no &quot;remember&quot; or bulk approval.
      </p>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {APPROVAL_FILTERS.map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)}
            className={cn("rounded-lg border px-2 py-0.5 text-[10px] capitalize cursor-pointer",
              filter === f ? "border-primary/50 bg-primary/15 text-primary" : "border-border/30 text-muted-foreground hover:bg-accent/20")}>
            {f}
          </button>
        ))}
      </div>
      {approvals.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">No {filter === "all" ? "" : `${filter} `}approvals.</p>
      ) : (
        <div className="space-y-2">
          {approvals.map((a) => {
            const expired = a.status === "expired";
            const decided = a.status === "approved" || a.status === "denied" || a.status === "consumed";
            return (
              <div key={a.id} className={cn("rounded-xl border px-3 py-2",
                expired ? "border-border/20 bg-muted/10 opacity-80"
                  : decided ? "border-border/20 bg-muted/10"
                    : "border-primary/20 bg-primary/5")}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono text-foreground">{a.tool}</span>
                  <EffectBadge effect={a.effect} />
                  <span className={cn("text-[9px] font-bold uppercase",
                    a.status === "approved" ? "text-emerald-400" : a.status === "consumed" ? "text-sky-400" : a.status === "denied" ? "text-rose-400" : a.status === "expired" ? "text-muted-foreground" : "text-primary")}>
                    {a.status}
                  </span>
                  {a.risk && (
                    <span className={cn("text-[9px] font-bold uppercase", a.risk === "high" ? "text-rose-400" : "text-muted-foreground")}>
                      {a.risk} risk
                    </span>
                  )}
                  <span className="text-[9px] font-mono text-muted-foreground">{a.serverId}</span>
                </div>
                {a.actionSummary && <p className="text-[11px] text-foreground/90 mt-1">{a.actionSummary}</p>}
                {a.affectedData && (
                  <p className="text-[9px] font-mono text-muted-foreground mt-1 break-all">affects: {a.affectedData}</p>
                )}
                <p className="text-[9px] font-mono text-muted-foreground mt-1 break-all">digest {a.argsDigest.slice(0, 16)}…</p>
                {a.decidedBy && <p className="text-[9px] text-muted-foreground mt-1">decided by {a.decidedBy}{a.reason ? `: ${a.reason}` : ""}</p>}
                {a.usedAt && <p className="text-[9px] text-sky-400/80 mt-1">consumed {a.usedAt}</p>}
                {a.expiresAt && <p className="text-[9px] text-muted-foreground mt-1">expires {a.expiresAt}</p>}
                {a.requestedByRunId && (
                  <p className="text-[9px] text-muted-foreground mt-1">
                    run <span className="font-mono">{a.requestedByRunId}</span>
                  </p>
                )}
                {a.status === "pending" && (
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => void decide(a.id, true)} disabled={working || busy}>Approve this exact call</Button>
                    <Button size="sm" variant="ghost" className="cursor-pointer rounded-xl text-rose-400" onClick={() => void decide(a.id, false)} disabled={working || busy}>Deny</Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}