import { describe, expect, it } from 'vitest';
import { deriveTaskbarSignal } from './taskbar';

const base = {
  unread: 0,
  focused: true,
  enabled: true,
  previousUnread: 0,
  working: false,
};

describe('deriveTaskbarSignal', () => {
  it('clears the taskbar when nothing is unread and nothing is running', () => {
    expect(deriveTaskbarSignal({ ...base, unread: 0 })).toEqual({
      state: 'idle',
      count: 0,
      flash: false,
      working: false,
    });
  });

  it('stays idle when the preference is off, even with unread items and a run', () => {
    expect(
      deriveTaskbarSignal({ ...base, unread: 3, working: true, enabled: false }),
    ).toEqual({
      state: 'idle',
      count: 0,
      flash: false,
      working: false,
    });
  });

  it('badges unread items without flashing while the window is focused', () => {
    expect(
      deriveTaskbarSignal({ ...base, unread: 2, focused: true, previousUnread: 0 }),
    ).toEqual({
      state: 'unread',
      count: 2,
      flash: false,
      working: false,
    });
  });

  it('flashes for a NEW arrival while unfocused', () => {
    expect(
      deriveTaskbarSignal({ ...base, unread: 1, focused: false, previousUnread: 0 }),
    ).toEqual({
      state: 'unread',
      count: 1,
      flash: true,
      working: false,
    });
  });

  it('flashes again when more items arrive while unfocused', () => {
    expect(
      deriveTaskbarSignal({ ...base, unread: 3, focused: false, previousUnread: 2 }),
    ).toEqual({
      state: 'unread',
      count: 3,
      flash: true,
      working: false,
    });
  });

  it('does not re-flash when focus is lost with no new arrival', () => {
    // 2 unread, was 2, window just lost focus: the operator was already told.
    expect(
      deriveTaskbarSignal({ ...base, unread: 2, focused: false, previousUnread: 2 }),
    ).toEqual({
      state: 'unread',
      count: 2,
      flash: false,
      working: false,
    });
  });

  it('does not flash while re-evaluating an existing badge after a reload', () => {
    // Mount seeds `previousUnread` with the restored count.
    expect(
      deriveTaskbarSignal({ ...base, unread: 4, focused: false, previousUnread: 4 }),
    ).toEqual({
      state: 'unread',
      count: 4,
      flash: false,
      working: false,
    });
  });

  it('clears the badge as soon as everything is read, focused or not', () => {
    expect(
      deriveTaskbarSignal({ ...base, unread: 0, focused: false, previousUnread: 5 }),
    ).toEqual({
      state: 'idle',
      count: 0,
      flash: false,
      working: false,
    });
  });

  it('shows progress while working, independently of unread state', () => {
    expect(deriveTaskbarSignal({ ...base, working: true }).working).toBe(true);
    const withUnread = deriveTaskbarSignal({ ...base, unread: 2, working: true });
    expect(withUnread).toMatchObject({ state: 'unread', count: 2, working: true });
  });

  it('still flashes for a new arrival during a run', () => {
    expect(
      deriveTaskbarSignal({
        ...base,
        unread: 1,
        previousUnread: 0,
        focused: false,
        working: true,
      }),
    ).toEqual({ state: 'unread', count: 1, flash: true, working: true });
  });

  it('normalizes negative and fractional counts', () => {
    expect(deriveTaskbarSignal({ ...base, unread: -3, previousUnread: 0 }).state).toBe('idle');
    expect(deriveTaskbarSignal({ ...base, unread: 2.7, previousUnread: 0 }).count).toBe(2);
  });
});
