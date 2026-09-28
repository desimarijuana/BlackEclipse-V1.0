"use client";

// ── Project Skills panel (Phase 2) ──────────────────────────────────────────
// Repository-carried skills are inert until an operator explicitly trusts the
// project root. This panel surfaces discovery notices (names only), the trust
// state, and trust/untrust controls. It never loads an untrusted skill and
// never grants a permission — a trusted project skill still runs through the
// same permission/execution gate as any other skill.

import { useCallback, useEffect, useState } from "react";
import { FolderGit2, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  projectSkillStatus,   trustProjectSkill, untrustProjectSkill, approveProjectSkill,
} from "@/lib/harness/skills-browser";
import type { ProjectSkillStatus } from "@/lib/harness/skills-types";

export function ProjectSkills({ isOperator }: { isOperator: boolean }) {
  const [status, setStatus] = useState<ProjectSkillStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setStatus(await projectSkillStatus()); }
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
    return <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" size={16} /> Loading…</div>;
  }
  if (error) {
    return <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center text-sm text-foreground">{error}</div>;
  }
  if (!status) return null;

  const root = status.discovery.root;
  const drifted = Boolean(status.discovery.drift || status.drift?.drift);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-4">
        <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">Project skills</h3>
        <p className="mt-1 text-[11px] text-muted-foreground max-w-2xl leading-relaxed">
          Skills a repository carries under <code>.black-eclipse/skills/</code> or{" "}
          <code>.agents/skills/</code>. They are never auto-loaded from a cloned repo:
          a project stays inert until you trust it. A trusted project skill still runs
          through the normal permission and evaluation gates.
        </p>
      </div>
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
                      ? "quarantined — content changed since trust"
                      : status.discovery.trustedRoot ? "trusted" : "untrusted — contents not read"}
                    {status.discovery.trustedSkillIds.length > 0 ? ` · ${status.discovery.trustedSkillIds.length} skill(s) active` : ""}
                  </p>
                </div>
              </div>
              <div className="shrink-0 flex gap-2">
                {drifted ? (
                  <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy}
                    onClick={() => act(() => approveProjectSkill(root ?? undefined, "re-approved after change"), "Project re-approved — skills reloaded")}>
                    <ShieldCheck size={12} className="mr-1" /> Re-approve
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
                The content of this trusted project changed since it was approved. Its skills are
                quarantined and not loaded. Review the change, then Re-approve to enable them, or Untrust.
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
            {!isOperator && <p className="mt-3 text-[10px] text-amber-300/90">Read-only session — trust changes require operator authorization.</p>}
          </div>

          {status.trusted.length > 0 && (
            <div className="mt-5 rounded-2xl border border-white/10 glass-card p-4">
              <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Trust decisions</p>
              <ul className="space-y-1">
                {status.trusted.map((t) => (
                  <li key={t.path} className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="truncate text-foreground">{t.path}</span>
                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
                      t.trusted ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : "border-border/40 text-muted-foreground")}>
                      {t.trusted ? "trusted" : "revoked"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
