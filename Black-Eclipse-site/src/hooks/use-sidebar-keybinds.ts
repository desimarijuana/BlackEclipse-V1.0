'use client';

import { useEffect, useRef } from 'react';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { shortcutTab, type SidebarConfig } from '@/lib/sidebar/config';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import type { AppTab } from '@/components/layout/sidebar';

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

export function useSidebarKeybinds(onNavigate: (tab: AppTab) => void) {
  useHydrateSidebarConfig();
  const navigateRef = useRef(onNavigate);
  useEffect(() => {
    navigateRef.current = onNavigate;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      handleSidebarShortcut(event, useSidebarConfigStore.getState().config, navigateRef.current);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
