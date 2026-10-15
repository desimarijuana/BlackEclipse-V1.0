'use client';

import { useEffect, useRef } from 'react';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { shortcutTab, type SidebarConfig, type NavGroup } from '@/lib/sidebar/config';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import type { AppTab } from '@/components/layout/sidebar';

/** Keys that switch the top-level Terminal / Agentic / Bots menu. Alt-based so
 *  they never collide with browser tab switching (Ctrl+1..9) or the Alt+1..9
 *  sub-tab selection. */
export const MODE_SHORTCUTS: Array<{ keys: string; mode: NavGroup }> = [
  { keys: 'alt+t', mode: 'terminal' },
  { keys: 'alt+a', mode: 'agentic' },
  { keys: 'alt+b', mode: 'bots' },
];

export function handleSidebarShortcut(event: KeyboardEvent, config: SidebarConfig, onNavigate: (tab: AppTab) => void): boolean {
  if (!/^F([1-9]|1[0-2])$/.test(event.key) || !matchesShortcut(event, event.key)) return false;
  if (useKeyboardShortcutsStore.getState().helpOpen || !canHandleKeyboardEvent(event)) return false;
  const tab = shortcutTab(config, event.key);
  if (tab) {
    event.preventDefault();
    onNavigate(tab);
    return true;
  }
  return false;
}

/**
 * Switch the sidebar between Terminal, Agentic and Bots. Terminal/Agentic leave
 * the active screen untouched — the menu simply re-filters; ChatBot is shared so
 * it stays put. Returns true when the shortcut fired.
 */
export function handleSidebarModeShortcut(event: KeyboardEvent): boolean {
  const hit = MODE_SHORTCUTS.find((s) => matchesShortcut(event, s.keys));
  if (!hit) return false;
  if (useKeyboardShortcutsStore.getState().helpOpen || !canHandleKeyboardEvent(event)) return false;
  event.preventDefault();
  useSidebarConfigStore.getState().setMode(hit.mode);
  return true;
}

export function useSidebarKeybinds(onNavigate: (tab: AppTab) => void) {
  useHydrateSidebarConfig();
  const navigateRef = useRef(onNavigate);
  useEffect(() => {
    navigateRef.current = onNavigate;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (handleSidebarModeShortcut(event)) {
        // Bots is a mode with no static nav — mirror the switcher click and open
        // the workspace so the panel and the page never disagree.
        if (useSidebarConfigStore.getState().mode === 'bots') navigateRef.current('bots');
        return;
      }
      handleSidebarShortcut(event, useSidebarConfigStore.getState().config, navigateRef.current);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
