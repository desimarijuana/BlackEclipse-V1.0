import { describe, expect, it } from 'vitest';
import { isBrowserShortcutKey, isEditableTarget, isFileDrag } from './shell-guards';

describe('isBrowserShortcutKey', () => {
  it('blocks the WebView browser chords', () => {
    for (const key of ['r', 'R', 'p', 's', 'u', '=', '+', '-', '0']) {
      expect(isBrowserShortcutKey({ key, ctrlKey: true })).toBe(true);
    }
    // Cmd on macOS resolves the same chords.
    expect(isBrowserShortcutKey({ key: 'r', metaKey: true })).toBe(true);
  });

  it('leaves Eclipse commands and plain keys alone', () => {
    for (const key of ['k', 'b', '`', ',', '/', 'z', 'F5']) {
      expect(isBrowserShortcutKey({ key, ctrlKey: true })).toBe(false);
    }
    expect(isBrowserShortcutKey({ key: 'r' })).toBe(false);
    // AltGr combinations must never be swallowed as a browser chord.
    expect(isBrowserShortcutKey({ key: 'r', ctrlKey: true, altKey: true })).toBe(false);
  });
});

describe('isEditableTarget', () => {
  it('keeps the platform text menu inside editable fields', () => {
    expect(isEditableTarget({ tagName: 'INPUT' } as unknown as EventTarget)).toBe(true);
    expect(isEditableTarget({ tagName: 'TEXTAREA' } as unknown as EventTarget)).toBe(true);
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true } as unknown as EventTarget)).toBe(true);
  });

  it('treats app chrome and content as non-editable', () => {
    expect(isEditableTarget({ tagName: 'BUTTON' } as unknown as EventTarget)).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
});

describe('isFileDrag', () => {
  it('detects OS file drags only', () => {
    expect(isFileDrag({ dataTransfer: { types: ['Files'] } })).toBe(true);
    expect(isFileDrag({ dataTransfer: { types: ['text/plain'] } })).toBe(false);
    expect(isFileDrag({ dataTransfer: null })).toBe(false);
    expect(isFileDrag({})).toBe(false);
  });
});
