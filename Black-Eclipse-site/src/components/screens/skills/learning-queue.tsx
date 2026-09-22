"use client";

// ── Learning Queue — captured lessons awaiting review ───────────────────────
// Candidates are inert: the UI can generate a draft, reject, or open the source
// run. It can never publish a skill directly.

import { useState } from "react";
import {
  AlertCircle, FileText, Lightbulb, Loader2, RefreshCcw, ShieldCheck, ThumbsDown, WandSparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { LearningCandidate } from "@/lib/harness/skills-types";
import { formatWhen, Panel } from "./skill-ui";

const TYPE_LABEL: Record<string, string> = {
  failure_recovery: "Failure recovery",
  user_correction: "User correction",
  successful_procedure: "Successful procedure",
  validation_improvement: "Validation improvement",
  source_selection_improvement: "Source selection",
  workflow_pattern: "Workflow pattern",
  terminology_or_preference: "Preference",
};

export function LearningQueue({
  candidates,
  loading,
  error,
  isOperator,
  onRefresh,
  onGenerateDraft,
  onReject,
  onOpenRun,
  onOpenDraft,
}: {
  candidates: LearningCandidate[];
  loading: boolean;
  error: string | null;
  isOperator: boolean;
  onRefresh: () => void;
  onGenerateDraft: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  onOpenRun: (runId: string) => void;
  onOpenDraft: (skillId: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  const act = async (id: string, fn: (id: string) => Promise<void>) => {
    setBusy(id);
    try { await fn(id); } finally { setBusy(null); }
  };

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <Lightbulb className="text-primary" size={22} />
          </span>
          <div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Learning Queue</h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-lg">
              Reusable lessons captured from execution traces. A candidate is an observation, not a skill — nothing
              here is active until evaluated and explicitly promoted.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl shrink-0" onClick={onRefresh} disabled={loading}>
          <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {!isOperator && (
        <p className="mb-4 flex items-center gap-1 text-[10px] text-amber-300/90">
          <ShieldCheck size={11} /> Read-only session — generating drafts and rejecting require operator authorization.
        </p>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" size={16} /> Loading…</div>
      ) : error ? (
        <Panel className="p-8 text-center">
          <AlertCircle size={24} className="mx-auto text-rose-400" />
          <p className="mt-2 text-sm text-foreground">{error}</p>
        </Panel>
      ) : candidates.length === 0 ? (
        <Panel className="p-10 text-center">
          <Lightbulb size={26} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">No learning candidates</p>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">
            Use “Learn from this run” on a completed execution to capture a reusable lesson.
          </p>
        </Panel>
      ) : (
        <div className="space-y-3">
          {candidates.map((candidate) => (
            <Panel key={candidate.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-foreground">{candidate.title}</span>
                    <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-primary">
                      {TYPE_LABEL[candidate.candidateType] ?? candidate.candidateType}
                    </span>
                    <span className={cn(
                      "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide",
                      candidate.status === "new" ? "border-sky-400/30 bg-sky-400/10 text-sky-300"
                      : candidate.status === "rejected" ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                      : candidate.status === "drafted" ? "border-violet-400/30 bg-violet-400/10 text-violet-300"
                      : "border-border/40 text-muted-foreground"
                    )}>
                      {candidate.status}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[11px] text-muted-foreground leading-relaxed">{candidate.problem}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-[10px] text-muted-foreground">confidence</p>
                  <p className="font-serif text-lg font-semibold text-foreground tabular-nums">{(candidate.confidence * 100).toFixed(0)}%</p>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="Proposed lesson" value={candidate.proposedLesson} />
                <Field label="Observed behaviour" value={candidate.observedBehavior} />
                <Field label="Known limitations" value={candidate.knownLimitations} />
                <Field label="Generalization" value={candidate.generalizationNotes} />
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-[10px] text-muted-foreground">Source run: {candidate.sourceRunId ?? "—"}</span>
                <span className="text-[10px] text-muted-foreground">· {formatWhen(candidate.createdAt)}</span>
                <span className="text-[10px] text-muted-foreground">· {candidate.evidenceReferences.length} evidence ref(s)</span>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm" className="rounded-xl cursor-pointer"
                  disabled={!isOperator || busy === candidate.id || candidate.status === "rejected"}
                  onClick={() => act(candidate.id, onGenerateDraft)}
                >
                  {busy === candidate.id ? <Loader2 size={13} className="mr-1 animate-spin" /> : <WandSparkles size={13} className="mr-1" />}
                  Generate draft
                </Button>
                <Button
                  variant="outline" size="sm" className="rounded-xl cursor-pointer text-rose-300"
                  disabled={!isOperator || busy === candidate.id || candidate.status === "rejected"}
                  onClick={() => act(candidate.id, onReject)}
                >
                  <ThumbsDown size={13} className="mr-1" /> Reject
                </Button>
                {candidate.sourceRunId && (
                  <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => onOpenRun(candidate.sourceRunId!)}>
                    View run
                  </Button>
                )}
                {candidate.resultingSkillId && (
                  <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => onOpenDraft(candidate.resultingSkillId!)}>
                    <FileText size={13} className="mr-1" /> Open draft
                  </Button>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-xl border border-border/20 bg-background/30 p-2.5">
      <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      <p className="mt-1 text-[11px] text-foreground leading-relaxed">{value || "—"}</p>
    </div>
  );
}
