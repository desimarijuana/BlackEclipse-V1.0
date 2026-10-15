'use client';

import { useEffect } from 'react';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';

/** The window event a `/` press broadcasts so the on-screen chat composer can
 *  take the caret. Emitters/listeners never touch each other directly: whichever
 *  composer is actually on screen answers (the hidden keep-alive tab and the
 *  suppressed ChatDock ignore it), so a single global listener covers the app. */
export const CHAT_FOCUS_EVENT = 'be:focus-chat';

/**
 * Plain `/` places the caret in the chat composer instead of opening the global
 * command center. Only fires outside text fields and blocking dialogs;
 * `matchesShortcut(event, '/')` requires no modifiers, so Ctrl/Cmd+K remains the
 * one way to open global search.
 */
export function useChatFocusKeybind() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, '/') || !canHandleKeyboardEvent(event)) return;
      event.preventDefault();
      window.dispatchEvent(new CustomEvent(CHAT_FOCUS_EVENT));
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
