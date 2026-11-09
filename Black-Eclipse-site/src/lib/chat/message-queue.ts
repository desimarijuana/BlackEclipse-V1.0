// ── Message queue — prompts waiting for the current run to finish ────────────
//
// A user often knows their next two questions while the agent is still writing
// the first answer. Before this existed the composer silently ignored Enter
// while a run was active, so those follow-ups were lost unless the user waited
// and retyped them. This module owns the ordered list as plain immutable data
// so the behaviour is testable without React.

export interface QueuedPrompt {
  id: string;
  /** Trimmed prompt text, exactly what will be sent. */
  text: string;
  /** Epoch ms — keeps the list stable and lets the UI say "queued 2m ago". */
  createdAt: number;
}

/** A bounded queue: past this the user is told to wait instead of silently
 *  accumulating an unbounded backlog in memory. */
export const MAX_QUEUED_PROMPTS = 20;

/**
 * Append a prompt. Empty/whitespace-only text and a full queue are rejected
 * (returns the SAME array reference so a caller can detect "not added").
 */
export function enqueuePrompt(
  items: readonly QueuedPrompt[],
  text: string,
  makeId: () => string,
  now = Date.now(),
): readonly QueuedPrompt[] {
  const trimmed = text.trim();
  if (!trimmed) return items;
  if (items.length >= MAX_QUEUED_PROMPTS) return items;
  return [...items, { id: makeId(), text: trimmed, createdAt: now }];
}

export function removeQueued(
  items: readonly QueuedPrompt[],
  id: string,
): readonly QueuedPrompt[] {
  const next = items.filter((item) => item.id !== id);
  return next.length === items.length ? items : next;
}

/** Edit a queued prompt in place. Empty text removes the item. */
export function updateQueued(
  items: readonly QueuedPrompt[],
  id: string,
  text: string,
): readonly QueuedPrompt[] {
  const trimmed = text.trim();
  if (!trimmed) return removeQueued(items, id);
  let changed = false;
  const next = items.map((item) => {
    if (item.id !== id || item.text === trimmed) return item;
    changed = true;
    return { ...item, text: trimmed };
  });
  return changed ? next : items;
}

/** Move an item one slot up or down; edges are a no-op. */
export function moveQueued(
  items: readonly QueuedPrompt[],
  id: string,
  direction: 'up' | 'down',
): readonly QueuedPrompt[] {
  const index = items.findIndex((item) => item.id === id);
  if (index === -1) return items;
  const target = direction === 'up' ? index - 1 : index + 1;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/**
 * Move an item to the front. "Run this next" promotes the chosen prompt so the
 * drain loop picks it up as soon as the current run stops.
 */
export function promoteQueued(
  items: readonly QueuedPrompt[],
  id: string,
): readonly QueuedPrompt[] {
  const index = items.findIndex((item) => item.id === id);
  if (index <= 0) return items;
  return [items[index], ...items.slice(0, index), ...items.slice(index + 1)];
}
