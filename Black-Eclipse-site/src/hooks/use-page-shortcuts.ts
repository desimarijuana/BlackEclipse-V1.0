'use client';

import { useEffect, useRef, type RefObject } from 'react';
import { create } from 'zustand';
import { canHandleKeyboardEvent, matchesShortcut, preferredKeyboardScope } from '@/lib/keyboard';

export interface PageShortcut {
  id: string;
  label: string;
  keys: string;
  run: () => void;
  enabled?: boolean;
}

export interface ShortcutScope {
  token: symbol;
  rootRef: RefObject<HTMLElement | null>;
  actionsRef: { current: readonly PageShortcut[] };
}

export const PLAIN_SHORTCUTS_KEY = 'be_plain_shortcuts_disabled';

interface KeyboardShortcutsState {
  scopes: readonly ShortcutScope[];
  helpOpen: boolean;
  plainShortcutsDisabled: boolean;
  setHelpOpen: (open: boolean) => void;
  setPlainShortcutsDisabled: (disabled: boolean) => void;
}

export const useKeyboardShortcutsStore = create<KeyboardShortcutsState>((set) => ({
  scopes: [],
  helpOpen: false,
  plainShortcutsDisabled: false,
  setHelpOpen: (helpOpen) => set({ helpOpen }),
  setPlainShortcutsDisabled: (plainShortcutsDisabled) => {
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PLAIN_SHORTCUTS_KEY, plainShortcutsDisabled ? '1' : '0');
      } catch {}
    }
    set({ plainShortcutsDisabled });
  },
}));

export function dispatchPageShortcut(event: KeyboardEvent): boolean {
  const state = useKeyboardShortcutsStore.getState();
  if (state.helpOpen) return false;
  const candidates = state.scopes.flatMap((scope) => {
    const root = scope.rootRef.current;
    if (!root || !canHandleKeyboardEvent(event, root)) return [];
    const action = scope.actionsRef.current.find((item) => {
      if (item.enabled === false) return false;
      if (state.plainShortcutsDisabled && !item.keys.includes('+')) return false;
      return matchesShortcut(event, item.keys);
    });
    return action ? [{ root, action }] : [];
  });
  const selected = preferredKeyboardScope(candidates, document.activeElement);
  if (!selected) return false;
  event.preventDefault();
  selected.action.run();
  return true;
}

export function usePageShortcuts(rootRef: RefObject<HTMLElement | null>, actions: readonly PageShortcut[]) {
  const actionsRef = useRef(actions);
  const tokenRef = useRef(Symbol('keyboard-scope'));

  useEffect(() => {
    actionsRef.current = actions;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      if (localStorage.getItem(PLAIN_SHORTCUTS_KEY) === '1') {
        useKeyboardShortcutsStore.setState({ plainShortcutsDisabled: true });
      }
    } catch {}
  }, []);

  useEffect(() => {
    const token = tokenRef.current;
    const state = useKeyboardShortcutsStore.getState();
    if (state.scopes.length === 0) window.addEventListener('keydown', dispatchPageShortcut);
    useKeyboardShortcutsStore.setState({ scopes: [...state.scopes, { token, rootRef, actionsRef }] });
    return () => {
      const scopes = useKeyboardShortcutsStore.getState().scopes.filter((scope) => scope.token !== token);
      useKeyboardShortcutsStore.setState({ scopes });
      if (scopes.length === 0) window.removeEventListener('keydown', dispatchPageShortcut);
    };
  }, [rootRef]);
}
