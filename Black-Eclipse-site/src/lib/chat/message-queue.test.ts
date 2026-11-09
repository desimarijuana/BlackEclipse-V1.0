import { describe, expect, it } from 'vitest';
import {
  MAX_QUEUED_PROMPTS,
  enqueuePrompt,
  moveQueued,
  promoteQueued,
  removeQueued,
  updateQueued,
  type QueuedPrompt,
} from './message-queue';

let seq = 0;
const id = () => `id-${++seq}`;
const make = (texts: string[]): QueuedPrompt[] =>
  texts.map((text) => ({ id: id(), text, createdAt: 1 }));

describe('message queue (pure list rules)', () => {
  it('trims and appends a prompt, ignoring empty text', () => {
    const empty: QueuedPrompt[] = [];
    expect(enqueuePrompt(empty, '   ', id)).toBe(empty);
    const next = enqueuePrompt(empty, '  research NVDA  ', id);
    expect(next).toHaveLength(1);
    expect(next[0].text).toBe('research NVDA');
  });

  it('rejects prompts past the cap without mutating the list', () => {
    const full = make(Array.from({ length: MAX_QUEUED_PROMPTS }, (_, i) => `p${i}`));
    expect(enqueuePrompt(full, 'one more', id)).toBe(full);
  });

  it('removes by id and keeps the original reference when nothing matches', () => {
    const items = make(['a', 'b']);
    expect(removeQueued(items, 'missing')).toBe(items);
    expect(removeQueued(items, items[0].id).map((i) => i.text)).toEqual(['b']);
  });

  it('edits in place and removes an item when the edit is empty', () => {
    const items = make(['a', 'b']);
    const edited = updateQueued(items, items[1].id, '  b2 ');
    expect(edited.map((i) => i.text)).toEqual(['a', 'b2']);
    expect(updateQueued(items, items[0].id, '   ')).toHaveLength(1);
    expect(updateQueued(items, items[0].id, 'a')).toBe(items);
  });

  it('moves items up/down and treats edges as no-ops', () => {
    const items = make(['a', 'b', 'c']);
    expect(moveQueued(items, items[2].id, 'up').map((i) => i.text)).toEqual(['a', 'c', 'b']);
    expect(moveQueued(items, items[0].id, 'down').map((i) => i.text)).toEqual(['b', 'a', 'c']);
    expect(moveQueued(items, items[0].id, 'up')).toBe(items);
    expect(moveQueued(items, items[2].id, 'down')).toBe(items);
  });

  it('promotes an item to the front for "run this next"', () => {
    const items = make(['a', 'b', 'c']);
    expect(promoteQueued(items, items[2].id).map((i) => i.text)).toEqual(['c', 'a', 'b']);
    expect(promoteQueued(items, items[0].id)).toBe(items);
  });
});
