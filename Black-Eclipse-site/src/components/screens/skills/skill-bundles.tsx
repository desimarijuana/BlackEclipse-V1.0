"use client";

// ── Skill Bundles panel (Phase 3) ───────────────────────────────────────────
// A bundle groups several skills under one stable id. It is a *reference*: the
// members must already exist, and resolution reports missing/unavailable
// members honestly — a bundle never enables a disabled skill or widens a
// permission. This panel creates/edits and resolves bundles.

import { useCallback, useEffect, useState } from "react";
import { Boxes, Loader2, Plus, RefreshCcw, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  listSkillBundles, saveSkillBundle, deleteSkillBundle,
} from "@/lib/harness/skills-browser";
import type { SkillBundle, SkillBundleResolution } from "@/lib/harness/skills-types";

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

  const remove = async (id: string) => {
    setBusy(true);
    try { await deleteSkillBundle(id); setToast("Bundle deleted"); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "delete failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4000); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" size={16} /> Loading…</div>;
  }
  if (error) {
    return <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center text-sm text-foreground">{error}</div>;
  }

  return (
    <div className="animate-fade-in-up">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">Skill bundles</h3>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-2xl leading-relaxed">
            Group skills for a recurring workflow under one id. A bundle is a reference — missing or
            disabled members are reported, never enabled. It cannot widen a permission or exceed the
            prompt budget.
          </p>
        </div>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer shrink-0" onClick={load} disabled={busy}>
          <RefreshCcw size={13} className="mr-1" /> Refresh
        </Button>
      </div>
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
        <div className="rounded-2xl border border-border/20 glass-card-subtle p-10 text-center">
          <Boxes size={24} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">No bundles yet</p>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">
            Create one to compose several skills under a single task profile (research, market-analysis, release-preparation…).
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {bundles.map((bundle) => {
            const r = resolved[bundle.id];
            return (
              <div key={bundle.id} className="rounded-2xl border border-white/10 dark:border-white/5 glass-card p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Boxes size={13} className="text-primary shrink-0" />
                      <span className="text-[12px] font-semibold text-foreground">{bundle.name || bundle.id}</span>
                      <span className="rounded-full border border-border/30 bg-accent/30 px-2 py-0.5 text-[9px] uppercase text-muted-foreground">{bundle.provenance}</span>
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
                <button onClick={() => editBundle(bundle)} disabled={!isOperator}
                  className="mt-2 text-[10px] text-primary hover:underline cursor-pointer disabled:text-muted-foreground">Edit</button>
              </div>
            );
          })}
        </div>
      )}
      {!isOperator && <p className="mt-3 text-[10px] text-amber-300/90">Read-only session — creating/deleting bundles requires operator authorization.</p>}
    </div>
  );
}
