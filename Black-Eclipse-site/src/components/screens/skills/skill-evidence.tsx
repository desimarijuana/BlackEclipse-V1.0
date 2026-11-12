"use client";

// ── Promotion evidence + version comparison ─────────────────────────────────
// Both panels are read-only projections of data the runtime already records.
// They exist so an operator can answer "is this version ready?" and "did the
// new version regress?" without leaving the skill. Neither promotes anything.

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeftRight, ArrowRight, ShieldCheck } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  compareSkillVersions, getSkillPromotionEvidence,
} from "@/lib/harness/clients/skills-browser";
import type {
  SkillPromotionEvidence, SkillQualityComparison, SkillQualityMetrics,
} from "@/lib/harness/skills-types";
import { ErrorState, formatDuration, LoadingState, MetaRow, Panel } from "./skill-ui";

const pct = (value: number | null | undefined) =>
  value == null ? "—" : `${(value * 100).toFixed(0)}%`;

function SampleNote({ metrics }: { metrics: SkillQualityMetrics }) {
  if (metrics.sampleReliable && !metrics.sampleWarning) return null;
  return (
    <p className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/10 px-2 py-1.5 text-[10px] text-amber-200">
      <AlertTriangle size={11} className="mt-0.5 shrink-0" />
      <span>
        {metrics.sampleWarning ?? "Small sample — treat this rate as provisional."}
        {" "}({metrics.executions} execution{metrics.executions === 1 ? "" : "s"})
      </span>
    </p>
  );
}

export function SkillPromotionEvidencePanel({
  skillId, version,
}: {
  skillId: string;
  version: string;
}) {
  const [evidence, setEvidence] = useState<SkillPromotionEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getSkillPromotionEvidence(skillId, version)
      .then((data) => { if (active) setEvidence(data); })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "failed to load evidence");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [skillId, version]);

  if (loading) return <LoadingState label="Loading promotion evidence…" />;
  if (error) return <ErrorState message={error} title="Evidence unavailable" />;
  if (!evidence) return <p className="text-[11px] text-muted-foreground">No evidence recorded.</p>;

  const metrics = evidence.executionMetrics;
  return (
    <div className="space-y-2">
      {!metrics.sampleReliable && <SampleNote metrics={metrics} />}
      <Panel className="p-3">
        <div className="mb-1 flex items-center gap-2">
          <ShieldCheck size={12} className="text-primary" />
          <span className="text-[11px] font-semibold text-foreground">
            Promotion evidence — v{evidence.version}
          </span>
          <span className={cn(
            "ml-auto rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
            evidence.evaluation?.status === "passed"
              ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
              : evidence.evaluation?.status
                ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                : "border-border/40 text-muted-foreground",
          )}>
            {evidence.evaluation?.status ?? "not evaluated"}
          </span>
        </div>
        {evidence.evaluation?.summary && (
          <p className="mb-1 text-[10px] text-muted-foreground">{evidence.evaluation.summary}</p>
        )}
        <MetaRow label="Executions">
          {metrics.executions} ({metrics.completed} completed, {metrics.failed} failed)
        </MetaRow>
        <MetaRow label="Success rate">
          {pct(metrics.successRate)}
          {metrics.successInterval
            ? ` · 95% CI ${pct(metrics.successInterval[0])}–${pct(metrics.successInterval[1])}`
            : ""}
        </MetaRow>
        <MetaRow label="Output validation">{pct(metrics.outputValidationRate)}</MetaRow>
        <MetaRow label="Usefulness">
          {evidence.usefulness.score == null
            ? "unknown"
            : pct(evidence.usefulness.score)}
          {` — ${evidence.usefulness.reason}`}
        </MetaRow>
        {evidence.deprecation.recommend && (
          <MetaRow label="Recommendation">Consider deprecation — {evidence.deprecation.reason}</MetaRow>
        )}
        <p className="mt-2 text-[10px] text-muted-foreground/80">{evidence.note}</p>
      </Panel>
    </div>
  );
}

