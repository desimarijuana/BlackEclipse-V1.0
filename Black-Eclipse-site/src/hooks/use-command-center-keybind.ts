'use client';

import { useEffect, useRef } from 'react';
import { canHandleKeyboardEvent, isKeyboardEventAvailable, matchesShortcut } from '@/lib/keyboard';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';

interface Options {
  open: boolean;
  onToggle: () => void;
  slashShortcut?: boolean;
}

export function useCommandCenterKeybind(options: Options) {
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isKeyboardEventAvailable(event) || useKeyboardShortcutsStore.getState().helpOpen) return;
      const { open, onToggle, slashShortcut = false } = optionsRef.current;
      if (open && (matchesShortcut(event, 'mod+k') || matchesShortcut(event, 'escape'))) {
        event.preventDefault();
        onToggle();
        return;
      }
      if (!canHandleKeyboardEvent(event)) return;
      if (matchesShortcut(event, 'mod+k') || (slashShortcut && !open && matchesShortcut(event, '/'))) {
        event.preventDefault();
        onToggle();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
