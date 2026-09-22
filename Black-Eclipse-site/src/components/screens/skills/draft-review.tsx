"use client";

// ── Draft Review — an unvalidated, generated skill ──────────────────────────
// Makes the unvalidated state visually obvious. Approve/reject require operator
// authorization; the server enforces it regardless.

import { useState } from "react";
import {
  AlertTriangle, CheckCircle2, FileWarning, Loader2, ShieldCheck, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SkillDetail } from "@/lib/harness/skills-types";
import { MetaRow, Panel, RiskBadge, SectionTitle } from "./skill-ui";

export function DraftReview({
  skill,
  isOperator,
  onEvaluate,
  onSubmitReview,
  onApprove,
  onReject,
}: {
  skill: SkillDetail;
  isOperator: boolean;
  onEvaluate: (skillId: string, version: string) => void;
  onSubmitReview: (skillId: string) => Promise<void>;
  onApprove: (skillId: string, requestId: string) => Promise<void>;
  onReject: (skillId: string, requestId: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const draft = skill as SkillDetail & { generationIssues?: string[]; knownLimitations?: string };
  const latestEvaluation = skill.evaluations[skill.evaluations.length - 1];
  const latestVersion = skill.latestVersion ?? skill.version;

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3 animate-fade-in-up">
      <Panel className="border-amber-400/30">
        <div className="flex items-start gap-3 p-4">
          <FileWarning size={20} className="text-amber-300 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-200">Unvalidated draft</p>
            <p className="mt-1 text-[11px] text-amber-100/80 leading-relaxed">
              This skill was generated from a learning candidate and has not been validated. It is inert —
              it cannot execute until it passes evaluation and an operator explicitly promotes it.
            </p>
          </div>
        </div>
      </Panel>

      <Panel>
        <div className="p-4">
          <SectionTitle icon={ShieldCheck} title="Proposed skill" />
          <MetaRow label="Skill ID"><span className="font-mono text-[10px]">{skill.id}</span></MetaRow>
          <MetaRow label="Name">{skill.name}</MetaRow>
          <MetaRow label="Version">{latestVersion}</MetaRow>
          <MetaRow label="Category">{skill.category}</MetaRow>
          <MetaRow label="Risk"><RiskBadge risk={skill.riskLevel} /></MetaRow>
          <MetaRow label="Required tools">{skill.requiredTools.length ? skill.requiredTools.join(", ") : "none"}</MetaRow>
          <MetaRow label="Permissions">{skill.permissions.join(", ") || "none"}</MetaRow>
          <MetaRow label="Source run"><span className="font-mono text-[10px]">{skill.sourceRunId ?? "—"}</span></MetaRow>
        </div>
      </Panel>

      <Panel>
        <div className="p-4">
          <SectionTitle icon={AlertTriangle} title="Generated limitations & issues" hint="Preserved from the source experience — promotion does not erase them." />
          {draft.knownLimitations && <p className="text-[11px] text-foreground leading-relaxed">{draft.knownLimitations}</p>}
          {(draft.generationIssues?.length ?? 0) > 0 && (
            <ul className="mt-2 list-disc list-inside space-y-0.5">
              {draft.generationIssues!.map((issue, index) => <li key={index} className="text-[10px] text-amber-300">{issue}</li>)}
            </ul>
          )}
          {skill.description && <p className="mt-2 text-[11px] text-muted-foreground">{skill.description}</p>}
        </div>
      </Panel>

      <Panel>
        <div className="p-4">
          <SectionTitle icon={CheckCircle2} title="Evaluation" />
          {latestEvaluation ? (
            <div>
              <div className="flex items-center gap-2">
                <span className={cn("text-[11px] font-semibold",
                  latestEvaluation.status === "passed" ? "text-emerald-300"
                  : latestEvaluation.status === "blocked" || latestEvaluation.status === "failed" ? "text-rose-300"
                  : "text-amber-300")}>
                  {latestEvaluation.status}
                </span>
                <span className="text-[10px] text-muted-foreground">{latestEvaluation.summary}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {latestEvaluation.dimensions.map((dimension) => (
                  <span key={dimension.name} className={cn(
                    "rounded-md px-1.5 py-0.5 text-[9px] font-semibold",
                    dimension.status === "passed" ? "bg-emerald-400/10 text-emerald-300"
                    : dimension.status === "failed" ? "bg-rose-400/10 text-rose-300"
                    : "bg-amber-400/10 text-amber-300"
                  )}>{dimension.name}{dimension.mandatory ? "*" : ""}</span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">Not evaluated yet. Run an evaluation before requesting promotion.</p>
          )}
        </div>
      </Panel>

      <Panel>
        <div className="p-4">
          <SectionTitle icon={ShieldCheck} title="Actions" />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={busy} onClick={() => onEvaluate(skill.id, latestVersion)}>
              Evaluate
            </Button>
            <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy} onClick={() => act(() => onSubmitReview(skill.id))}>
              {busy ? <Loader2 size={13} className="mr-1 animate-spin" /> : null} Submit for review
            </Button>
            <Button size="sm" className="rounded-xl cursor-pointer" disabled={!isOperator || busy} onClick={() => act(() => onApprove(skill.id, latestEvaluation?.id ?? ""))}>
              <CheckCircle2 size={13} className="mr-1" /> Approve (promote)
            </Button>
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer text-rose-300" disabled={!isOperator || busy} onClick={() => act(() => onReject(skill.id, latestEvaluation?.id ?? ""))}>
              <XCircle size={13} className="mr-1" /> Reject
            </Button>
          </div>
          {!isOperator && <p className="mt-2 text-[10px] text-amber-300/90">Read-only session — promotion requires operator authorization.</p>}
        </div>
      </Panel>
    </div>
  );
}
