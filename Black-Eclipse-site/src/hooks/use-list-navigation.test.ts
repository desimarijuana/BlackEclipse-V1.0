import { describe, expect, it } from 'vitest';
import { nextListId } from './use-list-navigation';

describe('nextListId', () => {
  const ids = ['a', 'b', 'c', 'd'];

  it('moves to the next id and wraps at the end', () => {
    expect(nextListId(ids, 'a', 'next')).toBe('b');
    expect(nextListId(ids, 'c', 'next')).toBe('d');
    expect(nextListId(ids, 'd', 'next')).toBe('a');
  });

  it('moves to the previous id and wraps at the start', () => {
    expect(nextListId(ids, 'c', 'prev')).toBe('b');
    expect(nextListId(ids, 'a', 'prev')).toBe('d');
  });

  it('selects the first id when moving next with no selection', () => {
    expect(nextListId(ids, null, 'next')).toBe('a');
  });

  it('selects the last id when moving prev with no selection', () => {
    expect(nextListId(ids, null, 'prev')).toBe('d');
  });

  it('jumps to home and end', () => {
    expect(nextListId(ids, 'c', 'first')).toBe('a');
    expect(nextListId(ids, 'b', 'last')).toBe('d');
  });

  it('returns null for an empty list', () => {
    expect(nextListId([], 'a', 'next')).toBeNull();
    expect(nextListId([], null, 'first')).toBeNull();
  });

  it('survives reordering because selection is keyed by stable id', () => {
    const before = ['a', 'b', 'c', 'd'];
    const selected = nextListId(before, 'b', 'next');
    expect(selected).toBe('c');
    const afterReorder = ['d', 'a', 'c', 'b'];
    expect(nextListId(afterReorder, selected, 'next')).toBe('b');
    expect(nextListId(afterReorder, selected, 'prev')).toBe('a');
  });

  it('survives filtering by falling back to an edge when the id disappears', () => {
    const filtered = ['b', 'd'];
    expect(nextListId(filtered, 'c', 'next')).toBe('b');
    expect(nextListId(filtered, 'c', 'prev')).toBe('d');
  });

  it('treats a single-item list as self-wrapping', () => {
    expect(nextListId(['only'], 'only', 'next')).toBe('only');
    expect(nextListId(['only'], 'only', 'prev')).toBe('only');
  });
});
