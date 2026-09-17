'use client';

// ── Display timezone — the client half ───────────────────────────────────────
// Mirrors `lib/currency.ts`: a localStorage preference plus a change event, so
// every panel agrees on one zone without prop-drilling.
//
// Why it exists: Investor Eye's timestamps were hard-coded to UTC, so an operator
// had to do mental arithmetic to answer "when did this happen?". Now the zone is
// a preference, and every formatted time PRINTS its zone — an unlabelled clock
// is impossible.
//
// The formatting itself lives in `lib/investor-eye/format.ts` (server-safe); this
// module only holds the browser preference and the React hook.

import { useEffect, useState } from 'react';
import { DEFAULT_TIMEZONE } from '@/lib/investor-eye/format';

const STORAGE_KEY = 'eclipse_display_timezone';

/** A short, useful list. Any IANA zone the browser knows is also accepted. */
export const DISPLAY_TIMEZONES: Array<{ id: string; label: string }> = [
  { id: 'UTC', label: 'UTC' },
  { id: 'America/New_York', label: 'New York' },
  { id: 'America/Chicago', label: 'Chicago' },
  { id: 'America/Los_Angeles', label: 'Los Angeles' },
  { id: 'America/Sao_Paulo', label: 'São Paulo' },
  { id: 'Europe/London', label: 'London' },
  { id: 'Europe/Paris', label: 'Paris' },
  { id: 'Europe/Berlin', label: 'Berlin' },
  { id: 'Europe/Moscow', label: 'Moscow' },
  { id: 'Africa/Johannesburg', label: 'Johannesburg' },
  { id: 'Asia/Dubai', label: 'Dubai' },
  { id: 'Asia/Karachi', label: 'Karachi' },
  { id: 'Asia/Kolkata', label: 'Kolkata' },
  { id: 'Asia/Shanghai', label: 'Shanghai' },
  { id: 'Asia/Tokyo', label: 'Tokyo' },
  { id: 'Asia/Singapore', label: 'Singapore' },
  { id: 'Australia/Sydney', label: 'Sydney' },
];

/** The browser's own zone, when the platform exposes it. */
export function browserTimeZone(): string {
  if (typeof Intl === 'undefined') return DEFAULT_TIMEZONE;
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_TIMEZONE;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/** True when `tz` is a zone this runtime accepts. */
export function isValidTimeZone(tz: string): boolean {
  if (!tz) return false;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

export function getDisplayTimeZone(): string {
  if (typeof window === 'undefined') return DEFAULT_TIMEZONE;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && isValidTimeZone(stored)) return stored;
  } catch { /* private mode */ }
  return DEFAULT_TIMEZONE;
}

export function setDisplayTimeZone(tz: string): void {
  if (!isValidTimeZone(tz)) return;
  try {
    localStorage.setItem(STORAGE_KEY, tz);
    window.dispatchEvent(new CustomEvent('eclipse:timezone-change', { detail: tz }));
  } catch { /* private mode — in-memory only */ }
}

/**
 * Subscribe to the display timezone. Re-renders on change so panels update
 * immediately rather than needing a reload.
 */
export function useDisplayTimeZone(): string {
  const [tz, setTz] = useState<string>(() => getDisplayTimeZone());

  useEffect(() => {
    const onChange = () => setTz(getDisplayTimeZone());
    window.addEventListener('eclipse:timezone-change', onChange);
    // Another tab changing the preference should be picked up too.
    const onStorage = (e: StorageEvent) => { if (e.key === STORAGE_KEY) onChange(); };
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('eclipse:timezone-change', onChange);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return tz;
}
