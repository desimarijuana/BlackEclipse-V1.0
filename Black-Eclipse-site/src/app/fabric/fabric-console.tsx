"use client";

// ── Execution Fabric Console ─────────────────────────────────────────────────
// Live observability over the Execution Fabric: queues, workers, jobs, the
// dead-letter queue and metrics. Talks to the Next proxy (`/api/fabric/*`),
// which forwards to the operator-gated Python admin API. Renders with the
// frosted-glass system.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  busiestQueues,
  formatDuration,
  jobProgressLabel,
  priorityLabel,
  statusTone,
  summarizeQueues,
  type FabricJobAttemptView,
  type FabricJobEventView,
  type FabricJobView,
  type FabricMetricsView,
  type FabricQueueStat,
  type FabricWorkerView,
} from "@/lib/harness/fabric-types";

type Tab = "queues" | "workers" | "jobs" | "dlq" | "metrics";

const inputClass =
  "rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-white/20";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/fabric${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: string }).error || `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return body as T;
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
        active ? "glass-card-strong text-foreground" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="glass-card-subtle rounded-xl p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-lg font-semibold ${tone ?? "text-foreground"}`}>{value}</div>
    </div>
  );
}

export function FabricConsole() {
  const [tab, setTab] = useState<Tab>("queues");
  const [error, setError] = useState<string | null>(null);
  const [queues, setQueues] = useState<FabricQueueStat[]>([]);
  const [workers, setWorkers] = useState<FabricWorkerView[]>([]);
  const [metrics, setMetrics] = useState<FabricMetricsView | null>(null);
  const [jobs, setJobs] = useState<FabricJobView[]>([]);
  const [dlq, setDlq] = useState<FabricJobView[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [queueFilter, setQueueFilter] = useState("");
  const [selected, setSelected] = useState<{ job: FabricJobView; events: FabricJobEventView[]; attempts: FabricJobAttemptView[] } | null>(null);

  const refreshQueues = useCallback(async () => {
    try {
      const [q, w, m] = await Promise.all([
        api<{ queues: FabricQueueStat[] }>("/queues"),
        api<{ workers: FabricWorkerView[] }>("/workers"),
        api<{ metrics: FabricMetricsView }>("/metrics"),
      ]);
      setQueues(q.queues ?? []);
      setWorkers(w.workers ?? []);
      setMetrics(m.metrics ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load the fabric");
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (queueFilter) params.set("queue", queueFilter);
      params.set("limit", "100");
      const body = await api<{ jobs: FabricJobView[] }>(`/jobs?${params.toString()}`);
      setJobs(body.jobs ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load jobs");
    }
  }, [statusFilter, queueFilter]);

  const refreshDlq = useCallback(async () => {
    try {
      const body = await api<{ deadLetters: FabricJobView[] }>("/dlq?limit=100");
      setDlq(body.deadLetters ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load the dead-letter queue");
    }
  }, []);

  useEffect(() => {
    void refreshQueues();
    const timer = setInterval(() => void refreshQueues(), 4000);
    return () => clearInterval(timer);
  }, [refreshQueues]);

  useEffect(() => {
    if (tab === "jobs") void refreshJobs();
    if (tab === "dlq") void refreshDlq();
  }, [tab, refreshJobs, refreshDlq]);

  const totals = useMemo(() => summarizeQueues(queues), [queues]);
  const busy = useMemo(() => busiestQueues(queues), [queues]);

  async function openJob(jobId: string) {
    try {
      const body = await api<{ job: FabricJobView; events: FabricJobEventView[]; attempts: FabricJobAttemptView[] }>(
        `/jobs/${encodeURIComponent(jobId)}`,
      );
      setSelected({ job: body.job, events: body.events ?? [], attempts: body.attempts ?? [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load the job");
    }
  }

  async function cancelJob(jobId: string) {
    try {
      await api(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      await Promise.all([refreshJobs(), refreshQueues(), openJob(jobId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not cancel the job");
    }
  }

  async function retryJob(jobId: string, replay = false) {
    const path = replay ? `/dlq/${encodeURIComponent(jobId)}/replay` : `/jobs/${encodeURIComponent(jobId)}/retry`;
    try {
      await api(path, { method: "POST" });
      await Promise.all([refreshJobs(), refreshDlq(), refreshQueues()]);
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not retry the job");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Execution Fabric</h1>
          <p className="text-xs text-muted-foreground">
            Durable queues, workers, retries, dead letters and execution modes.
          </p>
        </div>
        <button type="button" onClick={() => void refreshQueues()} className="glass-button rounded-lg px-3 py-1.5 text-xs">
          Refresh
        </button>
      </header>

      {error && (
        <div className="glass-card-subtle rounded-xl border border-red-500/30 p-2.5 text-xs text-red-300">{error}</div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <Metric label="Waiting" value={totals.waiting} tone="text-amber-300" />
        <Metric label="Active" value={totals.active} tone="text-sky-300" />
        <Metric label="Completed" value={totals.completed} tone="text-emerald-300" />
        <Metric label="Failed" value={totals.failed} tone="text-red-300" />
        <Metric label="Dead letters" value={totals.dlq} tone="text-red-300" />
        <Metric label="Workers" value={workers.length} />
      </div>

      <nav className="flex flex-wrap gap-1">
        {(["queues", "workers", "jobs", "dlq", "metrics"] as Tab[]).map((name) => (
          <TabButton key={name} active={tab === name} onClick={() => setTab(name)}>
            {name === "dlq" ? "Dead letters" : name.charAt(0).toUpperCase() + name.slice(1)}
          </TabButton>
        ))}
      </nav>

      {tab === "queues" && (
        <div className="glass-card rounded-xl p-4">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1">Queue</th>
                <th>Waiting</th><th>Active</th><th>Delayed</th>
                <th>Completed</th><th>Failed</th><th>DLQ</th><th>Total</th>
              </tr>
            </thead>
            <tbody>
              {busy.length === 0 && (
                <tr><td colSpan={8} className="py-3 text-muted-foreground">No queued work.</td></tr>
              )}
              {busy.map((q) => (
                <tr key={q.queue} className="border-t border-white/5">
                  <td className="py-1.5 font-medium text-foreground">{q.queue}</td>
                  <td className="text-amber-300">{q.waiting}</td>
                  <td className="text-sky-300">{q.active}</td>
                  <td>{q.delayed}</td>
                  <td className="text-emerald-300">{q.completed}</td>
                  <td className="text-red-300">{q.failed}</td>
                  <td className="text-red-300">{q.dlq}</td>
                  <td>{q.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "workers" && (
        <div className="glass-card rounded-xl p-4">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1">Worker</th><th>Kind</th><th>Queue</th><th>Status</th>
                <th>Active</th><th>Concurrency</th><th>Utilization</th><th>PID</th>
              </tr>
            </thead>
            <tbody>
              {workers.length === 0 && (
                <tr><td colSpan={8} className="py-3 text-muted-foreground">No workers running.</td></tr>
              )}
              {workers.map((w) => (
                <tr key={w.id} className="border-t border-white/5">
                  <td className="py-1.5 font-mono text-[11px] text-foreground">{w.id}</td>
                  <td>{w.kind}</td>
                  <td>{w.queue}</td>
                  <td className={statusTone(w.status === "BUSY" ? "RUNNING" : w.status === "IDLE" ? "SUCCEEDED" : w.status)}>{w.status}</td>
                  <td>{w.activeJobs}</td>
                  <td>{w.concurrency}</td>
                  <td>{Math.round((w.utilization ?? 0) * 100)}%</td>
                  <td className="text-muted-foreground">{w.pid ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "jobs" && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <input className={inputClass} placeholder="queue" value={queueFilter}
              onChange={(e) => setQueueFilter(e.target.value)} />
            <input className={inputClass} placeholder="status" value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)} />
            <button type="button" onClick={() => void refreshJobs()} className="glass-button rounded-lg px-3 py-1.5 text-xs">
              Apply
            </button>
          </div>
          <div className="glass-card rounded-xl p-4">
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1">Job</th><th>Type</th><th>Queue</th><th>Priority</th>
                  <th>Status</th><th>Progress</th><th>Duration</th><th />
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 && (
                  <tr><td colSpan={8} className="py-3 text-muted-foreground">No jobs.</td></tr>
                )}
                {jobs.map((job) => (
                  <tr key={job.jobId} className="border-t border-white/5 hover:bg-white/5">
                    <td className="py-1.5 font-mono text-[11px]">{job.jobId}</td>
                    <td>{job.type}</td>
                    <td>{job.queue}</td>
                    <td className="text-muted-foreground">{priorityLabel(job.priority)}</td>
                    <td className={statusTone(job.status)}>{job.status}</td>
                    <td>{jobProgressLabel(job)}</td>
                    <td>{formatDuration(job.durationMs)}</td>
                    <td className="space-x-2 text-right">
                      <button type="button" className="text-sky-300 hover:underline" onClick={() => void openJob(job.jobId)}>view</button>
                      {!job.terminal && (
                        <button type="button" className="text-red-300 hover:underline" onClick={() => void cancelJob(job.jobId)}>cancel</button>
                      )}
                      {job.status === "FAILED" || job.status === "TIMED_OUT" || job.status === "DEAD_LETTER" ? (
                        <button type="button" className="text-amber-300 hover:underline" onClick={() => void retryJob(job.jobId)}>retry</button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected && <JobDetail selected={selected} onClose={() => setSelected(null)} onCancel={cancelJob} onRetry={retryJob} />}
        </div>
      )}

      {tab === "dlq" && (
        <div className="glass-card rounded-xl p-4">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr><th className="py-1">Job</th><th>Type</th><th>Queue</th><th>Attempts</th><th>Error</th><th /></tr>
            </thead>
            <tbody>
              {dlq.length === 0 && (
                <tr><td colSpan={6} className="py-3 text-muted-foreground">The dead-letter queue is empty.</td></tr>
              )}
              {dlq.map((job) => (
                <tr key={job.jobId} className="border-t border-white/5">
                  <td className="py-1.5 font-mono text-[11px]">{job.jobId}</td>
                  <td>{job.type}</td>
                  <td>{job.queue}</td>
                  <td>{job.attempts}/{job.maxAttempts}</td>
                  <td className="max-w-[24rem] truncate text-red-300" title={job.error ?? ""}>
                    {job.errorClass ? `${job.errorClass}: ` : ""}{job.error ?? "—"}
                  </td>
                  <td className="text-right">
                    <button type="button" className="text-amber-300 hover:underline" onClick={() => void retryJob(job.jobId, true)}>replay</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "metrics" && (
        <div className="glass-card rounded-xl p-4">
          {metrics ? (
            <>
              <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric label="Uptime" value={formatDuration(metrics.uptimeSeconds * 1000)} />
                <Metric label="p50 latency" value={formatDuration(metrics.latency.p50Ms)} />
                <Metric label="p95 latency" value={formatDuration(metrics.latency.p95Ms)} />
                <Metric label="Samples" value={metrics.latency.samples} />
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {Object.entries(metrics.counters).map(([key, value]) => (
                  <Metric key={key} label={key} value={value} />
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Metrics unavailable.</p>
          )}
        </div>
      )}
    </div>
  );
}

function JobDetail({
  selected,
  onClose,
  onCancel,
  onRetry,
}: {
  selected: { job: FabricJobView; events: FabricJobEventView[]; attempts: FabricJobAttemptView[] };
  onClose: () => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  const { job, events, attempts } = selected;
  return (
    <div className="glass-card rounded-xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-mono text-xs text-foreground">{job.jobId}</div>
        <div className="flex gap-2">
          {!job.terminal && (
            <button type="button" className="glass-button rounded-lg px-2 py-1 text-xs text-red-300" onClick={() => onCancel(job.jobId)}>
              Cancel
            </button>
          )}
          {job.terminal && (
            <button type="button" className="glass-button rounded-lg px-2 py-1 text-xs text-amber-300" onClick={() => onRetry(job.jobId)}>
              Retry
            </button>
          )}
          <button type="button" className="glass-button rounded-lg px-2 py-1 text-xs" onClick={onClose}>Close</button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px] text-muted-foreground sm:grid-cols-4">
        <div>Type: <span className="text-foreground">{job.type}</span></div>
        <div>Queue: <span className="text-foreground">{job.queue}</span></div>
        <div>Status: <span className={statusTone(job.status)}>{job.status}</span></div>
        <div>Attempts: <span className="text-foreground">{job.attempts}/{job.maxAttempts}</span></div>
      </div>
      {job.error && <p className="mt-2 text-xs text-red-300">{job.errorClass ? `${job.errorClass}: ` : ""}{job.error}</p>}

      <h3 className="mt-4 text-[11px] uppercase tracking-wide text-muted-foreground">Timeline</h3>
      <ol className="mt-1 space-y-1 text-[11px]">
        {events.map((event) => (
          <li key={event.id} className="flex gap-2">
            <span className="w-16 shrink-0 text-muted-foreground">#{event.seq}</span>
            <span className="text-foreground">{event.type}</span>
          </li>
        ))}
        {events.length === 0 && <li className="text-muted-foreground">No events.</li>}
      </ol>

      <h3 className="mt-4 text-[11px] uppercase tracking-wide text-muted-foreground">Attempts</h3>
      <ol className="mt-1 space-y-1 text-[11px]">
        {attempts.map((attempt) => (
          <li key={attempt.id} className="flex gap-2">
            <span className="w-16 shrink-0 text-muted-foreground">#{attempt.attempt}</span>
            <span className={statusTone(attempt.status.toUpperCase())}>{attempt.status}</span>
            <span className="text-muted-foreground">{formatDuration(attempt.durationMs)}</span>
            {attempt.error && <span className="text-red-300">{attempt.error}</span>}
          </li>
        ))}
        {attempts.length === 0 && <li className="text-muted-foreground">No attempts recorded.</li>}
      </ol>
    </div>
  );
}
