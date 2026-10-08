// ── Execution Fabric view types + pure helpers ────────────────────────────────
// The typed surface over the Fabric admin API (`/api/fabric/*`). Pure helpers
// live here so the console stays presentational and the logic is unit-testable.

export type FabricJobStatus =
  | "CREATED"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "SUCCEEDED"
  | "FAILED"
  | "RETRYING"
  | "CANCEL_REQUESTED"
  | "CANCELLED"
  | "TIMED_OUT"
  | "DEAD_LETTER";

export interface FabricJobView {
  id: string;
  jobId: string;
  type: string;
  queue: string;
  status: FabricJobStatus;
  state: FabricJobStatus;
  priority: number;
  workerKind?: string | null;
  taskId?: string | null;
  parentJobId?: string | null;
  rootJobId?: string | null;
  agentId?: string | null;
  input?: Record<string, unknown>;
  output?: unknown;
  error?: string | null;
  errorClass?: string | null;
  progress: number;
  attempts: number;
  maxAttempts: number;
  durable?: boolean;
  correlationId?: string | null;
  createdAt: number;
  startedAt?: number | null;
  completedAt?: number | null;
  terminal: boolean;
  durationMs: number;
  metadata?: Record<string, unknown>;
}

export interface FabricJobEventView {
  id: string;
  jobId: string;
  seq: number;
  type: string;
  at: number;
  data: Record<string, unknown>;
}

export interface FabricJobAttemptView {
  id: string;
  jobId: string;
  attempt: number;
  workerId?: string | null;
  status: string;
  error?: string | null;
  errorClass?: string | null;
  startedAt: number;
  finishedAt?: number | null;
  durationMs: number;
}

export interface FabricQueueStat {
  queue: string;
  waiting: number;
  active: number;
  delayed: number;
  completed: number;
  failed: number;
  dlq: number;
  total: number;
}

export interface FabricWorkerView {
  id: string;
  kind: string;
  workerKind?: string;
  queue: string;
  status: string;
  concurrency: number;
  activeJobs: number;
  utilization: number;
  pid?: number | null;
}

export interface FabricMetricsView {
  uptimeSeconds: number;
  counters: Record<string, number>;
  latency: { samples: number; p50Ms: number; p95Ms: number; maxMs: number };
}

const TERMINAL: ReadonlySet<string> = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
  "DEAD_LETTER",
]);

export function isTerminalStatus(status: string): boolean {
  return TERMINAL.has(status);
}

/** A frosted-glass-compatible text tone for a job status. */
export function statusTone(status: string): string {
  switch (status) {
    case "SUCCEEDED":
      return "text-emerald-300";
    case "RUNNING":
    case "CANCEL_REQUESTED":
      return "text-sky-300";
    case "QUEUED":
    case "RETRYING":
    case "PAUSED":
      return "text-amber-300";
    case "FAILED":
    case "TIMED_OUT":
    case "DEAD_LETTER":
      return "text-red-300";
    case "CANCELLED":
      return "text-zinc-500";
    default:
      return "text-zinc-300";
  }
}

/** Human duration from milliseconds; honest about the zero case. */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

/** A compact progress/status label for a job row. */
export function jobProgressLabel(job: Pick<FabricJobView, "status" | "progress" | "attempts" | "maxAttempts">): string {
  if (job.status === "RUNNING") {
    return `${Math.round((job.progress || 0) * 100)}% · attempt ${job.attempts}/${job.maxAttempts}`;
  }
  if (job.status === "RETRYING" || job.status === "DEAD_LETTER") {
    return `attempt ${job.attempts}/${job.maxAttempts}`;
  }
  return job.status;
}

/** Roll a queue-stat list up into fleet totals (the Queues header). */
export function summarizeQueues(queues: FabricQueueStat[]): FabricQueueStat {
  return queues.reduce<FabricQueueStat>(
    (acc, q) => ({
      queue: "all",
      waiting: acc.waiting + q.waiting,
      active: acc.active + q.active,
      delayed: acc.delayed + q.delayed,
      completed: acc.completed + q.completed,
      failed: acc.failed + q.failed,
      dlq: acc.dlq + q.dlq,
      total: acc.total + q.total,
    }),
    { queue: "all", waiting: 0, active: 0, delayed: 0, completed: 0, failed: 0, dlq: 0, total: 0 },
  );
}

/** The queues that currently have any work, most-backed-up first. */
export function busiestQueues(queues: FabricQueueStat[]): FabricQueueStat[] {
  return [...queues]
    .filter((q) => q.total > 0)
    .sort((a, b) => b.waiting + b.active - (a.waiting + a.active));
}

export const PRIORITY_LABELS: Readonly<Record<number, string>> = {
  1000: "USER_REQUEST",
  900: "TRADING_ALERT",
  750: "AGENT_INTERACTIVE",
  500: "RESEARCH",
  250: "INGESTION",
  100: "MAINTENANCE",
};

export function priorityLabel(weight: number): string {
  if (PRIORITY_LABELS[weight]) return PRIORITY_LABELS[weight];
  const keys = Object.keys(PRIORITY_LABELS).map(Number).sort((a, b) => Math.abs(a - weight) - Math.abs(b - weight));
  return PRIORITY_LABELS[keys[0]] ?? String(weight);
}
