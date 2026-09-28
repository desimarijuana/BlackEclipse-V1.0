"use client";

// ── Skill quality over time (Phase 6) ───────────────────────────────────────
// Execution trends, sample-size honesty (a few runs are NOT reliable), failure
// causes, and same-case version comparison. Derived from real execution rows;
// never promotes or enables anything.

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, LineChart, Loader2 } from "lucide-react";
import { getSkillQuality } from "@/lib/harness/skills-browser";
import type { SkillQualityMetrics } from "@/lib/harness/skills-types";
import { MetaRow, Panel } from "./skill-ui";

export function SkillQualityPanel({ skillId, version }: { skillId: string; version?: string }) {
  const [metrics, setMetrics] = useState<SkillQualityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setMetrics(await getSkillQuality(skillId, version)); }
    catch (err) { setError(err instanceof Error ? err.message : "failed"); }
    finally { setLoading(false); }
  }, [skillId, version]);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="flex items-center gap-2 text-[11px] text-muted-foreground py-3"><Loader2 size={12} className="animate-spin" /> Loading quality…</div>;
  if (error) return <p className="text-[11px] text-rose-300">{error}</p>;
  if (!metrics || metrics.executions === 0) {
    return <p className="text-[11px] text-muted-foreground">No executions recorded yet — quality is unknown, not zero.</p>;
  }

  const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
  const causes = Object.entries(metrics.failureCauses).filter(([, n]) => n > 0);

  return (
    <div className="space-y-2">
      {metrics.sampleWarning && (
        <p className="flex items-center gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/10 px-2 py-1.5 text-[10px] text-amber-200">
          <AlertTriangle size={11} /> {metrics.sampleWarning}
        </p>
      )}
      <Panel className="p-3">
        <div className="flex items-center gap-2 mb-1"><LineChart size={12} className="text-primary" /><span className="text-[11px] font-semibold text-foreground">Execution quality</span></div>
        <MetaRow label="Executions">{metrics.executions} ({metrics.completed} completed, {metrics.failed} failed)</MetaRow>
        <MetaRow label="Success rate">
          {pct(metrics.successRate)}{metrics.successInterval ? ` · 95% CI ${pct(metrics.successInterval[0])}–${pct(metrics.successInterval[1])}` : ""}
          {metrics.sampleReliable ? "" : " · low sample"}
        </MetaRow>
        <MetaRow label="Recency-weighted success">{pct(metrics.timeWeightedSuccessRate)}</MetaRow>
        <MetaRow label="Output validation">{pct(metrics.outputValidationRate)}</MetaRow>
        <MetaRow label="Tool-budget failures">{pct(metrics.toolBudgetFailureRate)}</MetaRow>
        <MetaRow label="Mean duration">{metrics.meanDurationMs == null ? "—" : `${metrics.meanDurationMs}ms`}</MetaRow>
        <MetaRow label="Usefulness">{metrics.usefulness.score == null ? "unknown" : `${(metrics.usefulness.score * 100).toFixed(0)}%`} — {metrics.usefulness.reason}</MetaRow>
        {metrics.deprecation.recommend && (
          <MetaRow label="Recommendation">Consider deprecation — {metrics.deprecation.reason}</MetaRow>
        )}
      </Panel>

      {causes.length > 0 && (
        <Panel className="p-3">
          <p className="text-[11px] font-semibold text-foreground mb-1">Failure causes</p>
          <div className="flex flex-wrap gap-1.5">
            {causes.map(([cause, count]) => (
              <span key={cause} className="rounded-md border border-rose-400/25 bg-rose-400/10 px-1.5 py-0.5 text-[9px] text-rose-300">{cause} ×{count}</span>
            ))}
          </div>
        </Panel>
      )}

      {metrics.trend.length > 0 && (
        <Panel className="p-3">
          <p className="text-[11px] font-semibold text-foreground mb-1">Daily success trend (last {metrics.trend.length} days)</p>
          <div className="flex items-end gap-0.5 h-10">
            {metrics.trend.map((day) => (
              <div key={day.day} title={`${day.day}: ${day.completed}/${day.total}`}
                className="flex-1 rounded-sm bg-primary/60" style={{ height: `${Math.max(4, (day.successRate ?? 0) * 100)}%` }} />
            ))}
          </div>
          <p className="mt-1 text-[9px] text-muted-foreground">Bars show success rate per active day.</p>
        </Panel>
      )}
    </div>
  );
}
