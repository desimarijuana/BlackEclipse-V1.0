import { describe, expect, it } from 'vitest';
import { sortRevisions, undoRevision } from './dashboard-history';
import type { SdkDashboardRevision } from './index';

function revision(value: number, summary = `r${value}`): SdkDashboardRevision {
  return { revision: value, summary, changes: [], createdAt: '2026-10-19T00:00:00.000Z' };
}

describe('dashboard history helpers', () => {
  it('sorts newest first without mutating the input', () => {
    const input = [revision(2), revision(5), revision(3)];
    expect(sortRevisions(input).map((entry) => entry.revision)).toEqual([5, 3, 2]);
    expect(input.map((entry) => entry.revision)).toEqual([2, 5, 3]);
  });

  it('undoes to the newest revision older than the current one', () => {
    expect(undoRevision([revision(4), revision(2), revision(3)])?.revision).toBe(3);
    expect(undoRevision([revision(4), revision(2), revision(3)], 2)).toBeNull();
  });

  it('returns null when there is no earlier revision', () => {
    expect(undoRevision([])).toBeNull();
    expect(undoRevision([revision(1)])).toBeNull();
  });
});
