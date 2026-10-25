'use client';

// ── Run + version history ────────────────────────────────────────────────────
// The debugging surface for a saved workflow. Runs are read from the runtime
// (the summary endpoint; the full record is fetched before it is drawn) and
// versions from the immutable JDDS history. This panel NEVER invents a result:
// if a fetch fails it shows the error and keeps the previous list.

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { History, RefreshCw } from '@/lib/icons';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { getWorkflow, listVersions, type VersionSummary, type WorkflowRecord } from '@/lib/graph-studio/persistence-client';
import { getGraphRun, listWorkflowRuns, type GraphRunRecord } from '@/lib/graph-studio/execution-client';
import {
  formatDuration, formatTimestamp, shortHash, versionLabel,
} from '@/lib/graph-studio/history-model';

type Section = 'runs' | 'versions';

function RunStatusDot({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'h-1.5 w-1.5 shrink-0 rounded-full',
        status === 'running' ? 'bg-sky-400 animate-pulse'
          : status === 'queued' ? 'bg-slate-400'
          : status === 'succeeded' ? 'bg-emerald-400'
            : status === 'failed' ? 'bg-rose-400'
              : status === 'cancelled' ? 'bg-amber-400'
                : 'bg-slate-500',
      )}
    />
  );
}

export function HistoryPanel({
  workflowId,
  currentVersion,
  onOpenRun,
  onOpenVersion,
}: {
  workflowId: string | null;
  currentVersion?: number | null;
  onOpenRun: (run: GraphRunRecord) => void;
  onOpenVersion: (record: WorkflowRecord) => void;
}) {
  const dirty = useGraphEditor((s) => s.dirty);
  const [section, setSection] = useState<Section>('runs');
  const [runs, setRuns] = useState<GraphRunRecord[]>([]);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!workflowId) {
      setRuns([]);
      setVersions([]);
      return;
    }
    setLoading(true);
    try {
      const [nextRuns, nextVersions] = await Promise.all([
        listWorkflowRuns(workflowId),
        listVersions(workflowId),
      ]);
      setRuns(nextRuns);
      setVersions(nextVersions);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openRun = useCallback(async (runId: string) => {
    setOpening(runId);
    try {
      onOpenRun(await getGraphRun(runId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run');
    } finally {
      setOpening(null);
    }
  }, [onOpenRun]);

  const openVersion = useCallback(async (version: number) => {
    if (!workflowId) return;
    if (dirty && typeof window !== 'undefined' && !window.confirm('Discard unsaved changes and open this version?')) return;
    setOpening(`v${version}`);
    try {
      onOpenVersion(await getWorkflow(workflowId, version));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load version');
    } finally {
      setOpening(null);
    }
  }, [workflowId, dirty, onOpenVersion]);

  if (!workflowId) {
    return (
      <p className="px-3 py-3 text-[11px] leading-relaxed text-muted-foreground">
        Save this workflow to keep a run log and an immutable version history.
      </p>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/10 p-2">
        {([['runs', 'Runs'], ['versions', 'Versions']] as [Section, string][]).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSection(id)}
            className={cn(
              'flex-1 rounded-md px-2 py-1 text-[11px]',
              section === id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
            <span className="ml-1 text-[9.5px] text-muted-foreground">
              {id === 'runs' ? runs.length : versions.length}
            </span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          title="Refresh history"
          className="shrink-0 rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : undefined} />
        </button>
      </div>

      {error && (
        <p className="mx-2 mt-2 shrink-0 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading && runs.length === 0 && versions.length === 0 && (
          <p className="px-1 py-3 text-[11px] text-muted-foreground">Loading…</p>
        )}

        {section === 'runs' && (
          <>
            {!loading && runs.length === 0 && (
              <p className="px-1 py-3 text-[11px] leading-relaxed text-muted-foreground">
                No runs yet. A test run of the saved version will appear here with its node statuses and errors.
              </p>
            )}
            <ul className="space-y-1">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    disabled={opening === run.id}
                    onClick={() => void openRun(run.id)}
                    className="w-full rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5 text-left hover:bg-white/5 disabled:opacity-50"
                  >
                    <div className="flex items-center gap-1.5">
                      <RunStatusDot status={run.status} />
                      <span className="min-w-0 flex-1 truncate text-[11px] capitalize text-foreground">{run.status}</span>
                      <span className="shrink-0 text-[9.5px] text-muted-foreground">{formatDuration(run.durationMs)}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[9.5px] text-muted-foreground">
                      {formatTimestamp(run.startedAt)} · {run.mode}
                      {run.workflowVersion != null ? ` · v${run.workflowVersion}` : ''}
                      {` · ${run.testRun ? 'test' : 'operator'}`}
                    </div>
                    {run.error && <div className="mt-0.5 truncate text-[9.5px] text-rose-300">{run.error}</div>}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {section === 'versions' && (
          <>
            <p className="mb-2 px-1 text-[9.5px] leading-relaxed text-muted-foreground">
              Versions are immutable. Opening an old one loads it into the editor; saving appends a new version.
            </p>
            <ul className="space-y-1">
              {versions.map((version) => (
                <li key={version.version}>
                  <button
                    type="button"
                    disabled={opening === `v${version.version}`}
                    onClick={() => void openVersion(version.version)}
                    className="w-full rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5 text-left hover:bg-white/5 disabled:opacity-50"
                  >
                    <div className="flex items-center gap-1.5">
                      <History size={12} className="shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">
                        {versionLabel(version.version, currentVersion)}
                      </span>
                      <span className="shrink-0 font-mono text-[9px] text-muted-foreground">{shortHash(version.contentHash)}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[9.5px] text-muted-foreground">
                      {formatTimestamp(version.createdAt)}
                      {version.note ? ` · ${version.note}` : ''}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            {!loading && versions.length === 0 && (
              <p className="px-1 py-3 text-[11px] text-muted-foreground">No saved versions yet.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
