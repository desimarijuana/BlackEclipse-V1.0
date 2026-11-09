"use client";

// ── Skill maintenance (Milestone 1) ─────────────────────────────────────────
// Stale skills, the reason each is stale, and the recommended action. Derived
// entirely from persisted execution/version data. Report-only by default:
// nothing is archived unless the operator explicitly enables it. Pinned skills
// are exempt and labelled as such.

import { useCallback, useEffect, useState } from "react";
import { Pin, PinOff, RefreshCw, Wrench } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import {
  getSkillMaintenance, runSkillMaintenance, pinSkillVersion,
} from "@/lib/harness/skills-browser";
import type { SkillMaintenanceReport } from "@/lib/harness/skills-types";
import { ErrorState, LoadingState, MetaRow, Panel, PanelHeader, formatWhen } from "./skill-ui";

export function SkillMaintenancePanel({ isOperator = false }: { isOperator?: boolean }) {
  const [report, setReport] = useState<SkillMaintenanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setReport(await getSkillMaintenance()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed to load maintenance"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const runPass = useCallback(async () => {
    setBusy(true); setNote(null); setError(null);
    try {
      const result = await runSkillMaintenance();
      if (result.reportOnly) {
        setNote(`Report-only: ${result.stale} stale, ${result.archiveEligible} eligible to archive. Nothing changed.`);
      } else {
        setNote(`Archived ${result.archived.length} stale skill(s); skipped ${result.skipped}.`);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "maintenance run failed");
    } finally { setBusy(false); }
  }, [load]);

  const togglePin = useCallback(async (skillId: string, version: string, pinned: boolean) => {
    setBusy(true); setError(null);
    try {
      await pinSkillVersion(skillId, version, !pinned);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "pin change failed");
    } finally { setBusy(false); }
  }, [load]);

  const items = report?.recommendations ?? [];
  const recPager = usePagination(items, 25);
  const dupPager = usePagination(report?.nearDuplicates ?? [], 10);

  if (loading) return <LoadingState label="Loading maintenance…" />;
  if (error && !report) return <ErrorState message={error} title="Could not load maintenance" />;

  return (
    <div className="space-y-2">
      <PanelHeader
        icon={Wrench}
        title="Skill maintenance"
        description="Stale skills, the reason each is stale, and the recommended action. Report-only by default: nothing is archived unless auto-archive is explicitly enabled."
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-xl cursor-pointer"
              onClick={() => void load()}
            >
              <RefreshCw size={12} className="mr-1" /> Refresh
            </Button>
            {isOperator && (
              <Button
                type="button"
                size="sm"
                className="rounded-xl cursor-pointer"
                disabled={busy}
                onClick={() => void runPass()}
              >
                Run pass
              </Button>
            )}
          </>
        }
      />
      <Panel className="p-3">
        <p className="text-[10px] text-muted-foreground">
          {report?.reportOnly
            ? "Report-only: recommendations are surfaced but nothing is transitioned."
            : "Auto-archive is enabled: qualifying stale, unpinned skills are retired (reversible)."}
        </p>
        {note && <p className="mt-1 text-[10px] text-emerald-300">{note}</p>}
        {error && <p className="mt-1 text-[10px] text-rose-300">{error}</p>}
        <div className="mt-2 grid grid-cols-2 gap-x-4 sm:grid-cols-4">
          <MetaRow label="Versions">{report?.counts.versions ?? 0}</MetaRow>
          <MetaRow label="Stale">{report?.counts.stale ?? 0}</MetaRow>
          <MetaRow label="Eligible to archive">{report?.counts.archiveEligible ?? 0}</MetaRow>
          <MetaRow label="Pinned exempt">{report?.counts.pinnedExempt ?? 0}</MetaRow>
        </div>
        <MetaRow label="Thresholds">
          stale ≥ {report?.thresholds.staleAfterDays ?? 0}d · archive ≥ {report?.thresholds.archiveAfterDays ?? 0}d
        </MetaRow>
        {report?.lastRun && (
          <MetaRow label="Last pass">
            {formatWhen(report.lastRun.ranAt)} · {report.lastRun.ok ? "ok" : `error: ${report.lastRun.error ?? "unknown"}`} · inspected {report.lastRun.inspected}, archived {report.lastRun.archived}
          </MetaRow>
        )}
      </Panel>

      {items.length === 0 ? (
        <p className="px-1 text-[11px] text-muted-foreground">
          No stale skills. A skill is stale only after {report?.thresholds.staleAfterDays ?? 0} days without a successful execution.
        </p>
      ) : (
        <>
        <Panel className="divide-y divide-white/5 p-0">
          {recPager.pageItems.map((item) => (
            <div key={`${item.skillId}@${item.version}`} className="flex items-start justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[11px] font-semibold text-foreground">{item.skillId}</span>
                  <span className="text-[9px] text-muted-foreground">v{item.version}</span>
                  {item.pinned && (
                    <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[8px] font-bold text-primary">PINNED</span>
                  )}
                  <span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-1.5 py-0.5 text-[8px] font-bold text-amber-200">
                    {item.recommendedAction ?? (item.stale ? "review" : "keep")}
                  </span>
                </div>
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  {item.reasons.join("; ")} · {item.ageDays ?? "?"}d · runs {item.runs} ({item.successes} ok)
                  {item.trend ? ` · ${item.trend}` : ""}
                  {item.lastUsedAt ? ` · last used ${formatWhen(item.lastUsedAt)}` : ""}
                </p>
              </div>
              {isOperator && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void togglePin(item.skillId, item.version, item.pinned)}
                  title={item.pinned ? "Unpin" : "Pin (exempt from automatic maintenance)"}
                  className="shrink-0 rounded-md border border-white/10 p-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  {item.pinned ? <PinOff size={11} /> : <Pin size={11} />}
                </button>
              )}
            </div>
          ))}
        </Panel>
        <PaginationFooter pagination={recPager} label="recommendations" />
        </>
      )}

      {(report?.nearDuplicates?.length ?? 0) > 0 && (
        <Panel className="p-3">
          <p className="text-[11px] font-semibold text-foreground">Possible duplicate skills</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            Skill ids that differ only by separators/case — likely a stale duplicate to merge or retire.
          </p>
          <ul className="mt-1 space-y-0.5">
            {dupPager.pageItems.map((group) => (
              <li key={group.normalized} className="text-[10px] text-foreground/80">
                {group.skillIds.join("  ·  ")}
              </li>
            ))}
          </ul>
          <PaginationFooter pagination={dupPager} label="duplicate groups" />
        </Panel>
      )}
    </div>
  );
}
