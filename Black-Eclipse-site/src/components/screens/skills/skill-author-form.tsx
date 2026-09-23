"use client";

// ── Skill authoring form — create/edit a user skill ─────────────────────────
// Validates on the client for fast feedback, but the server is authoritative:
// the manifest, safe permissions, and real tools are all re-checked in Python.
// Built-in skills cannot be edited; only `origin: author` skills show Edit.

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Loader2, Plus, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  getAuthoringMeta, createUserSkill, updateUserSkill,
  type AuthoringMeta, type AuthorSkillInput,
} from "@/lib/harness/skills-browser";
import type { SkillDetail } from "@/lib/harness/skills-types";

interface Draft {
  skillId: string;
  name: string;
  description: string;
  category: string;
  instructions: string;
  tags: string;
  requiredTools: string[];
  permissions: string[];
  riskLevel: string;
}

const EMPTY: Draft = {
  skillId: "", name: "", description: "", category: "research",
  instructions: "", tags: "", requiredTools: [], permissions: ["data.read", "analysis.execute"],
  riskLevel: "low",
};

function fromDetail(skill: SkillDetail): Draft {
  return {
    skillId: skill.id,
    name: skill.name,
    description: skill.description,
    category: skill.category,
    instructions: skill.instructions ?? "",
    tags: (skill.tags ?? []).join(", "),
    requiredTools: [...(skill.requiredTools ?? [])],
    permissions: [...(skill.permissions ?? [])],
    riskLevel: skill.riskLevel,
  };
}

