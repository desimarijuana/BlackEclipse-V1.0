'use client';

import { useEffect, useRef } from 'react';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { shortcutTab, DEFAULT_SIDEBAR_SECTIONS, type SidebarConfig, type NavGroup } from '@/lib/sidebar/config';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';
import { isSidebarToggleShortcut } from '@/lib/shortcuts';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import type { AppTab } from '@/components/layout/sidebar';

/** Keys that switch the top-level Terminal / Agentic / Bots / Graph menu.
 *  Alt-based so they never collide with browser tab switching (Ctrl+1..9) or the
 *  Alt+1..9 sub-tab selection. */
export const MODE_SHORTCUTS: Array<{ keys: string; mode: NavGroup }> = [
  { keys: 'alt+t', mode: 'terminal' },
  { keys: 'alt+a', mode: 'agentic' },
  { keys: 'alt+b', mode: 'bots' },
  { keys: 'alt+g', mode: 'graph' },
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

/** Dedicated modes whose shortcut must also open their workspace tab. */
const MODE_OPENS_TAB: Partial<Record<NavGroup, AppTab>> = {
  bots: 'bots',
  graph: 'overview',
};

/**
 * Switch the sidebar between Terminal, Agentic, Bots and Graph Studio.
 * Terminal/Agentic leave a screen that belongs to them untouched — the menu
 * simply re-filters; ChatBot is shared so it stays put. When the active screen
 * belongs to a different mode (e.g. leaving Bots), navigate to that mode's
 * default so the menu and the page never disagree. Returns true when the
 * shortcut fired.
 */
export function handleSidebarModeShortcut(
  event: KeyboardEvent,
  onNavigate?: (tab: AppTab) => void,
  activeTab?: AppTab,
): boolean {
  const hit = MODE_SHORTCUTS.find((s) => matchesShortcut(event, s.keys));
  if (!hit) return false;
  if (useKeyboardShortcutsStore.getState().helpOpen || !canHandleKeyboardEvent(event)) return false;
  event.preventDefault();
  useSidebarConfigStore.getState().setMode(hit.mode);
  const opens = MODE_OPENS_TAB[hit.mode];
  if (opens && onNavigate) {
    onNavigate(opens);
    return true;
  }
  if (onNavigate && activeTab) {
    const def = DEFAULT_SIDEBAR_SECTIONS.find((s) => s.id === activeTab);
    const stays = Boolean(def && (def.group === 'both' || def.group === hit.mode));
    if (!stays) onNavigate(hit.mode === 'agentic' ? 'chat' : 'home');
  }
  return true;
}

export function useSidebarKeybinds(onNavigate: (tab: AppTab) => void, activeTab?: AppTab) {
  useHydrateSidebarConfig();
  const navigateRef = useRef(onNavigate);
  const activeTabRef = useRef(activeTab);
  useEffect(() => {
    navigateRef.current = onNavigate;
    activeTabRef.current = activeTab;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!useKeyboardShortcutsStore.getState().helpOpen && canHandleKeyboardEvent(event) && isSidebarToggleShortcut(event)) {
        event.preventDefault();
        useSidebarConfigStore.getState().toggleCollapsed();
        return;
      }
      // Dedicated modes (bots / graph) mirror the switcher click and open their
      // workspace, so the panel and the page never disagree.
      if (handleSidebarModeShortcut(event, navigateRef.current, activeTabRef.current)) return;
      handleSidebarShortcut(event, useSidebarConfigStore.getState().config, navigateRef.current);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
