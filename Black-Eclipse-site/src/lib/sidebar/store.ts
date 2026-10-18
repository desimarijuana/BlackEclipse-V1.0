// ── Sidebar customization store ──────────────────────────────────────────
// Client-side zustand store holding the user's sidebar config (order,
// visibility, shortcuts). Hydrated from localStorage after mount and written
// back on every change, so the sidebar and the Settings panel stay in sync
// without a prop-drilling chain.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import {
  defaultSidebarConfig,
  isNavGroup,
  loadSidebarConfig,
  saveSidebarConfig,
  type SidebarConfig,
  type NavGroup,
} from './config';
import type { AppTab } from '@/components/layout/sidebar';

export interface SidebarConfigStore {
  config: SidebarConfig;
  hydrated: boolean;
  /** Active top-level menu mode (Terminal vs Agentic). Shared so keyboard
   *  shortcuts and programmatic navigation can switch it, not just the UI. */
  mode: NavGroup;
  /** Merge a hydrated config from localStorage (client only, post-mount). */
  hydrate: () => void;
  setConfig: (cfg: SidebarConfig) => void;
  setMode: (mode: NavGroup) => void;
  toggleEnabled: (id: AppTab) => void;
  setShortcut: (id: AppTab, shortcut: string) => void;
  /** Move an item from one index to another (reorder). */
  move: (from: number, to: number) => void;
  reset: () => void;
}

/** Persisted top-level menu mode. */
export const SIDEBAR_MODE_KEY = 'be_sidebar_mode_v1';

export const useSidebarConfigStore = create<SidebarConfigStore>((set) => ({
  // SSR-consistent default; the real config is loaded on mount (avoids
  // hydration mismatch warnings).
  config: defaultSidebarConfig(),
  hydrated: false,
  mode: 'terminal',

  hydrate: () => {
    const config = loadSidebarConfig();
    saveSidebarConfig(config);
    let mode: NavGroup = 'terminal';
    if (typeof window !== 'undefined') {
      try {
        // Validated against the ONE mode list — an unknown/legacy value falls
        // back rather than putting the switcher into a mode it cannot render.
        const saved = localStorage.getItem(SIDEBAR_MODE_KEY);
        if (isNavGroup(saved)) mode = saved;
      } catch { /* private mode — keep the default */ }
    }
    set({ config, hydrated: true, mode });
  },

  setConfig: (config) => {
    saveSidebarConfig(config);
    set({ config });
  },

  setMode: (mode) => {
    if (typeof window !== 'undefined') {
      try { localStorage.setItem(SIDEBAR_MODE_KEY, mode); } catch { /* ignore */ }
    }
    set({ mode });
  },

  toggleEnabled: (id) =>
    set((s) => {
      const config = {
        sections: s.config.sections.map((x) => (x.id === id ? { ...x, enabled: !x.enabled } : x)),
      };
      saveSidebarConfig(config);
      return { config };
    }),

  setShortcut: (id, shortcut) =>
    set((s) => {
      // A key can only open one tab — assigning it here clears it elsewhere.
      const config = {
        sections: s.config.sections.map((x) => {
          if (x.id === id) return { ...x, shortcut };
          return x.shortcut === shortcut && shortcut !== '' ? { ...x, shortcut: '' } : x;
        }),
      };
      saveSidebarConfig(config);
      return { config };
    }),

  move: (from, to) =>
    set((s) => {
      const sections = [...s.config.sections];
      if (from < 0 || to < 0 || from >= sections.length || to >= sections.length || from === to) {
        return {};
      }
      const [item] = sections.splice(from, 1);
      sections.splice(to, 0, item);
      const config = { sections };
      saveSidebarConfig(config);
      return { config };
    }),

  reset: () => {
    const config = defaultSidebarConfig();
    saveSidebarConfig(config);
    set({ config });
  },
}));

/** Hydrate the sidebar config from localStorage once, on the client. */
export function useHydrateSidebarConfig() {
  const hydrate = useSidebarConfigStore((s) => s.hydrate);
  const hydrated = useSidebarConfigStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
