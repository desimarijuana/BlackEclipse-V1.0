import { describe, expect, it } from 'vitest';
import {
  GLOBAL_SHORTCUTS,
  isFocusModeShortcut,
  isHelpShortcut,
  isNewChatShortcut,
  isReservedSidebarShortcut,
  isSettingsShortcut,
  isSidebarToggleShortcut,
  isThemeShortcut,
} from './shortcuts';

function key(overrides: Partial<KeyboardEvent> = {}): KeyboardEvent {
  return {
    key: '',
    code: '',
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    repeat: false,
    defaultPrevented: false,
    isComposing: false,
    keyCode: 0,
    ...overrides,
  } as KeyboardEvent;
}

describe('global shortcut catalogue', () => {
  it('keeps ids unique so the help dialog can key rows reliably', () => {
    const ids = GLOBAL_SHORTCUTS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('documents only known groups', () => {
    const groups = new Set(GLOBAL_SHORTCUTS.map((s) => s.group));
    expect([...groups].every((g) => ['essentials', 'navigation', 'chart'].includes(g))).toBe(true);
  });
});

describe('isHelpShortcut', () => {
  it('accepts Ctrl/Cmd + /', () => {
    expect(isHelpShortcut(key({ key: '/', code: 'Slash', ctrlKey: true }))).toBe(true);
    expect(isHelpShortcut(key({ key: '/', code: 'Slash', metaKey: true }))).toBe(true);
  });

  it('accepts the physical Slash key on layouts that report another character', () => {
    expect(isHelpShortcut(key({ key: '÷', code: 'Slash', ctrlKey: true }))).toBe(true);
  });

  it('accepts plain ? (Shift + /) as the conventional alias', () => {
    expect(isHelpShortcut(key({ key: '?', code: 'Slash', shiftKey: true }))).toBe(true);
  });

  it('rejects unmodified / and unrelated chords', () => {
    expect(isHelpShortcut(key({ key: '/', code: 'Slash' }))).toBe(false);
    expect(isHelpShortcut(key({ key: 'k', code: 'KeyK', ctrlKey: true }))).toBe(false);
  });
});

describe('chords with an AltGr / layout fallback', () => {
  it('matches Ctrl/Cmd + Alt + N even when AltGr changes event.key', () => {
    expect(isNewChatShortcut(key({ key: 'n', code: 'KeyN', ctrlKey: true, altKey: true }))).toBe(true);
    expect(isNewChatShortcut(key({ key: 'ń', code: 'KeyN', ctrlKey: true, altKey: true }))).toBe(true);
    expect(isNewChatShortcut(key({ key: 'n', code: 'KeyN', ctrlKey: true }))).toBe(false);
  });

  it('matches Ctrl + Alt + X with the same fallback', () => {
    expect(isFocusModeShortcut(key({ key: 'x', code: 'KeyX', ctrlKey: true, altKey: true }))).toBe(true);
    expect(isFocusModeShortcut(key({ key: 'ż', code: 'KeyX', ctrlKey: true, altKey: true }))).toBe(true);
    expect(isFocusModeShortcut(key({ key: 'x', code: 'KeyX', ctrlKey: true }))).toBe(false);
  });
});

describe('new global chords', () => {
  it('recognises Settings, theme and sidebar toggles', () => {
    expect(isSettingsShortcut(key({ key: ',', code: 'Comma', ctrlKey: true }))).toBe(true);
    expect(isThemeShortcut(key({ key: 'l', code: 'KeyL', ctrlKey: true, shiftKey: true }))).toBe(true);
    expect(isSidebarToggleShortcut(key({ key: 'b', code: 'KeyB', metaKey: true }))).toBe(true);
    expect(isSidebarToggleShortcut(key({ key: 'b', code: 'KeyB' }))).toBe(false);
  });
});

describe('isReservedSidebarShortcut', () => {
  it('flags the chords a browser owns', () => {
    expect(['F1', 'F5', 'F11', 'F12'].every(isReservedSidebarShortcut)).toBe(true);
    expect(isReservedSidebarShortcut('F2')).toBe(false);
    expect(isReservedSidebarShortcut('')).toBe(false);
  });
});
