// ── useCommandCenterKeybind ────────────────────────────────────────────────
// Global ⌘K / Ctrl+K to toggle the command bar. Optionally allows a '/' shortcut
// (ignored when focus is already inside an input, textarea, or select).

'use client';

import { useEffect } from 'react';

interface Options {
  open: boolean;
  onToggle: () => void;
  /** Also bind the '/' shortcut. */
  slashShortcut?: boolean;
}

export function useCommandCenterKeybind({ open, onToggle, slashShortcut = false }: Options) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      // ⌘K / Ctrl+K — always.
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onToggle();
        return;
      }

      // Esc closes.
      if (e.key === 'Escape' && open) {
        onToggle();
        return;
      }

      // '/' opens when not focused in a text field.
      if (slashShortcut && e.key === '/' && !open) {
        const t = e.target as HTMLElement | null;
        const tag = t?.tagName?.toLowerCase();
        const isEditable =
          tag === 'input' || tag === 'textarea' || tag === 'select' || t?.isContentEditable;
        if (!isEditable) {
          e.preventDefault();
          onToggle();
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onToggle, slashShortcut]);
}
