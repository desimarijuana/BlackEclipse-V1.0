"use client";

// ── Guided Learn panel (Phase 4) ────────────────────────────────────────────
// Turn a run/document/repository/repeated-workflow/correction into a complete
// but INERT skill draft. The draft is schema-validated, linted (secrets, raw
// transcripts, issue numbers, dates flagged), and shown with its evidence and
// sanitization report. It cannot activate without evaluation + operator
// promotion.

import { useState } from "react";
import { GraduationCap, Loader2, ShieldAlert, WandSparkles } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { learnFromSource } from "@/lib/harness/clients/skills-browser";
import type { LearnDraftResult } from "@/lib/harness/skills-types";
import { PanelHeader } from "./skill-ui";

const SOURCE_KINDS = [
  { id: "run", label: "A run", hint: "A completed/failed run you want to make repeatable." },
  { id: "document", label: "A document", hint: "Paste or describe a document's procedure." },
  { id: "repository", label: "A repository", hint: "A workflow the repo's code/conventions embody." },
  { id: "repeated_workflow", label: "A repeated workflow", hint: "Something you do the same way every time." },
  { id: "correction", label: "A correction", hint: "A fix you keep applying after a mistake." },
] as const;

const LINT_LABEL: Record<string, string> = {
  raw_transcript: "looks like a raw transcript — capture the rule, not the log",
  secret: "contained a secret — removed",
  issue_number: "contained issue/PR numbers — removed",
  irrelevant_date: "contains an absolute date — prefer a relative rule",
  first_person: "written as incident narration — restate as a rule",
};

export function GuidedLearn({
  isOperator,
  onOpenDraft,
}: {
  isOperator: boolean;
  onOpenDraft: (skillId: string) => void;
}) {
  const [sourceKind, setSourceKind] = useState<typeof SOURCE_KINDS[number]["id"]>("run");
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [procedureText, setProcedureText] = useState("");
  const [sourceRunId, setSourceRunId] = useState("");
  const [toolsText, setToolsText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LearnDraftResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!title.trim()) { setError("A title is required."); return; }
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await learnFromSource({
        sourceKind, title: title.trim(), objective: objective.trim(),
        procedure: procedureText.split("\n").map((s) => s.trim()).filter(Boolean),
        sourceRunId: sourceRunId.trim() || undefined,
        tools: toolsText.split(/[,\n]/).map((s) => s.trim()).filter(Boolean),
      });
      setResult(res);
      if (!res.ok) setError(res.error ?? "draft generation failed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "learn failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="animate-fade-in-up">
      <PanelHeader
        icon={GraduationCap}
        title="Learn a skill"
        description="Turn something you already know into a reusable skill. The result is an inert draft: it must pass evaluation and operator promotion before it can run. Secrets, raw transcripts and issue numbers are stripped automatically."
      />

      <div className="mb-4 flex flex-wrap gap-1.5">
        {SOURCE_KINDS.map((kind) => (
          <button key={kind.id} onClick={() => setSourceKind(kind.id)} title={kind.hint}
            aria-pressed={sourceKind === kind.id}
            className={cn("rounded-lg px-2.5 py-1 text-[10px] font-semibold cursor-pointer",
              sourceKind === kind.id ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")}>
            {kind.label}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Skill title (a general rule, not an incident)" className="rounded-xl bg-background/60" />
        <textarea value={objective} onChange={(e) => setObjective(e.target.value)} rows={3}
          placeholder="What should this skill do? (objective / trigger conditions)" className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40" />
        <textarea value={procedureText} onChange={(e) => setProcedureText(e.target.value)} rows={4}
          placeholder="Procedure — one step per line (optional; derived from the objective if empty)" className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-[12px] outline-none focus:border-primary/40" />
        <div className="grid gap-2 md:grid-cols-2">
          <Input value={sourceRunId} onChange={(e) => setSourceRunId(e.target.value)} placeholder="Source run id (optional)" className="rounded-xl bg-background/60" />
          <Input value={toolsText} onChange={(e) => setToolsText(e.target.value)} placeholder="Tools (comma-separated, optional)" className="rounded-xl bg-background/60" />
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy} onClick={submit}>
          {busy ? <Loader2 size={13} className="mr-1 animate-spin" /> : <WandSparkles size={13} className="mr-1" />}
          Generate inert draft
        </Button>
      </div>

      {error && <p className="mt-3 text-[11px] text-rose-300">{error}</p>}

      {result?.ok && result.draft && (
        <div className="mt-5 rounded-2xl border border-emerald-400/25 glass-card p-4">
          <div className="flex items-center gap-2">
            <GraduationCap size={14} className="text-emerald-300" />
            <p className="text-[12px] font-semibold text-foreground">{result.draft.name}</p>
            <span className="rounded-full border border-slate-400/30 bg-slate-400/10 px-2 py-0.5 text-[9px] font-bold uppercase text-slate-300">draft · inert</span>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">{result.draft.description}</p>

          {(result.sanitized?.length || result.lint?.length) ? (
            <div className="mt-3 rounded-xl border border-amber-400/25 bg-amber-400/5 p-2.5">
              <p className="flex items-center gap-1 text-[10px] font-semibold text-amber-300"><ShieldAlert size={11} /> Content checks</p>
              <ul className="mt-1 space-y-0.5">
                {[...new Set([...(result.sanitized ?? []), ...(result.lint ?? [])])].map((code) => (
                  <li key={code} className="text-[10px] text-amber-200/90">{LINT_LABEL[code] ?? code}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-3 text-[10px] text-emerald-300/90">No secrets, transcripts, issue numbers or dates detected.</p>
          )}

          {result.issues && result.issues.length > 0 && (
            <ul className="mt-2 list-disc list-inside space-y-0.5">
              {result.issues.map((issue, i) => <li key={i} className="text-[10px] text-muted-foreground">{issue}</li>)}
            </ul>
          )}

          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={() => onOpenDraft(result.draft!.id)}>
              Review draft in library
            </Button>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground">
            This draft is inactive. It becomes usable only through the existing evaluation and operator promotion controls.
          </p>
        </div>
      )}
    </div>
  );
}
