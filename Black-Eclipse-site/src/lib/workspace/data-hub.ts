'use client';

// ── DataHub — client-side pub/sub data layer for widgets ────────────────────
// Every widget subscribes to topics (e.g. `market:quote:AAPL`). The hub batches
// fetches per topic, caches with a TTL, and fans results out to all subscribers.
// Hidden widgets unsubscribe so they don't burn rate limits. A failed topic only
// marks that topic UNAVAILABLE — the rest of the dashboard stays live.
//
// This is the foundation for the 36-widget catalog and the live side panel.

import { useCallback, useEffect, useRef, useState } from 'react';

/** Data-source provenance tag (spec §38). */
export type DataSource = 'LIVE' | 'CACHED' | 'HISTORICAL' | 'DEMO' | 'ESTIMATED' | 'UNAVAILABLE';

export interface HubEntry<T = unknown> {
  data: T | null;
  source: DataSource;
  updatedAt: number | null;
  error?: string;
}

export interface HubTopic {
  /** Stable topic id (e.g. 'market:quote:AAPL'). */
  id: string;
  /** Fetch the topic's data. Return null to mark UNAVAILABLE. */
  fetch: () => Promise<unknown>;
  /** Cache TTL in ms. */
  ttl: number;
  /** Refresh cadence in ms (0 = no auto-refresh). */
  interval?: number;
}

type Listener = (entry: HubEntry) => void;

interface TopicState {
  entry: HubEntry;
  listeners: Set<Listener>;
  lastFetch: number;
  timer: ReturnType<typeof setInterval> | null;
  inFlight: boolean;
}

const DEFAULT_TTL = 60_000;

class DataHub {
  private topics = new Map<string, TopicState>();

  /** Register a topic definition (idempotent). */
  register(topic: HubTopic): void {
    if (this.topics.has(topic.id)) return;
    this.topics.set(topic.id, {
      entry: { data: null, source: 'UNAVAILABLE', updatedAt: null },
      listeners: new Set(),
      lastFetch: 0,
      timer: null,
      inFlight: false,
    });
  }

  /** Subscribe a listener to a topic. Returns an unsubscribe fn. */
  subscribe(id: string, listener: Listener): () => void {
    const state = this.topics.get(id);
    if (!state) return () => {};
    state.listeners.add(listener);
    // If we have fresh data, deliver it immediately.
    if (state.entry.data !== null) listener(state.entry);
    // Start the auto-refresh timer if configured and not already running.
    const topic = this.topicDef(id);
    if (topic?.interval && !state.timer) {
      state.timer = setInterval(() => void this.refresh(id), topic.interval);
    }
    // Kick off a fetch if we have nothing yet.
    if (state.entry.data === null) void this.refresh(id);
    return () => this.unsubscribe(id, listener);
  }

  private unsubscribe(id: string, listener: Listener): void {
    const state = this.topics.get(id);
    if (!state) return;
    state.listeners.delete(listener);
    // Stop the timer when the last listener leaves (hidden widget → no burn).
    if (state.listeners.size === 0 && state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
  }

  /** Force-refresh a topic (used by F5 fan-out). */
  async refresh(id: string): Promise<void> {
    const state = this.topics.get(id);
    const topic = this.topicDef(id);
    if (!state || !topic || state.inFlight) return;
    state.inFlight = true;
    try {
      const data = await topic.fetch();
      const now = Date.now();
      state.entry = {
        data,
        source: data === null ? 'UNAVAILABLE' : now - state.lastFetch < topic.ttl ? 'CACHED' : 'LIVE',
        updatedAt: now,
      };
      state.lastFetch = now;
      this.emit(id);
    } catch (err) {
      state.entry = {
        data: null,
        source: 'UNAVAILABLE',
        updatedAt: Date.now(),
        error: err instanceof Error ? err.message : String(err),
      };
      this.emit(id);
    } finally {
      state.inFlight = false;
    }
  }

  /** Force-refresh every registered topic (F5 fan-out). */
  refreshAll(): void {
    for (const id of this.topics.keys()) void this.refresh(id);
  }

  /** Read the current entry for a topic (for non-hook consumers). */
  get(id: string): HubEntry {
    return this.topics.get(id)?.entry ?? { data: null, source: 'UNAVAILABLE', updatedAt: null };
  }

  private emit(id: string): void {
    const state = this.topics.get(id);
    if (!state) return;
    for (const l of state.listeners) l(state.entry);
  }

  private topicDef(id: string): HubTopic | undefined {
    return this.defs.get(id);
  }

  private defs = new Map<string, HubTopic>();
  registerDef(topic: HubTopic): void {
    this.defs.set(topic.id, topic);
    this.register(topic);
  }
}

/** Singleton hub shared across the app. */
export const dataHub = new DataHub();

/** Register a topic definition (call once at module load). */
export function registerTopic(topic: HubTopic): void {
  dataHub.registerDef(topic);
}

/** React hook: subscribe a component to a topic. */
export function useTopic<T = unknown>(id: string): HubEntry<T> {
  const [entry, setEntry] = useState<HubEntry<T>>(() => dataHub.get(id) as HubEntry<T>);
  const idRef = useRef(id);
  idRef.current = id;

  useEffect(() => {
    const unsub = dataHub.subscribe(id, (e) => setEntry(e as HubEntry<T>));
    return unsub;
  }, [id]);

  return entry;
}

/** React hook: force-refresh a set of topics (F5 fan-out). */
export function useRefreshAll(): () => void {
  return useCallback(() => dataHub.refreshAll(), []);
}

/** Convenience: build a topic that fetches a JSON endpoint. */
export function jsonTopic<T = unknown>(
  id: string,
  url: string,
  opts: { ttl?: number; interval?: number } = {},
): HubTopic {
  return {
    id,
    ttl: opts.ttl ?? DEFAULT_TTL,
    interval: opts.interval,
    fetch: async () => {
      const res = await fetch(url);
      if (!res.ok) return null;
      return (await res.json()) as T;
    },
  };
}

export { DEFAULT_TTL };
