import { describe, expect, it } from 'vitest';
import { insertTranscript, normalizeTranscript } from './insert';

describe('normalizeTranscript', () => {
  it('collapses whitespace and trims', () => {
    expect(normalizeTranscript('  buy   NVDA\n  calls  ')).toBe('buy NVDA calls');
    expect(normalizeTranscript('   ')).toBe('');
  });
});

describe('insertTranscript', () => {
  it('inserts into an empty composer', () => {
    expect(insertTranscript('', 'analyze gold')).toEqual({
      value: 'analyze gold',
      caret: 'analyze gold'.length,
    });
  });

  it('adds one separating space when the existing text needs it', () => {
    const result = insertTranscript('Show me', 'NVDA earnings', { start: 7, end: 7 });
    expect(result.value).toBe('Show me NVDA earnings');
    expect(result.caret).toBe(result.value.length);
  });

  it('does not double an existing space', () => {
    expect(insertTranscript('Show me ', 'NVDA', { start: 8, end: 8 }).value).toBe('Show me NVDA');
  });

  it('replaces the current selection instead of appending', () => {
    const result = insertTranscript('Compare AAPL', 'NVDA', { start: 8, end: 12 });
    expect(result.value).toBe('Compare NVDA');
    expect(result.caret).toBe('Compare NVDA'.length);
  });

  it('keeps trailing punctuation tight when text follows', () => {
    const result = insertTranscript('and then.', 'done', { start: 9, end: 9 });
    expect(result.value).toBe('and then. done');
    expect(result.caret).toBe('and then. done'.length);
  });

  it('adds a space before existing text when needed', () => {
    const result = insertTranscript('is it', 'growth', { start: 0, end: 0 });
    expect(result.value).toBe('growth is it');
    expect(result.caret).toBe('growth'.length + 1);
  });

  it('leaves the value untouched for an empty transcript', () => {
    expect(insertTranscript('abc', '   ', { start: 1, end: 1 })).toEqual({ value: 'abc', caret: 1 });
  });

  it('clamps an out-of-range selection', () => {
    const result = insertTranscript('abc', 'x', { start: 99, end: 200 });
    expect(result.value).toBe('abc x');
  });
});
