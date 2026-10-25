import { describe, expect, it } from 'vitest';
import { formatDuration, formatTimestamp, shortHash, versionLabel } from './history-model';

describe('history formatting', () => {
  it('renders timestamps in UTC regardless of the host locale', () => {
    expect(formatTimestamp('2026-10-25T14:05:59.000Z')).toBe('2026-10-25 14:05 UTC');
    expect(formatTimestamp('not-a-date')).toBe('—');
    expect(formatTimestamp(null)).toBe('—');
  });

  it('renders durations at a readable precision', () => {
    expect(formatDuration(0)).toBe('0 ms');
    expect(formatDuration(842)).toBe('842 ms');
    expect(formatDuration(1_400)).toBe('1.4 s');
    expect(formatDuration(123_000)).toBe('2m 3s');
    expect(formatDuration(undefined)).toBe('—');
  });

  it('shortens content hashes without hiding the prefix', () => {
    expect(shortHash('abcdef0123456789')).toBe('abcdef012345…');
    expect(shortHash('abc')).toBe('abc');
    expect(shortHash(null)).toBe('—');
  });

  it('marks the current version', () => {
    expect(versionLabel(3, 3)).toBe('v3 · current');
    expect(versionLabel(2, 3)).toBe('v2');
    expect(versionLabel(2)).toBe('v2');
  });
});
