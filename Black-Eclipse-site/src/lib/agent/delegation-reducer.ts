import type { DelegationChildView, DelegationView } from './response-model';
import type { HarnessUiEvent } from './events';

/**
 * Pure reducer for the parallel fan-out card.
 *
 * Kept free of React so the merge rules are unit-testable. The rules that
 * matter:
 *  - one row per `childIndex` (a later snapshot UPDATES, never duplicates);
 *  - a terminal state is never downgraded back to `running` by a late frame;
 *  - a goal already known is not erased by a snapshot that omits it;
 *  - a fan-out whose `started` frame was missed still appears from progress.
 */

type DelegationEvent = Extract<
  HarnessUiEvent,
  {
    kind:
      | 'delegation_start'
      | 'delegation_progress'
      | 'delegation_child'
      | 'delegation_done';
  }
>;

const TERMINAL_STATUSES = new Set<DelegationChildView['status']>([
  'completed', 'failed', 'refused', 'timed_out', 'cancelled',
]);

function isTerminal(status: DelegationChildView['status']): boolean {
  return TERMINAL_STATUSES.has(status);
}

function sortChildren(children: DelegationChildView[]): DelegationChildView[] {
  return [...children].sort((a, b) => a.childIndex - b.childIndex);
}

/** Merge one child snapshot into the existing row, honouring the rules above. */
export function mergeChild(
  previous: DelegationChildView | undefined,
  incoming: DelegationChildView,
): DelegationChildView {
  if (!previous) return incoming;
  const status =
    isTerminal(previous.status) && !isTerminal(incoming.status)
      ? previous.status
      : incoming.status;
  return {
    ...previous,
    ...incoming,
    goal: incoming.goal || previous.goal,
    status,
  };
}

function updateChild(
  delegation: DelegationView,
  child: DelegationChildView,
): DelegationView {
  const existing = delegation.children.find((c) => c.childIndex === child.childIndex);
  const merged = mergeChild(existing, child);
  const children = existing
    ? delegation.children.map((c) => (c.childIndex === child.childIndex ? merged : c))
    : [...delegation.children, merged];
  return { ...delegation, children: sortChildren(children) };
}

function upsertDelegation(
  state: DelegationView[],
  delegationId: string,
  create: () => DelegationView,
): { list: DelegationView[]; target: DelegationView } {
  const existing = state.find((d) => d.delegationId === delegationId);
  if (existing) return { list: state, target: existing };
  const target = create();
  return { list: [...state, target], target };
}

export function applyDelegationEvent(
  state: DelegationView[],
  event: DelegationEvent,
): DelegationView[] {
  if (event.kind === 'delegation_start') {
    const incoming = event.delegation;
    const existing = state.find((d) => d.delegationId === incoming.delegationId);
    if (!existing) return [...state, incoming];
    // A second start for the same id (resume) keeps known rows and their state.
    const children = incoming.children.reduce(
      (acc, child) => updateChild({ ...existing, children: acc }, child).children,
      existing.children,
    );
    return state.map((d) =>
      d.delegationId === incoming.delegationId
        ? { ...d, aggregate: incoming.aggregate, children }
        : d,
    );
  }

  if (event.kind === 'delegation_progress') {
    const { delegationId, ...child } = event.child;
    const { list, target } = upsertDelegation(state, delegationId, () => ({
      delegationId,
      aggregate: 'list',
      strategy: 'split',
      children: [],
      done: false,
    }));
    const updated = updateChild(target, child);
    const found = list.some((d) => d.delegationId === delegationId);
    return found
      ? list.map((d) => (d.delegationId === delegationId ? updated : d))
      : [...list, updated];
  }

  if (event.kind === 'delegation_child') {
    const { delegationId, childIndex, status, tokens, reason } = event;
    const { list, target } = upsertDelegation(state, delegationId, () => ({
      delegationId,
      aggregate: 'list',
      strategy: 'split',
      children: [],
      done: false,
    }));
    const updated = updateChild(target, {
      childIndex,
      goal: '',
      status,
      ...(tokens != null ? { tokens } : {}),
      ...(reason ? { reason } : {}),
    });
    const found = list.some((d) => d.delegationId === delegationId);
    return found
      ? list.map((d) => (d.delegationId === delegationId ? updated : d))
      : [...list, updated];
  }

  // delegation_done
  const found = state.find((d) => d.delegationId === event.delegationId);
  if (!found) return state;
  return state.map((d) => {
    if (d.delegationId !== event.delegationId) return d;
    return {
      ...d,
      done: true,
      ...(event.droppedClaims != null ? { droppedClaims: event.droppedClaims } : {}),
      ...(event.tokens != null ? { tokens: event.tokens } : {}),
      ...(event.winner !== undefined ? { winner: event.winner } : {}),
    };
  });
}

/** Total known cost; `unknown` when at least one part has no known price. */
export function delegationCost(children: DelegationChildView[]): {
  total: number;
  unknown: boolean;
} {
  let total = 0;
  let unknown = false;
  for (const child of children) {
    if (typeof child.costUsd === 'number' && Number.isFinite(child.costUsd)) {
      total += child.costUsd;
    } else if (
      // A part that RAN but has no declared price makes the total unknown. A
      // refused part never ran, so it must not turn a real total into "—".
      child.costUsd == null &&
      (child.status === 'running' ||
        child.status === 'completed' ||
        (child.tokens ?? 0) > 0)
    ) {
      unknown = true;
    }
  }
  return { total, unknown };
}
