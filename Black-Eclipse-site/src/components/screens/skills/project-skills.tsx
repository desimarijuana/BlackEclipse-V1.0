"use client";

// ── Project Skills panel (Phase 2) ──────────────────────────────────────────
// Repository-carried skills are inert until an operator explicitly trusts the
// project root. This panel surfaces discovery notices (names only), the trust
// state, and trust/untrust controls. It never loads an untrusted skill and
// never grants a permission — a trusted project skill still runs through the
// same permission/execution gate as any other skill.

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, FolderGit2, ShieldCheck, ShieldOff, History } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import {
  projectSkillStatus, trustProjectSkill, untrustProjectSkill, approveProjectSkill,
  projectTrustHistory,
} from "@/lib/harness/clients/skills-browser";
import type { ProjectSkillStatus, ProjectTrustApproval } from "@/lib/harness/skills-types";
import { ErrorState, formatWhen, LoadingState, PanelHeader } from "./skill-ui";

export function ProjectSkills({ isOperator }: { isOperator: boolean }) {
  const [status, setStatus] = useState<ProjectSkillStatus | null>(null);
  const [history, setHistory] = useState<ProjectTrustApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const trustedPager = usePagination(status?.trusted ?? [], 10);
  const historyPager = usePagination(history, 10);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const next = await projectSkillStatus();
      setStatus(next);
      try { setHistory(await projectTrustHistory(next.projectRoot ?? undefined)); }
      catch { setHistory([]); }
    }
    catch (err) { setError(err instanceof Error ? err.message : "failed to load"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<void>, message: string) => {
    setBusy(true);
    try { await fn(); setNotice(message); await load(); }
    catch (err) { setNotice(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setNotice(null), 4000); }
  };

  if (loading) {
    return <LoadingState label="Loading project skills…" />;
  }
  if (error) {
    return <ErrorState message={error} title="Could not load project skills" />;
  }
  if (!status) return null;

  const root = status.discovery.root;
  const changedIds = status.changedSkills?.changedSkillIds ?? status.discovery.changedSkillIds ?? [];
  const unchangedIds = status.changedSkills?.unchangedSkillIds ?? status.discovery.unchangedSkillIds ?? [];
  const reviewChanges = status.changedSkills?.changes ?? [];
  const drifted = Boolean(status.discovery.drift || status.drift?.drift);

  return (
    <div className="animate-fade-in-up">
      <PanelHeader
        icon={FolderGit2}
        title="Project skills"
        description={
          <>
            Skills a repository carries under <code>.black-eclipse/skills/</code> or{" "}
            <code>.agents/skills/</code>. They are never auto-loaded from a cloned repo:
            a project stays inert until you trust it. On a change, only the changed
            skills are quarantined — unchanged skills keep working. A trusted project
            skill still runs through the normal permission and evaluation gates.
          </>
        }
      />
      {notice && <p className="mb-3 text-[11px] text-primary">{notice}</p>}

      {!status.projectDiscovery && (
        <div className="rounded-2xl border border-border/20 glass-card-subtle p-4 text-[11px] text-muted-foreground">
          Project skill discovery is disabled globally (policy <code>project_skill_discovery</code>).
          No project root is scanned.
        </div>
      )}

      {status.projectDiscovery && (
        <>
          <div className="rounded-2xl border border-white/10 glass-card p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 min-w-0">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10">
                  <FolderGit2 size={16} className="text-primary" />
                </span>
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-foreground truncate">{root ?? "no project root"}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {drifted
                      ? `${changedIds.length} skill(s) changed — quarantined`
                      : status.discovery.trustedRoot ? "trusted" : "untrusted — contents not read"}
                    {status.discovery.trustedSkillIds.length > 0 ? ` · ${status.discovery.trustedSkillIds.length} skill(s) active` : ""}
                  </p>
                </div>
              </div>
              <div className="shrink-0 flex gap-2">
                {drifted ? (
                  <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                    onClick={() => act(() => approveProjectSkill(root ?? undefined, "re-approved after change", changedIds), "Project re-approved — changed skills reloaded")}>
                    <ShieldCheck size={12} className="mr-1" /> Approve changed
                  </Button>
                ) : status.discovery.trustedRoot ? (
                  <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300" disabled={!isOperator || busy}
                    onClick={() => act(() => untrustProjectSkill(root ?? undefined), "Project untrusted — its skills are no longer injected")}>
                    <ShieldOff size={12} className="mr-1" /> Untrust
                  </Button>
                ) : (
                  <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy || !root}
                    onClick={() => act(() => trustProjectSkill(root ?? undefined), "Project trusted — its skills will load")}>
                    <ShieldCheck size={12} className="mr-1" /> Trust project
                  </Button>
                )}
              </div>
            </div>

            {drifted && (
              <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-400/5 p-2.5 text-[10px] text-amber-200">
                {changedIds.length > 0 && unchangedIds.length > 0
                  ? "Only the changed skill(s) below are quarantined; unchanged skills remain active. Review the hashes, then Approve changed to re-enable them, or Untrust."
                  : "The content of this trusted project changed since it was approved. Review the hashes, then Approve changed to re-enable them, or Untrust."}
              </div>
            )}

            {reviewChanges.length > 0 && reviewChanges.some((c) => c.status !== "unchanged") && (
              <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <p className="mb-2 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Changed-skill review</p>
                <ul className="space-y-1.5">
                  {reviewChanges.filter((c) => c.status !== "unchanged").map((c) => (
                    <li key={c.skillId} className="flex items-center justify-between gap-3 text-[10px]">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full",
                          c.status === "unchanged" ? "bg-emerald-400" : c.status === "removed" ? "bg-rose-400" : "bg-amber-400")} />
                        <span className="truncate text-foreground">{c.skillId}</span>
                        <span className="shrink-0 rounded-full border border-border/40 px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground">{c.status}</span>
                      </span>
                      <code className="shrink-0 text-[9px] text-muted-foreground" title={`approved ${c.approvedHash ?? "—"} → current ${c.currentHash ?? "—"}`}>
                        {c.approvedHash?.slice(0, 7) ?? "—"} → {c.currentHash?.slice(0, 7) ?? "—"}
                      </code>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {status.discovery.notices.map((n, i) => (
              <p key={i} className="mt-3 text-[11px] text-amber-300/90">{n}</p>
            ))}

            {status.discovery.trustedSkillIds.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {status.discovery.trustedSkillIds.map((id) => (
                  <span key={id} className="rounded-lg border border-border/30 bg-accent/30 px-2 py-1 text-[10px] text-foreground">{id}</span>
                ))}
              </div>
            )}
          </div>

          {status.trusted.length > 0 && (
            <div className="mt-5 rounded-2xl border border-white/10 glass-card p-4">
              <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Trust decisions</p>
              <ul className="space-y-1">
                {trustedPager.pageItems.map((t) => (
                  <li key={t.path} className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="truncate text-foreground">{t.path}</span>
                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
                      t.trusted ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : "border-border/40 text-muted-foreground")}>
                      {t.trusted ? "trusted" : "revoked"}
                    </span>
                  </li>
                ))}
              </ul>
              <PaginationFooter pagination={trustedPager} label="trust decisions" />
            </div>
          )}

          {history.length > 0 && (
            <div className="mt-5 rounded-2xl border border-white/10 glass-card p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
                <History size={11} /> Approval history
              </p>
              <ul className="space-y-1.5">
                {historyPager.pageItems.map((h) => (
                  <li key={h.id} className="flex items-center justify-between gap-3 text-[10px]">
                    <span className="flex items-center gap-1.5 min-w-0">
                      {h.action === "untrust"
                        ? <ShieldOff size={10} className="shrink-0 text-rose-300" />
                        : <CheckCircle2 size={10} className="shrink-0 text-emerald-300" />}
                      <span className="shrink-0 uppercase text-foreground">{h.action}</span>
                      <span className="shrink-0 rounded-full border border-border/40 px-1.5 py-0.5 text-[9px] text-muted-foreground">{h.level}</span>
                      <span className="truncate text-muted-foreground">{h.actor ?? "operator"}</span>
                      {h.skillIds.length > 0 && <span className="shrink-0 text-muted-foreground">· {h.skillIds.length} skill(s)</span>}
                    </span>
                    <span className="shrink-0 text-muted-foreground">{h.approvedAt ? formatWhen(h.approvedAt) : ""}</span>
                  </li>
                ))}
              </ul>
              <PaginationFooter pagination={historyPager} label="decisions" />
            </div>
          )}
        </>
      )}
    </div>
  );
}
