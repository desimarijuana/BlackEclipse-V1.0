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
  loadSidebarConfig,
  saveSidebarConfig,
  normalizeSidebarConfig,
  isPinnedSection,
  type SidebarConfig,
} from './config';
import type { AppTab } from '@/components/layout/sidebar';

export interface SidebarConfigStore {
  config: SidebarConfig;
  hydrated: boolean;
  /** Merge a hydrated config from localStorage (client only, post-mount). */
  hydrate: () => void;
  setConfig: (cfg: SidebarConfig) => void;
  toggleEnabled: (id: AppTab) => void;
  setShortcut: (id: AppTab, shortcut: string) => void;
  /** Move an item from one index to another (reorder). */
  move: (from: number, to: number) => void;
  reset: () => void;
}

export const useSidebarConfigStore = create<SidebarConfigStore>((set) => ({
  // SSR-consistent default; the real config is loaded on mount (avoids
  // hydration mismatch warnings).
  config: defaultSidebarConfig(),
  hydrated: false,

  hydrate: () => {
    const config = loadSidebarConfig();
    saveSidebarConfig(config);
    set({ config, hydrated: true });
  },

  setConfig: (config) => {
    saveSidebarConfig(config);
    set({ config });
  },

  toggleEnabled: (id) =>
    set((s) => {
      if (isPinnedSection(id)) return {};
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
      // Pinned items stay locked at the top: neither the dragged item nor the
      // drop slot may fall inside the pinned region.
      if (isPinnedSection(sections[from].id) || isPinnedSection(sections[to].id)) {
        return {};
      }
      const [item] = sections.splice(from, 1);
      sections.splice(to, 0, item);
      const config = normalizeSidebarConfig({ sections });
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
