"use client";

// Diagnostics cluster (retention, contradiction detection, real usage and
// compaction). Extracted from the Lifecycle view so browsing facts is not buried
// under operational prose; Maintenance owns these read/repair surfaces.

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  acceptCompaction, detectCompaction, listCompaction, memoryRetention,
  memoryUsageReport, rejectCompaction,
} from "@/lib/harness/clients/eclipse-memory-browser";
import type {
  CompactionProposal, MemoryRetentionStatus, MemoryUsageReport,
} from "@/lib/harness/eclipse-memory-types";
import { Spinner } from "./memory-ui";

export function MemoryDiagnostics({ isOperator }: { isOperator: boolean }) {
  const [retention, setRetention] = useState<MemoryRetentionStatus | null>(null);
  const [usage, setUsage] = useState<MemoryUsageReport | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [retentionBody, usageBody] = await Promise.all([
        memoryRetention(),
        memoryUsageReport(30),
      ]);
      setRetention(retentionBody);
      setUsage(usageBody);
    } catch {
      // Diagnostics are best-effort; a failure must not blank the Maintenance tab.
      setRetention(null);
      setUsage(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <Spinner label="Loading diagnostics…" />;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {retention && (
          <div className="rounded-2xl border border-white/10 glass-card p-3.5">
            <p className="text-[11px] font-semibold text-foreground">Retention</p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              {retention.automaticExpiryEnabled
                ? `Automatically learned memory expires after ${retention.retentionDays} day(s); explicit memory is never silently expired.`
                : "Automatic retention is off (0 days) — automatic memory never expires by policy. Explicit memory is never silently expired."}
            </p>
            {retention.nextMaintenanceAction && (
              <p className="mt-1 text-[10px] text-foreground/80">Next: {retention.nextMaintenanceAction}</p>
            )}
            {retention.lastSweep ? (
              <p className={cn("mt-1 text-[10px]", retention.lastSweep.ok ? "text-muted-foreground" : "text-amber-400")}>
                Last sweep {retention.lastSweep.ranAt}: inspected {retention.lastSweep.inspected}, expired {retention.lastSweep.expired}, skipped {retention.lastSweep.skipped}
                {!retention.lastSweep.ok && retention.lastSweep.error ? ` — failed: ${retention.lastSweep.error}` : ""}
              </p>
            ) : (
              <p className="mt-1 text-[10px] text-muted-foreground">No sweep recorded yet.</p>
            )}
          </div>
        )}

        <div className="rounded-2xl border border-white/10 glass-card p-3.5">
          <p className="text-[11px] font-semibold text-foreground">Contradiction detection</p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Deterministic lexical detection only. No network, no model, no embeddings.
            The optional semantic candidate layer was removed — deterministic
            normalization closed the measured gap, so it added no recall at a safe
            threshold.
          </p>
        </div>
      </div>

      {usage && (
        <div className="rounded-2xl border border-white/10 glass-card p-3.5">
          <p className="text-[11px] font-semibold text-foreground">Real usage (last {usage.windowDays} days)</p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Measured from actual persisted rows — not a synthetic set. A labeled eval proves
            the detector implements its rules, not that the rules match reality. Early
            numbers are small; treat them as such.
          </p>
          {usage.insufficientData ? (
            <p className="mt-1 text-[10px] text-muted-foreground/80">No usage in this window yet.</p>
          ) : (
            <>
              <p className="mt-1.5 text-[10px] text-foreground/80">
                Writes: {usage.durableWrites.saved} saved · {usage.durableWrites.suggested} suggested ·{" "}
                {usage.durableWrites.historyOnly} history-only · {usage.durableWrites.ignored} ignored
                {usage.durableWrites.explicitRequestRate != null
                  ? ` · explicit ${Math.round(usage.durableWrites.explicitRequestRate * 100)}% of saves`
                  : ""}
              </p>
              <p className="mt-1 text-[10px] text-foreground/80">
                Conflicts: {usage.conflicts.raised} raised · {usage.conflicts.accepted} accepted ·{" "}
                {usage.conflicts.dismissed} dismissed · {usage.conflicts.pending} pending
                {usage.conflicts.falsePositiveRate != null
                  ? ` · ${Math.round(usage.conflicts.falsePositiveRate * 100)}% dismissed (proxy)`
                  : ""}
              </p>
              <p className="mt-1 text-[10px] text-foreground/80">
                Ground truth (operator-labelled): {usage.conflicts.labeled} labelled
                {usage.conflicts.precision != null
                  ? ` · precision ${Math.round(usage.conflicts.precision * 100)}%` +
                    (usage.conflicts.precisionInterval
                      ? ` (95% CI ${Math.round(usage.conflicts.precisionInterval[0] * 100)}–${Math.round(usage.conflicts.precisionInterval[1] * 100)}%)`
                      : "") +
                    ` · ${usage.conflicts.labeledTrue} true / ${usage.conflicts.labeledFalsePositive} false`
                  : " · no labels yet — precision unknown, not perfect"}
              </p>
              {usage.trend && usage.trend.confident === false && (
                <p className="mt-1 text-[10px] text-muted-foreground/80">
                  Trend: insufficient data in one or both halves to name a direction.
                </p>
              )}
              {usage.trend && usage.trend.confident && (
                <p className="mt-1 text-[10px] text-foreground/80">
                  Trend: decisions {usage.trend.direction} (older {usage.trend.decisionsOlder} → recent {usage.trend.decisionsRecent})
                </p>
              )}
              {usage.smallSample && (
                <p className="mt-1 text-[10px] text-amber-300/90">
                  Sample is small — treat these numbers as directional, not reliable.
                </p>
              )}
              {usage.likelyMissedConflicts.count > 0 && (
                <p className="mt-1 text-[10px] text-amber-300/90">
                  {usage.likelyMissedConflicts.count} subject(s) have more than one active same-type
                  record — possible missed conflicts for human review (no text shown here).
                </p>
              )}
            </>
          )}
        </div>
      )}

      <CompactionPanel isOperator={isOperator} />
    </div>
  );
}

function CompactionPanel({ isOperator }: { isOperator: boolean }) {
  const [proposals, setProposals] = useState<CompactionProposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setProposals(await listCompaction("proposed")); } catch { setProposals([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true); setToast(null);
    try { await fn(); setToast(message); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  return (
    <div className="rounded-2xl border border-white/10 glass-card p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-foreground">Memory compaction</p>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
          onClick={() => act(() => detectCompaction(), "Checked for near-duplicates")}>
          Find duplicates
        </Button>
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        Near-duplicate facts in the same scope/subject can be merged. Nothing changes until you accept a
        proposal; originals are superseded (retained) and the merge is reversible.
      </p>
      {toast && <p className="mt-1 text-[10px] text-primary">{toast}</p>}
      {proposals.length > 0 && (
        <div className="mt-2 space-y-2">
          {proposals.map((p) => (
            <div key={p.id} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
              <p className="text-[10px] text-muted-foreground">{p.scope}{p.scopeId ? `:${p.scopeId}` : ""} · {p.subject ?? "no subject"} · {p.memberIds.length} memories</p>
              <p className="mt-1 text-[11px] text-foreground">{p.mergedContent}</p>
              {p.rationale && <p className="mt-1 text-[10px] text-muted-foreground/80">{p.rationale}</p>}
              <div className="mt-2 flex gap-2">
                <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => acceptCompaction(p.id), "Merged")}>Accept merge</Button>
                <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                  onClick={() => act(() => rejectCompaction(p.id), "Proposal dismissed")}>Dismiss</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
