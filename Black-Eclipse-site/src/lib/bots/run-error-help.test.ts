import { describe, expect, it } from 'vitest';
import { runErrorHelp } from './run-error-help';

describe('runErrorHelp', () => {
  it('returns null when there is no error class', () => {
    expect(runErrorHelp(null)).toBeNull();
    expect(runErrorHelp(undefined)).toBeNull();
    expect(runErrorHelp('')).toBeNull();
  });

  it('explains a known transient class and marks it retryable', () => {
    const help = runErrorHelp('PROVIDER_TIMEOUT');
    expect(help?.retryable).toBe(true);
    expect(help?.what.toLowerCase()).toContain('time limit');
    expect(help?.fix.length).toBeGreaterThan(0);
  });

  it('marks a configuration failure as not retryable', () => {
    expect(runErrorHelp('INVALID_CONFIGURATION')?.retryable).toBe(false);
  });

  it('does not invent a cause for an unknown class', () => {
    const help = runErrorHelp('SOMETHING_NEW');
    expect(help).not.toBeNull();
    expect(help?.what).toContain('does not have a specific note');
  });
});
