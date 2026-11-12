"use client";

// ── Execution Activity — skill runs and their traces ────────────────────────
// A readable trace view. Secrets are never part of a trace payload (the runtime
// redacts tool text), so nothing here leaks credentials.

import { useEffect, useState } from "react";
import { Activity, ChevronDown, ChevronRight, Loader2, RefreshCcw } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import { getSkillExecution } from "@/lib/harness/clients/skills-browser";
import type { SkillExecutionRecord } from "@/lib/harness/skills-types";
import { EmptyState, ErrorState, formatDuration, formatWhen, LoadingState, MetaRow, Panel, PanelHeader } from "./skill-ui";

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
  focusRunId,
  onClearFocus,
}: {
  executions: ExecutionWithSkill[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onOpenSkill: (skillId: string) => void;
  onLearn: (runId: string) => Promise<void>;
  isOperator: boolean;
  /** A run to open on arrival (deep link / "View run"). */
  focusRunId?: string | null;
  onClearFocus?: () => void;
}) {
  const [open, setOpen] = useState<string | null>(focusRunId ?? null);
  const [busy, setBusy] = useState<string | null>(null);
  // A run older than the list window still has to be viewable.
  const [fetched, setFetched] = useState<ExecutionWithSkill | null>(null);
  const [focusError, setFocusError] = useState<string | null>(null);

  const inList = Boolean(focusRunId && executions.some((e) => e.runId === focusRunId));

  useEffect(() => {
    setOpen(focusRunId ?? null);
    if (!focusRunId || inList) {
      setFetched(null);
      setFocusError(null);
      return;
    }
    let active = true;
    setFocusError(null);
    getSkillExecution(focusRunId)
      .then((record) => {
        if (!active) return;
        if (record) setFetched(record);
        else setFocusError(`Run ${focusRunId} was not found.`);
      })
      .catch((err) => {
        if (active) setFocusError(err instanceof Error ? err.message : "could not load run");
      });
    return () => { active = false; };
  }, [focusRunId, inList]);

  const rows: ExecutionWithSkill[] =
    focusRunId && fetched && !inList ? [fetched, ...executions] : executions;
  const pagination = usePagination(rows, 25);

  return (
    <div className="animate-fade-in-up">
      <PanelHeader
        icon={Activity}
        title="Execution Activity"
        description="Every skill run through the agent runtime — its mode, dependencies, tools, evidence and outcome."
        actions={
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl shrink-0" onClick={onRefresh} disabled={loading}>
            <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
          </Button>
        }
      />

      {loading ? (
        <LoadingState label="Loading execution activity…" />
      ) : error ? (
        <ErrorState message={error} />
      ) : focusError ? (
        <ErrorState message={focusError} title="Run not found" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No executions yet"
          hint="Run a skill from the library to see its trace here."
        />
      ) : (
        <>
          <div className="space-y-2">
            {pagination.pageItems.map((execution) => {
            const expanded = open === execution.runId;
            return (
              <Panel
                key={execution.id}
                className={cn(execution.runId === focusRunId && "ring-1 ring-primary/40")}
              >
                <button
                  onClick={() => {
                    setOpen(expanded ? null : execution.runId);
                    if (expanded && execution.runId === focusRunId) onClearFocus?.();
                  }}
                  aria-expanded={expanded}
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
