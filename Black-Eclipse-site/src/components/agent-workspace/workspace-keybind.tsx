'use client';

// ── Agent Workspace — global toggle keybind ────────────────────────────────────
// Ctrl/Cmd + Shift + E opens/closes the right sidebar (the VS Code "toggle
// Explorer" chord). Like the terminal keybind, this is a dedicated capture-phase
// listener mounted in the root layout for the life of the app, so it works
// whether the sidebar is open or closed — the sidebar itself only mounts when
// open, which is exactly when a "can't open it" bug bites.
//
// It matches on `event.code` (layout-independent) with a `key` fallback, and is
// skipped while typing in a field so a shortcut never eats a keystroke.

import { useEffect } from 'react';
import { useWorkspaceStore } from '@/lib/agent-workspace/store';

const EDITABLE = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"], [role="combobox"]';

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== 'function') return false;
  return el.isContentEditable === true || !!el.closest(EDITABLE);
}

/**
 * Whether a keydown is the workspace toggle: Ctrl/Cmd + Shift + E (the VS Code
 * "toggle Explorer / sidebar" chord). A pure predicate (unit-tested). It matches
 * on `event.code` (layout-independent, like the terminal keybind) with a `key`
 * fallback for keyboards that report the letter without a code.
 */
export function isWorkspaceShortcut(
  event: Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey' | 'code' | 'key'>,
): boolean {
  if (event.altKey || !event.shiftKey) return false;
  if (!event.ctrlKey && !event.metaKey) return false;
  if (event.ctrlKey && event.metaKey) return false;
  return event.code === 'KeyE' || event.key.toLowerCase() === 'e';
}

export function WorkspaceKeybind() {
  const toggle = useWorkspaceStore((s) => s.toggle);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isWorkspaceShortcut(event)) return;
      if (isTyping(event.target)) return;
      // Take the key before the browser or a focused element sees it.
      event.preventDefault();
      event.stopPropagation();
      toggle();
    };
    // Capture phase, so nothing else can consume it first.
    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  }, [toggle]);

  return null;
}
