"use client";

// ── Evaluation Center — evaluation runs and their dimensions ────────────────
// Multi-dimensional, never a single misleading score. Mandatory dimensions are
// marked; a blocked/failed mandatory dimension blocks promotion.

import { useEffect, useState } from "react";
import { AlertCircle, FlaskConical, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SkillEvaluationRecord, SkillSummary } from "@/lib/harness/skills-types";
import { EvalBadge, formatWhen, LoadingState, Panel } from "./skill-ui";

export function EvaluationCenter({
  skills,
  onOpenSkill,
}: {
  skills: SkillSummary[];
  isOperator: boolean;
  onOpenSkill: (skillId: string) => void;
}) {
  const [selected, setSelected] = useState<string>(skills[0]?.id ?? "");
  const [evaluations, setEvaluations] = useState<SkillEvaluationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && skills[0]) setSelected(skills[0].id);
  }, [skills, selected]);

  const load = async (skillId: string) => {
    if (!skillId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/skills/${encodeURIComponent(skillId)}/evaluations`);
      const body = (await res.json()) as { evaluations?: SkillEvaluationRecord[]; error?: string };
      if (!res.ok) throw new Error(body.error ?? "failed");
      setEvaluations(body.evaluations ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load evaluations");
      setEvaluations([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selected) return;
    void load(selected);
  }, [selected]);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <FlaskConical className="text-primary" size={22} />
          </span>
          <div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Evaluation Center</h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-lg">
              Deterministic, multi-dimensional evaluation. Mandatory checks block promotion; there is no single
              aggregate score.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl shrink-0" onClick={() => void load(selected)} disabled={loading}>
          <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      <div className="mb-4">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="w-full max-w-md rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-xs text-foreground outline-none focus:border-primary/40"
        >
          {skills.map((skill) => (
            <option key={skill.id} value={skill.id}>
              {skill.name} — v{skill.latestVersion ?? skill.version} ({skill.evaluationStatus})
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <LoadingState label="Loading evaluations…" />
      ) : error ? (
        <Panel className="p-8 text-center"><AlertCircle size={24} className="mx-auto text-rose-400" /><p className="mt-2 text-sm text-foreground">{error}</p></Panel>
      ) : evaluations.length === 0 ? (
        <Panel className="p-10 text-center">
          <FlaskConical size={26} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">No evaluations recorded</p>
          <p className="mt-1 text-[11px] text-muted-foreground">Open the skill and click Evaluate to run the deterministic suite.</p>
        </Panel>
      ) : (
        <div className="space-y-3">
          {evaluations.map((evaluation) => (
            <Panel key={evaluation.id} className="p-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-foreground">v{evaluation.version}</span>
                  <EvalBadge status={evaluation.status} />
                  <span className="text-[10px] text-muted-foreground">{evaluation.evaluator}</span>
                </div>
                <button onClick={() => onOpenSkill(evaluation.skillId)} className="text-[10px] text-primary hover:underline cursor-pointer">
                  {evaluation.skillId}
                </button>
              </div>
              {evaluation.summary && <p className="mt-2 text-[11px] text-muted-foreground">{evaluation.summary}</p>}
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                {evaluation.dimensions.map((dimension) => (
                  <div key={dimension.name} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-semibold text-foreground">
                        {dimension.name}{dimension.mandatory ? <span className="text-rose-300"> (mandatory)</span> : null}
                      </span>
                      <span className={cn(
                        "rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase",
                        dimension.status === "passed" ? "bg-emerald-400/10 text-emerald-300"
                        : dimension.status === "failed" ? "bg-rose-400/10 text-rose-300"
                        : "bg-amber-400/10 text-amber-300"
                      )}>{dimension.status.replace("_", " ")}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">{dimension.detail}</p>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground">Run {formatWhen(evaluation.createdAt)} · {evaluation.id}</p>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
