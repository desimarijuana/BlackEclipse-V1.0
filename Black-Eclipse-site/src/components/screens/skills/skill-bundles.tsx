"use client";

// ── Skill Bundles panel (Phase 3) ───────────────────────────────────────────
// A bundle groups several skills under one stable id. It is a *reference*: the
// members must already exist, and resolution reports missing/unavailable
// members honestly — a bundle never enables a disabled skill or widens a
// permission. This panel creates/edits and resolves bundles.

import { useCallback, useEffect, useState } from "react";
import { Boxes, Plus, RefreshCcw, Trash2, X } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import {
  listSkillBundles, saveSkillBundle, deleteSkillBundle,
  lockSkillBundle, unlockSkillBundle, bundleUpdatePreview, rollbackSkillBundle,
} from "@/lib/harness/skills-browser";
import type {
  BundleUpdatePreview, SkillBundle, SkillBundleResolution,
} from "@/lib/harness/skills-types";
import { EmptyState, ErrorState, LoadingState, PanelHeader } from "./skill-ui";

const EMPTY: Partial<SkillBundle> & { id: string } = {
  id: "", name: "", description: "", skills: [], instruction: "", constraints: "", provenance: "manual",
};

export function SkillBundles({ isOperator }: { isOperator: boolean }) {
  const [bundles, setBundles] = useState<SkillBundle[]>([]);
  const [resolved, setResolved] = useState<Record<string, SkillBundleResolution>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [draft, setDraft] = useState<(Partial<SkillBundle> & { id: string }) | null>(null);
  const [skillsText, setSkillsText] = useState("");
  const [previews, setPreviews] = useState<Record<string, BundleUpdatePreview>>({});
  const [previewing, setPreviewing] = useState<string | null>(null);
  const pagination = usePagination(bundles, 10);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await listSkillBundles();
      setBundles(data.bundles);
      setResolved(data.resolved);
    } catch (err) { setError(err instanceof Error ? err.message : "failed to load"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const editBundle = (bundle: SkillBundle) => {
    setDraft({ ...bundle });
    setSkillsText(bundle.skills.join("\n"));
  };

  const save = async () => {
    if (!draft?.id.trim()) return;
    setBusy(true);
    try {
      await saveSkillBundle({
        id: draft.id.trim(),
        name: draft.name || draft.id,
        description: draft.description || "",
        skills: skillsText.split("\n").map((s) => s.trim()).filter(Boolean),
        instruction: draft.instruction || "",
        constraints: draft.constraints || "",
        provenance: draft.provenance || "manual",
      });
      setToast("Bundle saved"); setDraft(null); setSkillsText(""); await load();
    } catch (err) { setToast(err instanceof Error ? err.message : "save failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  const remove = async (id: string) => {
    if (!window.confirm(`Delete bundle "${id}"? Skills in it are not affected.`)) return;
    setBusy(true);
    try { await deleteSkillBundle(id); setToast("Bundle deleted"); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "delete failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  const previewUpdate = async (id: string) => {
    setPreviewing(id);
    try {
      const next = await bundleUpdatePreview(id);
      setPreviews((prev) => ({ ...prev, [id]: next }));
    } catch (err) {
      setToast(err instanceof Error ? err.message : "preview failed");
      setTimeout(() => setToast(null), 4000);
    } finally {
      setPreviewing(null);
    }
  };

  const rollback = async (id: string) => {
    if (!window.confirm(`Roll bundle "${id}" back to its previous locked member versions?`)) return;
    setPreviews((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    await act(() => rollbackSkillBundle(id), "Bundle rolled back");
  };

  if (loading) {
    return <LoadingState label="Loading bundles…" />;
  }
  if (error) {
    return <ErrorState message={error} title="Could not load bundles" />;
  }

  return (
    <div className="animate-fade-in-up">
      <PanelHeader
        icon={Boxes}
        title="Skill bundles"
        description="Group skills for a recurring workflow under one id. A bundle is a reference — missing or disabled members are reported, never enabled. It cannot widen a permission or exceed the prompt budget."
        actions={
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer shrink-0" onClick={load} disabled={busy}>
            <RefreshCcw size={13} className="mr-1" /> Refresh
          </Button>
        }
      />
      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      {draft ? (
        <div className="mb-5 rounded-2xl border border-primary/20 glass-card p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold text-foreground">{draft.id ? `Edit ${draft.id}` : "New bundle"}</p>
            <button onClick={() => { setDraft(null); setSkillsText(""); }} className="text-muted-foreground hover:text-foreground cursor-pointer"><X size={14} /></button>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <Input value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="id (lowercase slug)" className="rounded-xl bg-background/60" disabled={Boolean(draft.id && bundles.some((b) => b.id === draft.id))} />
            <Input value={draft.name ?? ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="display name" className="rounded-xl bg-background/60" />
          </div>
          <Input value={draft.description ?? ""} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="description" className="rounded-xl bg-background/60" />
          <textarea value={skillsText} onChange={(e) => setSkillsText(e.target.value)} rows={3}
            placeholder="One skill id per line…" className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40" />
          <textarea value={draft.instruction ?? ""} onChange={(e) => setDraft({ ...draft, instruction: e.target.value })} rows={2}
            placeholder="optional instruction prepended when the bundle is used" className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40" />
          <div className="flex justify-end">
            <Button size="sm" className="rounded-xl cursor-pointer" disabled={busy || !draft.id.trim() || !isOperator} onClick={save}>Save bundle</Button>
          </div>
        </div>
      ) : (
        <Button size="sm" className="mb-5 rounded-xl cursor-pointer" disabled={!isOperator}
          onClick={() => { setDraft({ ...EMPTY }); setSkillsText(""); }}>
          <Plus size={13} className="mr-1" /> New bundle
        </Button>
      )}

      {bundles.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No bundles yet"
          hint="Create one to compose several skills under a single task profile (research, market-analysis, release-preparation…)."
        />
      ) : (
        <>
        <div className="space-y-2">
          {pagination.pageItems.map((bundle) => {
            const r = resolved[bundle.id];
            return (
              <div key={bundle.id} className="rounded-2xl border border-white/10 dark:border-white/5 glass-card p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Boxes size={13} className="text-primary shrink-0" />
                      <span className="text-[12px] font-semibold text-foreground">{bundle.name || bundle.id}</span>
                      <span className="rounded-full border border-border/30 bg-accent/30 px-2 py-0.5 text-[9px] uppercase text-muted-foreground">{bundle.provenance}</span>
                      <span className="rounded-md border border-border/30 bg-accent/30 px-1.5 py-0.5 text-[9px] text-muted-foreground">v{bundle.version}</span>
                      {bundle.locked && <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 text-[9px] font-bold uppercase text-emerald-300">locked</span>}
                      {r?.drifted && <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[9px] font-bold uppercase text-amber-300">drifted</span>}
                    </div>
                    {bundle.description && <p className="mt-1 text-[11px] text-muted-foreground">{bundle.description}</p>}
                    <div className="mt-2 flex flex-wrap gap-1">
                      {bundle.skills.map((s) => {
                        const missing = r?.missing.includes(s);
                        const unavailable = r?.unavailable.includes(s);
                        return (
                          <span key={s} className={cn("rounded-md border px-1.5 py-0.5 text-[10px]",
                            missing ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                            : unavailable ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                            : "border-emerald-400/20 bg-emerald-400/10 text-emerald-300")}>
                            {s}{missing ? " · missing" : unavailable ? " · unavailable" : ""}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300 shrink-0" disabled={!isOperator || busy}
                    onClick={() => remove(bundle.id)}>
                    <Trash2 size={12} />
                  </Button>
                </div>
                {r?.drifted && (
                  <p className="mt-2 text-[10px] text-amber-300/90">
                    {r.incompatible?.join(" · ") || "A member changed since this bundle was locked."}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <button onClick={() => editBundle(bundle)} disabled={!isOperator}
                    className="text-[10px] text-primary hover:underline cursor-pointer disabled:text-muted-foreground">Edit</button>
                  {bundle.locked ? (
                    <>
                      <button onClick={() => void previewUpdate(bundle.id)} disabled={!isOperator || busy || previewing === bundle.id}
                        className="text-[10px] text-sky-300 hover:underline cursor-pointer disabled:text-muted-foreground">
                        {previewing === bundle.id ? "Checking…" : "Preview update"}
                      </button>
                      <button onClick={() => void rollback(bundle.id)} disabled={!isOperator || busy}
                        className="text-[10px] text-rose-300 hover:underline cursor-pointer disabled:text-muted-foreground">Rollback</button>
                      <button onClick={() => act(() => unlockSkillBundle(bundle.id), "Bundle unlocked")} disabled={!isOperator || busy}
                        className="text-[10px] text-amber-300 hover:underline cursor-pointer disabled:text-muted-foreground">Unlock</button>
                    </>
                  ) : (
                    <button onClick={() => act(() => lockSkillBundle(bundle.id), "Bundle locked to current member versions")} disabled={!isOperator || busy}
                      className="text-[10px] text-emerald-300 hover:underline cursor-pointer disabled:text-muted-foreground">Lock</button>
                  )}
                </div>

                {previews[bundle.id] && (
                  <div className="mt-2 rounded-xl border border-sky-400/20 bg-sky-400/5 p-2.5">
                    <p className="text-[10px] font-semibold text-sky-200">
                      {previews[bundle.id].wouldChange
                        ? "A new lock would change these members:"
                        : "No member changes since the last lock."}
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {previews[bundle.id].changes
                        .filter((change) => change.change !== "unchanged")
                        .map((change) => (
                          <li key={change.skillId} className="text-[10px] text-muted-foreground">
                            <span className="text-foreground">{change.skillId}</span>
                            {" · "}{change.change.replace("_", " ")}
                            {change.lockedVersion ? ` · locked v${change.lockedVersion}` : ""}
                            {change.currentVersion ? ` → current v${change.currentVersion}` : ""}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <PaginationFooter pagination={pagination} label="bundles" />
        </>
      )}
    </div>
  );
}
