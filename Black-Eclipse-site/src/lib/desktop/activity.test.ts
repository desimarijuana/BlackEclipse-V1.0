import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  beginDesktopActivity,
  desktopActivityCount,
  isDesktopActivity,
  subscribeDesktopActivity,
} from './activity';

// The counter is module state, so every test releases what it started.
afterEach(() => {
  while (desktopActivityCount() > 0) {
    // Defensive: a leaked token would poison the next test.
    beginDesktopActivity()();
  }
});

describe('desktop activity counter', () => {
  it('is idle with no streams', () => {
    expect(isDesktopActivity()).toBe(false);
    expect(desktopActivityCount()).toBe(0);
  });

  it('counts concurrent streams and clears only when the last settles', () => {
    const first = beginDesktopActivity();
    const second = beginDesktopActivity();
    expect(desktopActivityCount()).toBe(2);
    expect(isDesktopActivity()).toBe(true);

    first();
    expect(isDesktopActivity()).toBe(true);
    second();
    expect(isDesktopActivity()).toBe(false);
  });

  it('releases are idempotent — a double settle cannot underflow', () => {
    const release = beginDesktopActivity();
    release();
    release();
    expect(desktopActivityCount()).toBe(0);
  });

  it('notifies subscribers on start and settle', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeDesktopActivity(listener);
    const release = beginDesktopActivity();
    release();
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    const after = beginDesktopActivity();
    after();
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('keeps notifying other subscribers when one throws', () => {
    const broken = subscribeDesktopActivity(() => {
      throw new Error('boom');
    });
    const healthy = vi.fn();
    const unsubscribe = subscribeDesktopActivity(healthy);
    beginDesktopActivity()();
    expect(healthy).toHaveBeenCalled();
    broken();
    unsubscribe();
  });
});
