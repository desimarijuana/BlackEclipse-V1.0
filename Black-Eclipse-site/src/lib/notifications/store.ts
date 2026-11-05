'use client';

// ── Notification center ─────────────────────────────────────────────────────
// One client-side ledger of "something happened while you were elsewhere".
// Producers (price alerts, agent approvals, background task completion) push
// items tagged with the AppTab that owns them; the sidebar renders a red
// unread badge per tab, and the visible tab's items are auto-marked read.
//
// Delivery side effects (toast, desktop notification, sound) live in
// `components/layout/alert-notification-provider.tsx` — this store is the
// ledger only, so producers and UI never duplicate dedupe/read logic.
//
// Persistence mirrors the other `be_*` stores: localStorage, hydrated after
// mount so SSR output stays stable.

import { useEffect } from 'react';
import { create } from 'zustand';
import type { AppTab } from '@/lib/app-tabs';
import type { SoundName } from '@/lib/sounds';
import { APP_TABS } from '@/lib/search/deep-link';

export type NotificationKind = 'alert' | 'task' | 'approval' | 'agent' | 'bot';

export interface AppNotification {
  /** Stable dedupe key (e.g. an alert event id or `task:<id>:<stamp>`). */
  id: string;
  /** The tab that owns this notification — drives the red badge. */
  tab: AppTab;
  kind: NotificationKind;
  title: string;
  body: string;
  /** Epoch ms. */
  at: number;
  read: boolean;
}

export interface NotificationInput {
  /** Absent = generated (no cross-tick dedupe for that caller). */
  id?: string;
  tab: AppTab;
  kind?: NotificationKind;
  title: string;
  body?: string;
}

/**
 * Detail accepted by the shared `be:alert-notify` window event — the one
 * channel any surface uses to raise a toast + desktop notification pair.
 * `tab`/`kind` route it into the center; `sound` requests a cue.
 */
export interface NotificationRequest {
  id?: string;
  title?: string;
  body?: string;
  tab?: AppTab;
  kind?: NotificationKind;
  sound?: SoundName;
  /** Alert id, so a re-fire replaces the previous desktop notification. */
  alertId?: string;
  /** Test raises a toast but is never recorded in the center. */
  test?: boolean;
}

export const NOTIFICATIONS_STORAGE_KEY = 'be_notifications_v1';

/** Ring capacity; older items fall off the tail. */
export const MAX_NOTIFICATIONS = 100;

const VALID_TABS = new Set<string>(APP_TABS);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isStoredNotification(value: unknown): value is AppNotification {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === 'string' &&
    typeof value.tab === 'string' &&
    VALID_TABS.has(value.tab) &&
    typeof value.title === 'string' &&
    (value.body === undefined || typeof value.body === 'string') &&
    typeof value.at === 'number' &&
    typeof value.read === 'boolean'
  );
}

function read(): AppNotification[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(NOTIFICATIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    const list = Array.isArray(parsed) ? parsed : isRecord(parsed) ? parsed.items : null;
    if (!Array.isArray(list)) return [];
    return list
      .filter(isStoredNotification)
      .map((n) => ({ ...n, kind: n.kind ?? 'alert', body: n.body ?? '' }))
      .slice(0, MAX_NOTIFICATIONS);
  } catch {
    return [];
  }
}

function persist(items: AppNotification[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify({ items }));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function makeId(): string {
  return `n_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Unread counts per tab, for the sidebar badges. */
export function unreadCountsByTab(items: AppNotification[]): Partial<Record<AppTab, number>> {
  const counts: Partial<Record<AppTab, number>> = {};
  for (const item of items) {
    if (item.read) continue;
    counts[item.tab] = (counts[item.tab] ?? 0) + 1;
  }
  return counts;
}

/** Total unread across every tab (aggregate badge). */
export function totalUnread(items: AppNotification[]): number {
  let n = 0;
  for (const item of items) if (!item.read) n += 1;
  return n;
}

export interface NotificationsStore {
  /** Newest first, capped at MAX_NOTIFICATIONS. */
  items: AppNotification[];
  /** The tab the operator is currently looking at (set by the SPA shell). */
  activeTab: AppTab | null;
  hydrated: boolean;
  hydrate: () => void;
  /** Record one event. Returns false when the id was already recorded. */
  push: (input: NotificationInput) => boolean;
  markTabRead: (tab: AppTab) => void;
  /** Clear the unread state across every tab (header "Mark all read"). */
  markAllRead: () => void;
  /**
   * Track the visible tab AND mark its items read — a notification the
   * operator can already see never badges.
   */
  setActiveTab: (tab: AppTab) => void;
}

export const useNotificationsStore = create<NotificationsStore>((set, get) => ({
  items: [],
  activeTab: null,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ items: read(), hydrated: true });
  },

  push: (input) => {
    const { items, activeTab } = get();
    const id = input.id ?? makeId();
    if (items.some((n) => n.id === id)) return false;
    const item: AppNotification = {
      id,
      tab: input.tab,
      kind: input.kind ?? 'alert',
      title: input.title,
      body: input.body ?? '',
      at: Date.now(),
      // Visible tab: it is already in front of the operator — no badge.
      read: input.tab === activeTab,
    };
    const next = [item, ...items].slice(0, MAX_NOTIFICATIONS);
    persist(next);
    set({ items: next });
    return true;
  },

  markTabRead: (tab) => {
    const { items } = get();
    if (!items.some((n) => n.tab === tab && !n.read)) return;
    const next = items.map((n) => (n.tab === tab && !n.read ? { ...n, read: true } : n));
    persist(next);
    set({ items: next });
  },

  markAllRead: () => {
    const { items } = get();
    if (!items.some((n) => !n.read)) return;
    const next = items.map((n) => (n.read ? n : { ...n, read: true }));
    persist(next);
    set({ items: next });
  },

  setActiveTab: (tab) => {
    if (get().activeTab !== tab) set({ activeTab: tab });
    get().markTabRead(tab);
  },
}));

/** Hydrate the notification ledger from localStorage once, on the client. */
export function useHydrateNotifications(): void {
  const hydrate = useNotificationsStore((s) => s.hydrate);
  const hydrated = useNotificationsStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
