'use client';

// ── Update status for the app UI ────────────────────────────────────────────
// One hook for "is a newer signed release available". Both the banner and the
// title-bar download button use it, so the two surfaces can never disagree.
//
// Mirrors the rules in the banner: the check is opt-out, a failure is silent
// here (Settings is where the user asked), and nothing polls when disabled.
// The local route caches the verified manifest for 6 hours, so two mounted
// consumers cost one upstream fetch, not two.

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DEFAULT_UPDATE_PREFS,
  loadUpdatePrefs,
  subscribeUpdatePrefs,
  type UpdatePrefs,
} from './prefs';
import type { UpdateStatus } from './types';

const FIRST_CHECK_MS = 6_000;
const RECHECK_MS = 6 * 60 * 60 * 1000;

export interface UseUpdateStatus {
  /** null until the first answer (or when checks are off / the app is offline). */
  status: UpdateStatus | null;
  checking: boolean;
  prefs: UpdatePrefs;
  /** Force a check, bypassing the server's 6h manifest cache. */
  refresh: () => Promise<void>;
}

export function useUpdateStatus(): UseUpdateStatus {
  // Server and first client render must agree; localStorage is read in an effect.
  const [prefs, setPrefs] = useState<UpdatePrefs>(DEFAULT_UPDATE_PREFS);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  useEffect(() => {
    setPrefs(loadUpdatePrefs());
    return subscribeUpdatePrefs(() => setPrefs(loadUpdatePrefs()));
  }, []);

  const check = useCallback(async (refresh: boolean) => {
    if (!prefsRef.current.enabled) return;
    setChecking(true);
    try {
      const res = await fetch(`/api/updates${refresh ? '?refresh=1' : ''}`, {
        cache: 'no-store',
      });
      if (!res.ok) return;
      setStatus((await res.json()) as UpdateStatus);
    } catch {
      /* offline / server restarting — stay quiet, the interval retries */
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (!prefs.enabled) {
      setStatus(null);
      return;
    }
    const first = window.setTimeout(() => void check(false), FIRST_CHECK_MS);
    const timer = window.setInterval(() => void check(false), RECHECK_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [prefs.enabled, check]);

  const refresh = useCallback(() => check(true), [check]);

  return { status, checking, prefs, refresh };
}
