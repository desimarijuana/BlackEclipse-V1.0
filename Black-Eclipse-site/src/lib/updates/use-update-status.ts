'use client';

// ── Update status for the app UI ────────────────────────────────────────────
// One hook for "is a newer signed release available". Both the banner and the
// title-bar download button use it, so the two surfaces can never disagree.
//
// Mirrors the rules in the banner: the check is opt-out, a failure is silent
// here (Settings is where the user asked), and nothing polls when disabled.
// A new release is announced ONCE per version per session through the shared
// toast channel (`be:alert-notify`), so it is not missed behind a small dot.
//
// Cadence: first check after 2 s, then every 10 min, plus a revalidation when
// the window regains focus or the network returns (throttled). The server
// revalidates the signed manifest at most every 5 min, so a just-published
// release surfaces within minutes, not hours.

import { useCallback, useEffect, useRef, useState } from 'react';

import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import {
  DEFAULT_UPDATE_PREFS,
  loadUpdatePrefs,
  subscribeUpdatePrefs,
  type UpdatePrefs,
} from './prefs';
import type { UpdateStatus } from './types';

const FIRST_CHECK_MS = 2_000;
const RECHECK_MS = 10 * 60 * 1000;
/** Focus/resume checks are cheap (server cache 5 min), but not on every alt-tab. */
const WAKE_THROTTLE_MS = 60 * 1000;
/** One announcement per version per app session. */
const ANNOUNCED = new Set<string>();

function announce(status: UpdateStatus, prefs: UpdatePrefs) {
  const version = status.latestVersion;
  if (!status.ok || !status.available || !version) return;
  if (!prefs.enabled || version === prefs.skippedVersion) return;
  if (ANNOUNCED.has(version)) return;
  ANNOUNCED.add(version);
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(ALERT_NOTIFY_EVENT, {
      detail: {
        // A toast, not a ledger entry: this is an app notice, not a tab event.
        transient: true,
        title: `Eclipse v${version} is available`,
        body: status.installer
          ? 'Open the download menu to update — the signed installer is verified before it runs.'
          : 'Open the download menu to see the release.',
      },
    }),
  );
}

export interface UseUpdateStatus {
  /** null until the first answer (or when checks are off / the app is offline). */
  status: UpdateStatus | null;
  checking: boolean;
  prefs: UpdatePrefs;
  /** Force a check, bypassing the server's short manifest cache. */
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
      const next = (await res.json()) as UpdateStatus;
      setStatus(next);
      announce(next, prefsRef.current);
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
    // A release published while the window was in the background should surface
    // when the user comes back, not up to 10 minutes later. The server's TTL
    // bounds the upstream traffic; this only decides when to ask it.
    let lastWake = 0;
    const onWake = () => {
      if (document.hidden) return;
      const now = Date.now();
      if (now - lastWake < WAKE_THROTTLE_MS) return;
      lastWake = now;
      void check(false);
    };
    const onOnline = () => void check(false);
    document.addEventListener('visibilitychange', onWake);
    window.addEventListener('focus', onWake);
    window.addEventListener('online', onOnline);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onWake);
      window.removeEventListener('focus', onWake);
      window.removeEventListener('online', onOnline);
    };
  }, [prefs.enabled, check]);

  const refresh = useCallback(() => check(true), [check]);

  return { status, checking, prefs, refresh };
}
