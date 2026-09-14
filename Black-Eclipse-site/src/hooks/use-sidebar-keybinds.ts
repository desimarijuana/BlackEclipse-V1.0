// ── useSidebarKeybinds ────────────────────────────────────────────────────
// Global F1–F12 bindings that open a sidebar tab, driven by the user's
// sidebar customization (Settings › Sidebar). Mirrors the modifier-aware
// typing guard used by the command-center keybind hook.

'use client';

import { useEffect } from 'react';
import { useSidebarConfigStore } from '@/lib/sidebar/store';
import { shortcutTab } from '@/lib/sidebar/config';
import type { AppTab } from '@/components/layout/sidebar';

export function useSidebarKeybinds(onNavigate: (tab: AppTab) => void) {
  const config = useSidebarConfigStore((s) => s.config);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // F-keys have no modifier; ignore modified presses so browser/OS
      // combinations (e.g. Alt+F4) pass through untouched.
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const tab = shortcutTab(config, e.key);
      if (!tab) return;

      const target = e.target as HTMLElement | null;
      if (target?.isContentEditable) return;

      e.preventDefault();
      onNavigate(tab);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [config, onNavigate]);
}
