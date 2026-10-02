import { describe, expect, it } from 'vitest';
import { SEEN_CAP, seedSeen, selectNewEvents, type LiveAlertEvent } from './event-diff';

const ev = (id: string, detail = `d-${id}`): LiveAlertEvent => ({ id, detail });

describe('event-diff', () => {
  it('seeds without producing notifications', () => {
    const seen = seedSeen([ev('3'), ev('2'), ev('1')]);
    expect([...seen].sort()).toEqual(['1', '2', '3']);
    const { fresh } = selectNewEvents([ev('3'), ev('2'), ev('1')], seen);
    expect(fresh).toHaveLength(0);
  });

  it('returns only genuinely new events, oldest-first', () => {
    const seen = seedSeen([ev('1')]);
    // Newest-first feed: 3 then 2 are new.
    const { fresh, seen: next } = selectNewEvents([ev('3'), ev('2'), ev('1')], seen);
    expect(fresh.map((e) => e.id)).toEqual(['2', '3']);
    expect(next.has('3')).toBe(true);
  });

  it('does not re-fire when the newest event scrolls out of the 50-item feed', () => {
    // Poll 1: newest is 100.
    let seen = seedSeen([ev('100'), ev('99')]);
    // Poll 2: a burst pushes 100 out of a 50-row window; we only see 98..49.
    const window = [ev('98'), ev('97'), ev('96'), ev('95')];
    const { fresh, seen: next } = selectNewEvents(window, seen);
    expect(fresh.map((e) => e.id)).toEqual(['95', '96', '97', '98']);
    seen = next;
    // Poll 3: same window again — nothing new, and 100 must NOT resurface.
    const again = selectNewEvents(window, seen);
    expect(again.fresh).toHaveLength(0);
  });

  it('ignores entries without an id', () => {
    const { fresh } = selectNewEvents([{ id: '' }, ev('5')], new Set());
    expect(fresh.map((e) => e.id)).toEqual(['5']);
  });

  it('bounds the seen-set and drops the oldest ids', () => {
    const many: LiveAlertEvent[] = [];
    for (let i = 0; i < SEEN_CAP + 50; i++) many.push(ev(String(i)));
    const seen = seedSeen(many);
    expect(seen.size).toBe(SEEN_CAP);
    expect(seen.has('0')).toBe(false); // oldest pruned
    expect(seen.has(String(SEEN_CAP + 49))).toBe(true); // newest kept
  });
});
