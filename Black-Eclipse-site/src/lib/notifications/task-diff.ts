// ── Task completion diffing ─────────────────────────────────────────────────
// Pure helper for the global task watcher. The Python Task / Plan store owns
// the truth; the watcher polls GET /api/tasks and this module answers the only
// question that matters per poll: which tasks FINISHED since the last one?
//
// First sight of a task id is never a transition (it seeds the status map), so
// opening the app never replays completed history. A completion's notification
// id embeds `completedAt` (falling back to `updatedAt`), so a task that is
// reopened and completed again produces a NEW id and re-notifies.
//
// Kept framework-free and pure so it can be unit-tested without a DOM.

export type TaskStatus =
  | 'TODO' | 'IN_PROGRESS' | 'BLOCKED' | 'WAITING'
  | 'FAILED' | 'COMPLETED' | 'CANCELLED';

/** The subset of the runtime TaskNode this module reads. */
export interface WatchedTask {
  id: string;
  title: string;
  status: string;
  error?: string | null;
  completedAt?: string | null;
  updatedAt?: string | null;
}

export interface TaskNotification {
  /** Stable dedupe key: `task:<id>:<completedAt|updatedAt|status>`. */
  id: string;
  taskId: string;
  title: string;
  body: string;
  failed: boolean;
}

/** Build the status map from a full feed (used on the first poll). */
export function seedTaskStatuses(tasks: WatchedTask[]): Map<string, string> {
  const next = new Map<string, string>();
  for (const task of tasks) next.set(task.id, task.status);
  return next;
}

/**
 * Compare the current list against the previous status map and return the
 * notifications for tasks that reached a terminal state since the last poll,
 * plus the next status map (mirroring the current list, so deleted tasks and
 * out-of-window tasks are dropped rather than tracked forever).
 */
export function selectTaskTransitions(
  tasks: WatchedTask[],
  previous: Map<string, string>,
): { notifications: TaskNotification[]; next: Map<string, string> } {
  const notifications: TaskNotification[] = [];
  const next = new Map<string, string>();

  for (const task of tasks) {
    const prev = previous.get(task.id);
    next.set(task.id, task.status);
    if (prev === undefined || prev === task.status) continue;
    if (task.status !== 'COMPLETED' && task.status !== 'FAILED') continue;

    const stamp = task.completedAt || task.updatedAt || task.status;
    const failed = task.status === 'FAILED';
    notifications.push({
      id: `task:${task.id}:${stamp}`,
      taskId: task.id,
      title: failed ? 'Task failed' : 'Task completed',
      body: failed ? (task.error || task.title) : task.title,
      failed,
    });
  }

  return { notifications, next };
}