export function SkillAuthorForm({
  editing,
  onClose,
  onSaved,
}: {
  editing?: SkillDetail | null;
  onClose: () => void;
  onSaved: (skillId: string) => void;
}) {
  const [meta, setMeta] = useState<AuthoringMeta | null>(null);
  const [draft, setDraft] = useState<Draft>(editing ? fromDetail(editing) : { ...EMPTY });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Portal to <body> only after mount (SSR-safe).
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    getAuthoringMeta().then(setMeta).catch(() => setMeta(null));
  }, []);

  const isEdit = Boolean(editing);

  const submit = async () => {
    setError(null);
    if (!draft.name.trim()) { setError("Name is required."); return; }
    if (!draft.instructions.trim()) { setError("Instructions are required — they are the procedure."); return; }
    if (draft.requiredTools.length > 0 && !meta) {
      setError("Tool list unavailable; retry once the runtime is ready."); return;
    }
    setSaving(true);
    const payload: AuthorSkillInput = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      instructions: draft.instructions,
      category: draft.category,
      tags: draft.tags.split(",").map((t) => t.trim()).filter(Boolean),
      requiredTools: draft.requiredTools,
      permissions: draft.permissions,
      riskLevel: draft.riskLevel,
      skillId: draft.skillId || undefined,
    };
    try {
      const result = isEdit
        ? await updateUserSkill(draft.skillId, payload)
        : await createUserSkill(payload);
      onSaved(result.skillId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the skill.");
    } finally {
      setSaving(false);
    }
  };

  const toggleTool = (tool: string) => {
    setDraft((d) => ({
      ...d,
      requiredTools: d.requiredTools.includes(tool)
        ? d.requiredTools.filter((t) => t !== tool)
        : [...d.requiredTools, tool],
    }));
  };
  const togglePermission = (permission: string) => {
    setDraft((d) => ({
      ...d,
      permissions: d.permissions.includes(permission)
        ? d.permissions.filter((p) => p !== permission)
        : [...d.permissions, permission],
    }));
  };

  // The drawer must render at <body>, not inside the main glass container: that
  // container is a backdrop root (blur/transform), which would scope the fixed
  // positioning and trap the panel under the app header.
  const overlay = (
    <div className="fixed inset-0 z-[100] flex justify-end" role="dialog" aria-label={isEdit ? "Edit skill" : "Add skill"}>
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-xl h-full glass-card-strong border-l border-white/10 overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border/10 bg-background/80 px-5 py-3 backdrop-blur">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
              <Plus size={15} className="text-primary" />
            </span>
            <h3 className="text-sm font-semibold text-foreground">{isEdit ? "Edit skill" : "Add your own skill"}</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            A skill is a reusable procedure the agent follows. Write the steps you want it to take,
            and pick the tools it may use. It becomes available to the agent immediately and is stored
            in Eclipse Memory.
          </p>

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-400/30 bg-rose-400/5 p-3 text-[11px] text-rose-200">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3">
            <Field label="Name" hint="What the skill does, e.g. “Earnings call summary”.">
              <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="Earnings call summary" className="rounded-xl bg-background/60" disabled={isEdit} />
            </Field>

            <Field label="Description" hint="One line the agent sees when discovering skills.">
              <Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder="Summarize the latest earnings call with sources." className="rounded-xl bg-background/60" />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Category">
                <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                  className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-xs outline-none focus:border-primary/40">
                  {(meta?.categories ?? ["research", "quality", "finance", "system"]).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Risk level">
                <select value={draft.riskLevel} onChange={(e) => setDraft({ ...draft, riskLevel: e.target.value })}
                  className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-xs outline-none focus:border-primary/40">
                  {(meta?.riskLevels ?? ["low", "medium"]).map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </Field>
            </div>

            <Field label="Instructions" hint="The step-by-step procedure. This is what the agent follows.">
              <textarea
                value={draft.instructions}
                onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
                rows={8}
                placeholder={"1. Retrieve the latest news for the instrument.\n2. Summarize the key facts.\n3. Cite every source."}
                className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 font-mono text-[11px] leading-relaxed outline-none focus:border-primary/40"
              />
            </Field>

            <Field label="Tags" hint="Comma-separated, optional.">
              <Input value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })}
                placeholder="earnings, summary" className="rounded-xl bg-background/60" />
            </Field>

            <Field label="Tools this skill may use" hint="Only these tools are available while the skill runs.">
              {meta ? (
                <div className="flex flex-wrap gap-1.5">
                  {meta.tools.map((tool) => (
                    <button key={tool} type="button" onClick={() => toggleTool(tool)}
                      className={cn("rounded-lg border px-2 py-1 text-[10px] font-mono cursor-pointer",
                        draft.requiredTools.includes(tool)
                          ? "border-primary/40 bg-primary/15 text-primary"
                          : "border-border/30 text-muted-foreground hover:text-foreground")}>
                      {tool}
                    </button>
                  ))}
                </div>
              ) : <p className="text-[10px] text-muted-foreground">Loading tools…</p>}
            </Field>

            <Field label="Permissions" hint="Limited to the safe, read-only set. Financial-execution permissions are never allowed.">
              <div className="flex flex-wrap gap-1.5">
                {(meta?.permissions ?? ["data.read", "research.read", "analysis.execute", "report.generate"]).map((permission) => (
                  <button key={permission} type="button" onClick={() => togglePermission(permission)}
                    className={cn("rounded-lg border px-2 py-1 text-[10px] cursor-pointer",
                      draft.permissions.includes(permission)
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border/30 text-muted-foreground hover:text-foreground")}>
                    {permission}
                  </button>
                ))}
              </div>
            </Field>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <Button size="sm" className="rounded-xl cursor-pointer" disabled={saving} onClick={submit}>
              {saving ? <Loader2 size={13} className="mr-1 animate-spin" /> : <Save size={13} className="mr-1" />}
              {isEdit ? "Save new version" : "Create skill"}
            </Button>
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={onClose}>Cancel</Button>
            {isEdit && <span className="text-[10px] text-muted-foreground">Saving creates a new version; the current one is preserved.</span>}
          </div>
        </div>
      </div>
    </div>
  );

  if (!mounted) return null;
  return createPortal(overlay, document.body);
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{label}</label>
      {hint && <p className="mt-0.5 mb-1.5 text-[10px] text-muted-foreground/80">{hint}</p>}
      {children}
    </div>
  );
}
