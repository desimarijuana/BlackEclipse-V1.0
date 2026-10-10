import { describe, it, expect, beforeEach } from 'vitest';
import {
  breakerCanAttempt, breakerRecordSuccess, breakerRecordFailure, breakerSnapshot,
  openBreakers, configureBreaker, resetBreakers,
} from './circuit-breaker';

describe('circuit breaker', () => {
  beforeEach(() => {
    resetBreakers();
    configureBreaker({ failureThreshold: 3, cooldownMs: 1000 });
  });

  it('starts closed and allows attempts', () => {
    expect(breakerCanAttempt('gdelt')).toBe(true);
    expect(breakerSnapshot('gdelt')).toEqual({ id: 'gdelt', open: false, failures: 0, retryAfterMs: 0 });
  });

  it('opens after the configured number of consecutive failures', () => {
    const t = 1_000_000;
    breakerRecordFailure('x', t);
    breakerRecordFailure('x', t);
    expect(breakerCanAttempt('x', t)).toBe(true);
    breakerRecordFailure('x', t);
    expect(breakerCanAttempt('x', t)).toBe(false);
    const snap = breakerSnapshot('x', t);
    expect(snap.open).toBe(true);
    expect(snap.failures).toBe(3);
    expect(snap.retryAfterMs).toBe(1000);
  });

  it('allows a half-open probe once the cooldown elapses', () => {
    const t = 1_000_000;
    for (let i = 0; i < 3; i++) breakerRecordFailure('x', t);
    expect(breakerCanAttempt('x', t + 999)).toBe(false);
    expect(breakerCanAttempt('x', t + 1000)).toBe(true);
  });

  it('closes on the next success', () => {
    const t = 1_000_000;
    for (let i = 0; i < 3; i++) breakerRecordFailure('x', t);
    breakerRecordSuccess('x');
    expect(breakerCanAttempt('x', t)).toBe(true);
    expect(breakerSnapshot('x', t).failures).toBe(0);
  });

  it('re-opens immediately when a half-open probe fails', () => {
    const t = 1_000_000;
    for (let i = 0; i < 3; i++) breakerRecordFailure('x', t);
    // Probe allowed at cooldown, but the source fails again.
    expect(breakerCanAttempt('x', t + 1000)).toBe(true);
    breakerRecordFailure('x', t + 1000);
    expect(breakerCanAttempt('x', t + 1000)).toBe(false);
    expect(breakerSnapshot('x', t + 1000).failures).toBe(4);
  });

  it('tracks multiple sources independently', () => {
    const t = 1_000_000;
    for (let i = 0; i < 3; i++) breakerRecordFailure('a', t);
    breakerRecordSuccess('b');
    const open = openBreakers(t);
    expect(open.map((s) => s.id)).toEqual(['a']);
  });
});
