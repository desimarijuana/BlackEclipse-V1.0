"use client";

// ── Settings › Analytics ──────────────────────────────────────────────────
// Token-consumption analytics for the agent runtime, read straight from the
// runtime's `agent-memory.db` via `GET /api/harness/usage`.
//
// Honesty rule (this is a financial product): providers do not all report a
// usage block. Local Ollama/LM Studio servers commonly omit it. Rather than
// inventing a number, the panel shows the real totals and, when some runs had
// no usage reported, states that explicitly. `totals.runsWithUsage` is the
// signal that makes the distinction possible.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, BarChart3, Coins, Cpu, Loader2, RefreshCcw, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { UsageSummary } from "@/lib/harness/types";

const WINDOWS = [7, 30, 90] as const;

function compact(n: number): string {
  if (!Number.isFinite(n)) return "UNAVAILABLE";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`;
  return n.toLocaleString();
}

function Panel({ className, children, ...rest }: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)} {...rest}>
      {children}
    </div>
  );
}

function StatTile({ icon: Icon, label, value, sub }: { icon: React.ElementType; label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border/20 glass-card-subtle p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon size={13} className="text-primary shrink-0" />
        <span className="text-[10px] uppercase tracking-widest font-bold">{label}</span>
      </div>
      <p className="mt-2 font-serif text-2xl font-semibold tracking-tight text-foreground tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-[10px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function AnalyticsSettingsPanel() {
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (window: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/harness/usage?days=${window}`);
      const body = (await res.json()) as UsageSummary & { error?: string };
      if (!res.ok) {
        setError(body.error ?? "Failed to load usage analytics");
        setData(null);
        return;
      }
      setData(body);
    } catch {
      setError("Failed to reach the analytics endpoint");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(days);
  }, [days, load]);

  const totals = data?.totals;
  const peakDay = useMemo(() => Math.max(1, ...(data?.byDay ?? []).map((d) => d.totalTokens)), [data]);
  const unreported = totals && totals.runs > 0 && totals.runsWithUsage < totals.runs;

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <BarChart3 className="text-primary" size={22} />
          </span>
          <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Token Analytics</h2>
        </div>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
          Real token consumption recorded by the agent runtime for every agent run. Providers that
          do not report usage are shown honestly rather than estimated.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 mb-4">
        <Select value={String(days)} onValueChange={(v) => setDays(Number(v ?? "30"))}>
          <SelectTrigger className="h-8 w-[140px] text-[11px] rounded-xl">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOWS.map((w) => (
              <SelectItem key={w} value={String(w)}>{`Last ${w} days`}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          className="cursor-pointer rounded-xl"
          onClick={() => void load(days)}
          disabled={loading}
        >
          <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {error ? (
        <Panel className="p-8 text-center">
          <AlertCircle className="mx-auto text-rose-400 w-7 h-7 mb-3" />
          <p className="text-xs text-muted-foreground">{error}</p>
          <p className="text-[10px] text-muted-foreground/70 mt-2">
            Analytics require the Python agent runtime. Install it with <span className="font-mono">npm run setup:python</span>.
          </p>
        </Panel>
      ) : loading && !data ? (
        <Panel className="p-8 flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">Loading usage…</span>
        </Panel>
      ) : totals && totals.runs === 0 ? (
        <Panel className="p-8 text-center">
          <Activity className="mx-auto text-muted-foreground w-8 h-8 mb-3" />
          <p className="text-xs text-muted-foreground">
            No agent runs in the last {days} days. Token usage appears here after the first run.
          </p>
        </Panel>
      ) : totals ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile
              icon={Coins}
              label="Total tokens"
              value={compact(totals.totalTokens)}
              sub={`${compact(totals.promptTokens)} in · ${compact(totals.completionTokens)} out`}
            />
            <StatTile
              icon={Activity}
              label="Runs"
              value={compact(totals.runs)}
              sub={`${totals.completed} completed · ${totals.failed} failed`}
            />
            <StatTile
              icon={Cpu}
              label="Model steps"
              value={compact(totals.modelSteps)}
              sub={totals.runs > 0 ? `${(totals.modelSteps / totals.runs).toFixed(1)} avg / run` : undefined}
            />
          </div>

          {unreported && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {totals.runs - totals.runsWithUsage} of {totals.runs} runs did not report token usage
                (common for local providers such as Ollama or LM Studio). Those runs are counted but
                contribute 0 tokens — the totals above are not estimates.
              </p>
            </div>
          )}

          <Panel>
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/10">
              <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Daily consumption</span>
              <span className="text-[10px] text-muted-foreground font-mono">peak {compact(peakDay)}</span>
            </div>
            {(data?.byDay.length ?? 0) === 0 ? (
              <p className="px-5 py-6 text-[11px] text-muted-foreground text-center">No daily data in this window.</p>
            ) : (
              <div className="px-5 py-5">
                <div className="flex items-end gap-1 h-32">
                  {data!.byDay.map((d) => (
                    <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group min-w-0">
                      <div
                        className="w-full rounded-t-md bg-primary/40 group-hover:bg-primary/70 transition-colors"
                        style={{ height: `${Math.max(2, (d.totalTokens / peakDay) * 100)}%` }}
                        title={`${d.date}: ${d.totalTokens.toLocaleString()} tokens · ${d.runs} run(s)`}
                      />
                    </div>
                  ))}
                </div>
                <div className="flex justify-between mt-2 text-[9px] text-muted-foreground font-mono">
                  <span>{data!.byDay[0]?.date}</span>
                  <span>{data!.byDay[data!.byDay.length - 1]?.date}</span>
                </div>
              </div>
            )}
          </Panel>

          <Panel>
            <div className="px-5 py-3.5 border-b border-border/10">
              <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">By model</span>
            </div>
            <div className="divide-y divide-border/10">
              {data!.byModel.length === 0 ? (
                <p className="px-5 py-6 text-[11px] text-muted-foreground text-center">No model activity.</p>
              ) : (
                data!.byModel.map((m) => (
                  <div key={`${m.provider}:${m.model}`} className="flex items-center justify-between gap-3 px-5 py-3.5">
                    <div className="min-w-0">
                      <span className="text-xs font-medium text-foreground block truncate">{m.model}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">{m.provider} · {m.runs} run(s)</span>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-xs font-semibold text-foreground tabular-nums block">{compact(m.totalTokens)}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">{compact(m.promptTokens)} in · {compact(m.completionTokens)} out</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Panel>

          <Panel>
            <div className="px-5 py-3.5 border-b border-border/10 flex items-center gap-2">
              <Wrench size={12} className="text-primary" />
              <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Recent runs</span>
            </div>
            <div className="divide-y divide-border/10">
              {data!.recent.length === 0 ? (
                <p className="px-5 py-6 text-[11px] text-muted-foreground text-center">No runs yet.</p>
              ) : (
                data!.recent.map((r) => (
                  <div key={r.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="min-w-0">
                      <span className="text-[11px] text-foreground block truncate">{r.model ?? "—"}</span>
                      <span className="text-[9px] text-muted-foreground font-mono">
                        {r.agentId} · {r.toolCalls} tool(s){r.toolErrors > 0 ? ` · ${r.toolErrors} err` : ""} · {new Date(r.createdAt).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-right shrink-0">
                      <span className={cn("text-[11px] font-semibold tabular-nums block", r.totalTokens > 0 ? "text-foreground" : "text-muted-foreground/60")}>
                        {r.totalTokens > 0 ? compact(r.totalTokens) : "not reported"}
                      </span>
                      <span className={cn("text-[9px] font-mono", r.status === "completed" ? "text-primary" : r.status === "failed" ? "text-rose-400" : "text-muted-foreground")}>
                        {r.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}
