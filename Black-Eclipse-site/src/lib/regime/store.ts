// ── Market Regime scope store ────────────────────────────────────────────────
// Persisted choice of which market the regime reads: the active selected market,
// US, or global. Shared by the Aurora glow and the top-bar control so both agree.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import type { RegimeScope } from './types';

const STORAGE_KEY = 'be_regime_scope_v1';

function isScope(v: unknown): v is RegimeScope {
  return v === 'selected' || v === 'us' || v === 'global';
}

function loadScope(): RegimeScope {
  if (typeof window === 'undefined') return 'selected';
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return isScope(v) ? v : 'selected';
  } catch {
    return 'selected';
  }
}

export interface RegimeScopeStore {
  scope: RegimeScope;
  hydrated: boolean;
  hydrate: () => void;
  setScope: (scope: RegimeScope) => void;
}

export const useRegimeScopeStore = create<RegimeScopeStore>((set) => ({
  scope: 'selected',
  hydrated: false,
  hydrate: () => set({ scope: loadScope(), hydrated: true }),
  setScope: (scope) => {
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(STORAGE_KEY, scope);
      } catch {
        /* quota / private mode — in-memory only */
      }
    }
    set({ scope });
  },
}));

/** Hydrate the regime scope from localStorage once, on the client. */
export function useHydrateRegimeScope() {
  const hydrate = useRegimeScopeStore((s) => s.hydrate);
  const hydrated = useRegimeScopeStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
