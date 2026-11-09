"use client";

// ── Evaluation Center — evaluation runs and their dimensions ────────────────
// Multi-dimensional, never a single misleading score. Mandatory dimensions are
// marked; a blocked/failed mandatory dimension blocks promotion.

import { useEffect, useMemo, useState } from "react";
import { FlaskConical, RefreshCcw, Search } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import type { SkillEvaluationRecord, SkillSummary } from "@/lib/harness/skills-types";
import { listSkillEvaluations } from "@/lib/harness/skills-browser";
import { EmptyState, ErrorState, EvalBadge, formatWhen, LoadingState, Panel, PanelHeader } from "./skill-ui";

export function EvaluationCenter({
  skills,
  onOpenSkill,
}: {
  skills: SkillSummary[];
  onOpenSkill: (skillId: string) => void;
}) {
  const [selected, setSelected] = useState<string>(skills[0]?.id ?? "");
  const [evaluations, setEvaluations] = useState<SkillEvaluationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const pagination = usePagination(evaluations, 10);

  // A 90+ option <select> is unusable without a filter. Match on id/name/
  // category and always keep the current selection visible.
  const pickerSkills = useMemo(() => {
    const terms = pickerQuery.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return skills;
    const matched = skills.filter((skill) => {
      const hay = `${skill.id} ${skill.name} ${skill.category}`.toLowerCase();
      return terms.every((term) => hay.includes(term));
    });
    const current = skills.find((skill) => skill.id === selected);
    if (current && !matched.some((skill) => skill.id === selected)) {
      return [current, ...matched];
    }
    return matched;
  }, [skills, pickerQuery, selected]);

  useEffect(() => {
    if (!selected && skills[0]) setSelected(skills[0].id);
  }, [skills, selected]);

  const load = async (skillId: string) => {
    if (!skillId) return;
    setLoading(true);
    setError(null);
    try {
      setEvaluations(await listSkillEvaluations(skillId));
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
      <PanelHeader
        icon={FlaskConical}
        title="Evaluation Center"
        description="Deterministic, multi-dimensional evaluation. Mandatory checks block promotion; there is no single aggregate score."
        actions={
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl shrink-0" onClick={() => void load(selected)} disabled={loading}>
            <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
          </Button>
        }
      />

      <div className="mb-4 max-w-md space-y-1.5">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={pickerQuery}
            onChange={(e) => setPickerQuery(e.target.value)}
            placeholder="Filter skills by name, id or category…"
            className="rounded-xl bg-background/60 pl-9"
          />
        </div>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          aria-label="Skill to evaluate"
          className="w-full rounded-xl border border-border/30 bg-background/60 px-3 py-2 text-xs text-foreground outline-none focus:border-primary/40"
        >
          {pickerSkills.length === 0 ? (
            <option value={selected}>No matching skills</option>
          ) : (
            pickerSkills.map((skill) => (
              <option key={skill.id} value={skill.id}>
                {skill.name} — v{skill.latestVersion ?? skill.version} ({skill.evaluationStatus})
              </option>
            ))
          )}
        </select>
        <p className="text-[10px] text-muted-foreground">
          {pickerSkills.length} of {skills.length} skills
        </p>
      </div>

      {loading ? (
        <LoadingState label="Loading evaluations…" />
      ) : error ? (
        <ErrorState message={error} />
      ) : evaluations.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="No evaluations recorded"
          hint="Open the skill and click Evaluate to run the deterministic suite."
        />
      ) : (
        <>
        <div className="space-y-3">
          {pagination.pageItems.map((evaluation) => (
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
        <PaginationFooter pagination={pagination} label="evaluations" />
        </>
      )}
    </div>
  );
}
