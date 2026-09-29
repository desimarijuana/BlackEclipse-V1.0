"use client";

// ── Execution Activity — skill runs and their traces ────────────────────────
// A readable trace view. Secrets are never part of a trace payload (the runtime
// redacts tool text), so nothing here leaks credentials.

import { useState } from "react";
import { Activity, AlertCircle, ChevronDown, ChevronRight, Loader2, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import type { SkillExecutionRecord } from "@/lib/harness/skills-types";
import { formatDuration, formatWhen, LoadingState, MetaRow, Panel } from "./skill-ui";

export interface ExecutionWithSkill extends SkillExecutionRecord {
  skillName?: string;
}

export function ExecutionActivity({
  executions,
  loading,
  error,
  onRefresh,
  onOpenSkill,
  onLearn,
  isOperator,
}: {
  executions: ExecutionWithSkill[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onOpenSkill: (skillId: string) => void;
  onLearn: (runId: string) => Promise<void>;
  isOperator: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const pagination = usePagination(executions, 25);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <Activity className="text-primary" size={22} />
          </span>
          <div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Execution Activity</h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-lg">
              Every skill run through the agent runtime — its mode, dependencies, tools, evidence and outcome.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl shrink-0" onClick={onRefresh} disabled={loading}>
          <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {loading ? (
        <LoadingState label="Loading execution activity…" />
      ) : error ? (
        <Panel className="p-8 text-center"><AlertCircle size={24} className="mx-auto text-rose-400" /><p className="mt-2 text-sm text-foreground">{error}</p></Panel>
      ) : executions.length === 0 ? (
        <Panel className="p-10 text-center">
          <Activity size={26} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">No executions yet</p>
          <p className="mt-1 text-[11px] text-muted-foreground">Run a skill from the library to see its trace here.</p>
        </Panel>
      ) : (
        <>
          <div className="space-y-2">
            {pagination.pageItems.map((execution) => {
            const expanded = open === execution.runId;
            return (
              <Panel key={execution.id}>
                <button
                  onClick={() => setOpen(expanded ? null : execution.runId)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 cursor-pointer hover:bg-accent/20 transition-colors text-left"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {expanded ? <ChevronDown size={14} className="text-muted-foreground shrink-0" /> : <ChevronRight size={14} className="text-muted-foreground shrink-0" />}
                    <span className="text-[11px] font-semibold text-foreground truncate">{execution.skillName ?? execution.skillId}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">v{execution.version}</span>
                    <span className="rounded-md bg-accent/40 px-1.5 py-0.5 text-[9px] text-muted-foreground">{execution.executionMode}</span>
                    {execution.parentRunId && (
                      <span className="rounded-md bg-violet-400/10 px-1.5 py-0.5 text-[9px] text-violet-300">child of {execution.parentRunId.slice(0, 12)}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[10px] text-muted-foreground">{formatDuration(execution.durationMs)}</span>
                    <span className={cn("text-[10px] font-bold uppercase", execution.status === "completed" ? "text-emerald-300" : execution.status === "running" ? "text-sky-300" : "text-rose-300")}>
                      {execution.status}
                    </span>
                    <span className="text-[10px] text-muted-foreground">{formatWhen(execution.createdAt)}</span>
                  </div>
                </button>

                {expanded && (
                  <div className="px-4 pb-4 border-t border-border/10">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                      <div>
                        <MetaRow label="Run ID"><span className="font-mono text-[10px]">{execution.runId}</span></MetaRow>
                        <MetaRow label="Trace ID"><span className="font-mono text-[10px]">{execution.traceId ?? "—"}</span></MetaRow>
                        <MetaRow label="Parent run"><span className="font-mono text-[10px]">{execution.parentRunId ?? "—"}</span></MetaRow>
                        <MetaRow label="Manifest hash"><span className="font-mono text-[10px]">{(execution.manifestHash ?? "—").slice(0, 12)}</span></MetaRow>
                        <MetaRow label="Output validated">
                          {execution.outputValidated === true ? (
                            <span className="text-[10px] font-semibold text-emerald-300">validated</span>
                          ) : execution.outputValidated === false ? (
                            <span className="text-[10px] font-semibold text-amber-300">not validated — see warnings</span>
                          ) : (
                            <span className="text-[10px] text-muted-foreground">not recorded</span>
                          )}
                        </MetaRow>
                        {execution.metrics && (
                          <MetaRow label="Execution">
                            <span className="text-[10px] text-muted-foreground">
                              {execution.metrics.toolCalls ?? 0} tool calls
                              {execution.metrics.toolErrors ? ` (${execution.metrics.toolErrors} errors)` : ""}
                              {" · "}
                              {execution.metrics.modelSteps ?? 0} steps
                              {typeof execution.metrics.totalTokens === "number" ? ` · ${execution.metrics.totalTokens} tokens` : ""}
                            </span>
                          </MetaRow>
                        )}
                        <MetaRow label="Actor">{execution.actor ?? "—"}</MetaRow>
                        <MetaRow label="Finished">{formatWhen(execution.finishedAt)}</MetaRow>
                        <button onClick={() => onOpenSkill(execution.skillId)} className="mt-2 text-[10px] text-primary hover:underline cursor-pointer">Open skill</button>
                      </div>
                      <div className="space-y-2">
                        {execution.error && (
                          <div className="rounded-xl border border-rose-400/30 bg-rose-400/5 p-2.5">
                            <p className="text-[9px] uppercase tracking-widest font-bold text-rose-300">Error</p>
                            <p className="mt-1 text-[11px] text-foreground">{execution.error.code}: {execution.error.message}</p>
                          </div>
                        )}
                        {execution.warnings && execution.warnings.length > 0 && <ListBlock title="Warnings" items={execution.warnings} tone="amber" />}
                        {execution.missingData && execution.missingData.length > 0 && <ListBlock title="Missing data" items={execution.missingData} tone="rose" />}
                        {execution.limitations && execution.limitations.length > 0 && <ListBlock title="Limitations" items={execution.limitations} tone="muted" />}
                        {execution.evidence && execution.evidence.length > 0 && (
                          <div>
                            <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Evidence ({execution.evidence.length})</p>
                            <ul className="mt-1 space-y-0.5">
                              {execution.evidence.slice(0, 8).map((item, index) => {
                                const record = item as Record<string, unknown>;
                                return <li key={index} className="text-[10px] text-muted-foreground truncate">{String(record.tool ?? "evidence")} · {formatWhen(record.at as string)}</li>;
                              })}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>

                    {execution.output && (
                      <details className="mt-3">
                        <summary className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground cursor-pointer">Output</summary>
                        <pre className="mt-2 max-h-[300px] overflow-auto rounded-xl border border-border/20 bg-background/40 p-3 text-[10px] text-muted-foreground whitespace-pre-wrap font-mono">{execution.output}</pre>
                      </details>
                    )}

                    <div className="mt-3">
                      <Button
                        variant="outline" size="sm" className="rounded-xl cursor-pointer"
                        disabled={!isOperator || busy === execution.runId || execution.status !== "completed"}
                        onClick={async () => { setBusy(execution.runId); try { await onLearn(execution.runId); } finally { setBusy(null); } }}
                      >
                        {busy === execution.runId ? <Loader2 size={13} className="mr-1 animate-spin" /> : null}
                        Learn from this run
                      </Button>
                      {!isOperator && <span className="ml-2 text-[10px] text-muted-foreground">requires operator</span>}
                    </div>
                  </div>
                )}
              </Panel>
            );
          })}
          </div>
          <PaginationFooter pagination={pagination} label="executions" />
        </>
      )}
    </div>
  );
}

function ListBlock({ title, items, tone }: { title: string; items: string[]; tone: "amber" | "rose" | "muted" }) {
  const color = tone === "amber" ? "text-amber-300" : tone === "rose" ? "text-rose-300" : "text-muted-foreground";
  return (
    <div>
      <p className={cn("text-[9px] uppercase tracking-widest font-bold", color)}>{title}</p>
      <ul className="mt-1 list-disc list-inside space-y-0.5">
        {items.map((item, index) => <li key={index} className="text-[10px] text-muted-foreground">{item}</li>)}
      </ul>
    </div>
  );
}
