import { describe, expect, it } from 'vitest';
import { NAV_HISTORY_LIMIT, backTarget, recordVisit } from './navigation-history';

describe('recordVisit', () => {
  it('appends a new tab', () => {
    expect(recordVisit(['chat'], 'journal')).toEqual(['chat', 'journal']);
  });

  it('ignores a consecutive duplicate and keeps the same reference', () => {
    const history = ['chat', 'journal'];
    expect(recordVisit(history, 'journal')).toBe(history);
  });

  it('allows a non-consecutive repeat', () => {
    expect(recordVisit(['chat', 'journal'], 'chat')).toEqual(['chat', 'journal', 'chat']);
  });

  it('drops the oldest entry past the cap', () => {
    expect(recordVisit(['a', 'b', 'c'], 'd', { cap: 3 })).toEqual(['b', 'c', 'd']);
  });

  it('caps at the default limit', () => {
    let history: string[] = [];
    for (let i = 0; i < NAV_HISTORY_LIMIT + 5; i += 1) history = recordVisit(history, `tab-${i}`);
    expect(history).toHaveLength(NAV_HISTORY_LIMIT);
    expect(history[0]).toBe('tab-5');
    expect(history[history.length - 1]).toBe(`tab-${NAV_HISTORY_LIMIT + 4}`);
  });

  it('ignores tabs rejected by isKnown', () => {
    const history = ['chat'];
    const isKnown = (tab: string) => tab === 'chat' || tab === 'journal';
    expect(recordVisit(history, 'bogus', { isKnown })).toBe(history);
  });

  it('records a known tab when isKnown allows it', () => {
    const isKnown = (tab: string) => tab === 'chat' || tab === 'journal';
    expect(recordVisit(['chat'], 'journal', { isKnown })).toEqual(['chat', 'journal']);
  });
});

describe('backTarget', () => {
  it('returns the previous tab and shrinks the history', () => {
    expect(backTarget(['chat', 'journal', 'economics'])).toEqual({
      tab: 'journal',
      history: ['chat', 'journal'],
    });
  });

  it('returns null with fewer than two entries', () => {
    expect(backTarget([])).toBeNull();
    expect(backTarget(['chat'])).toBeNull();
  });

  it('walks back one step at a time then stops', () => {
    const first = backTarget(['chat', 'journal', 'economics']);
    expect(first).not.toBeNull();
    const second = backTarget(first!.history);
    expect(second).toEqual({ tab: 'chat', history: ['chat'] });
    expect(backTarget(second!.history)).toBeNull();
  });

  it('does not mutate the input', () => {
    const history = ['chat', 'journal'];
    backTarget(history);
    expect(history).toEqual(['chat', 'journal']);
  });
});
