import type { ActivityItem } from './response-model';

/**
 * Pure activity-list reducer.
 *
 * The normalizer emits deterministic logical ids (`retrieval:<source>:<type>`,
 * `tool:<name>`), and the same source/tool can run more than once in a single
 * run. Storing those ids directly would produce duplicate React keys — rows
 * would then duplicate or vanish. This reducer assigns each *instance* a unique
 * id while keeping a logical→instance stack so a start still correlates to its
 * matching end (LIFO), even when the same operation overlaps itself.
 *
 * Kept free of React so the correlation logic is unit-testable.
 */
export interface ActivityState {
  activities: ActivityItem[];
  /** Monotonic counter for instance ids. */
  seq: number;
  /** logical id → stack of live instance ids (most recent last). */
  live: Map<string, string[]>;
}

export function initialActivityState(): ActivityState {
  return { activities: [], seq: 0, live: new Map() };
}

function pushInstance(state: ActivityState, item: ActivityItem, logicalId: string): void {
  state.seq += 1;
  const instanceId = `${logicalId}#${state.seq}`;
  state.activities.push({ ...item, id: instanceId });
  const stack = state.live.get(logicalId) ?? [];
  stack.push(instanceId);
  state.live.set(logicalId, stack);
}

/** Add a running activity. */
export function startActivity(state: ActivityState, item: ActivityItem): ActivityState {
  pushInstance(state, item, item.id);
  return state;
}

export interface EndActivityInput {
  /** Logical id from the normalizer (absent for some runtime events). */
  id?: string;
  name: string;
  status: 'completed' | 'failed';
  durationMs?: number;
  code?: string;
  summary?: string;
}

/** Resolve the running activity this end refers to. */
export function endActivity(state: ActivityState, end: EndActivityInput): ActivityState {
  let idx = -1;

  // 1. Exact logical-id match via the LIFO instance stack.
  if (end.id) {
    const stack = state.live.get(end.id);
    if (stack && stack.length > 0) {
      const instanceId = stack[stack.length - 1];
      idx = state.activities.findIndex((a) => a.id === instanceId);
      if (idx !== -1) {
        stack.pop();
        if (stack.length === 0) state.live.delete(end.id);
      }
    }
  }

  // 2. Fallback: most recent still-running item with the same name.
  if (idx === -1) {
    for (let i = state.activities.length - 1; i >= 0; i -= 1) {
      const a = state.activities[i];
      if (a.name === end.name && a.status === 'running') {
        idx = i;
        break;
      }
    }
  }

  if (idx !== -1) {
    state.activities[idx] = {
      ...state.activities[idx],
      status: end.status,
      durationMs: end.durationMs ?? state.activities[idx].durationMs,
      code: end.code ?? state.activities[idx].code,
      summary: end.summary ?? state.activities[idx].summary,
    };
    return state;
  }

  // No matching start seen (e.g. joined mid-run): record a completed row with a
  // guaranteed-unique id.
  state.seq += 1;
  state.activities.push({
    id: `end:${end.name}#${state.seq}`,
    kind: 'tool',
    name: end.name,
    label: end.name,
    status: end.status,
    durationMs: end.durationMs,
    code: end.code,
    summary: end.summary,
  });
  return state;
}

/** True when every activity id in the list is unique (invariant for React keys). */
export function hasUniqueIds(activities: ActivityItem[]): boolean {
  return new Set(activities.map((a) => a.id)).size === activities.length;
}