export function SkillVersionComparisonPanel({
  skillId, versions, current,
}: {
  skillId: string;
  versions: string[];
  current: string;
}) {
  const candidates = versions.filter((version) => version !== current);
  const [older, setOlder] = useState(candidates[0] ?? "");
  const [result, setResult] = useState<SkillQualityComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOlder(candidates[0] ?? "");
    setResult(null);
    setError(null);
    // `candidates` is derived from props; compare by id/version, not identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId, current, versions.join(",")]);

  if (!candidates.length) {
    return (
      <p className="text-[11px] text-muted-foreground">
        Only one version exists — there is nothing to compare yet.
      </p>
    );
  }

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await compareSkillVersions(skillId, older, current));
    } catch (err) {
      setError(err instanceof Error ? err.message : "comparison failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-0.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
          Compare
          <select
            value={older}
            onChange={(e) => setOlder(e.target.value)}
            className="rounded-lg border border-border/30 bg-background/60 px-2 py-1 text-[11px] font-normal normal-case tracking-normal text-foreground outline-none focus:border-primary/40"
          >
            {candidates.map((version) => (
              <option key={version} value={version}>v{version}</option>
            ))}
          </select>
        </label>
        <span className="pb-1.5 text-[11px] text-muted-foreground">against</span>
        <span className="pb-1 text-[11px] font-semibold text-foreground">v{current}</span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto rounded-xl cursor-pointer"
          disabled={loading || !older}
          onClick={() => void run()}
        >
          <ArrowLeftRight size={13} className="mr-1" />
          {loading ? "Comparing…" : "Compare"}
        </Button>
      </div>

      {error && <p className="text-[10px] text-rose-300">{error}</p>}

      {result && (
        <Panel className="p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-foreground">
            <span>v{result.older}</span>
            <ArrowRight size={12} className="text-muted-foreground" />
            <span>v{result.newer}</span>
            <span className={cn(
              "ml-auto rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase",
              result.regressed
                ? "border-rose-400/30 bg-rose-400/10 text-rose-300"
                : "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
            )}>
              {result.regressed ? "regressed" : "no regressions"}
            </span>
          </div>

          <div className="mt-2 grid grid-cols-2 gap-x-4">
            <Metric label="Success" before={pct(result.before.successRate)} after={pct(result.after.successRate)} />
            <Metric label="Validated" before={pct(result.before.outputValidationRate)} after={pct(result.after.outputValidationRate)} />
            <Metric label="Executions" before={String(result.before.executions)} after={String(result.after.executions)} />
            <Metric label="Mean duration" before={formatDuration(result.before.meanDurationMs)} after={formatDuration(result.after.meanDurationMs)} />
          </div>

          {(!result.before.sampleReliable || !result.after.sampleReliable) && (
            <p className="mt-2 flex items-center gap-1 text-[10px] text-amber-200">
              <AlertTriangle size={11} /> Low sample on{" "}
              {result.lowSampleVersions.map((version) => `v${version}`).join(", ") || "one side"} — the comparison is provisional.
            </p>
          )}

          {result.regressions.length > 0 && (
            <div className="mt-2">
              <p className="text-[9px] uppercase tracking-widest font-bold text-rose-300">Regressions</p>
              <ul className="mt-1 list-disc list-inside space-y-0.5">
                {result.regressions.map((regression) => (
                  <li key={regression} className="text-[10px] text-foreground/80">{regression}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-2 flex flex-wrap gap-1.5 text-[9px] text-muted-foreground">
            <span>shared cases: {result.caseComparison.sharedCases.length}</span>
            <span>· added: {result.caseComparison.addedCases.length}</span>
            <span>· removed: {result.caseComparison.removedCases.length}</span>
            {result.caseComparison.caseRegressions.length > 0 && (
              <span className="text-rose-300">· case regressions: {result.caseComparison.caseRegressions.length}</span>
            )}
            {!result.caseComparison.comparable && <span>· case sets not comparable</span>}
          </div>
        </Panel>
      )}
    </div>
  );
}

function Metric({ label, before, after }: { label: string; before: string; after: string }) {
  const changed = before !== after;
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 py-1 text-[10px] last:border-0">
      <span className="uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      <span className={cn("font-mono", changed ? "text-foreground" : "text-muted-foreground")}>
        {before} → {after}
      </span>
    </div>
  );
}
