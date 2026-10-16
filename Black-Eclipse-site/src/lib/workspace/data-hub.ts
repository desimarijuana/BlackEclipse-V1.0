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
export type DataSource = 'LIVE' | 'CACHED' | 'HISTORICAL' | 'DEMO' | 'ESTIMATED' | 'CUSTOM' | 'UNAVAILABLE';

export interface HubEntry<T = unknown> {
  data: T | null;
  source: DataSource;
  updatedAt: number | null;
  error?: string;
  /** Connector/provider that served the data (server-reported), if any. */
  sourceId?: string;
}

/**
 * A fetch may return raw data (provenance inferred as LIVE/CACHED) or an
 * envelope that carries the SERVER's provenance. Custom connectors report
 * `CUSTOM`/`HISTORICAL`; the hub never invents a tag for them.
 */
export interface TopicPayload<T = unknown> {
  data: T | null;
  source?: DataSource;
  sourceId?: string;
}

export type TopicFetch<T = unknown> = () => Promise<T | TopicPayload<T> | null>;

export interface HubTopic {
  /** Stable topic id (e.g. 'market:quote:AAPL'). */
  id: string;
  /** Fetch the topic's data. Return null to mark UNAVAILABLE. */
  fetch: TopicFetch;
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

const DATA_SOURCES: readonly DataSource[] = [
  'LIVE', 'CACHED', 'HISTORICAL', 'DEMO', 'ESTIMATED', 'CUSTOM', 'UNAVAILABLE',
];

/**
 * Distinguish a raw payload from a provenance envelope. A topic that wants to
 * report server-side provenance returns `{ data, source }` where `source` is a
 * recognised DataSource tag; everything else is treated as plain data and tagged
 * LIVE/CACHED by the hub as before. Requiring a valid tag means an ordinary
 * payload that happens to contain a `data` key is never accidentally unwrapped.
 */
function normalizePayload<T>(returned: T | TopicPayload<T> | null): TopicPayload<T> {
  if (returned === null || returned === undefined) return { data: null };
  if (typeof returned === 'object' && !Array.isArray(returned)) {
    const candidate = returned as TopicPayload<T>;
    if (typeof candidate.source === 'string' && DATA_SOURCES.includes(candidate.source)) {
      return { data: candidate.data ?? null, source: candidate.source, sourceId: candidate.sourceId };
    }
  }
  return { data: returned as T };
}

class DataHub {
  private topics = new Map<string, TopicState>();

  constructor() {
    // A backgrounded tab must not keep every auto-refresh topic polling the
    // single-threaded server. The interval itself pauses while hidden (see
    // subscribe); becoming visible again triggers ONE catch-up refresh of the
    // topics that currently have listeners, so data is fresh on return without
    // waking dormant topics nobody is watching.
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) this.refreshVisible();
      });
    }
  }

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
      state.timer = setInterval(() => {
        // Skip the tick while the tab is hidden — the interval keeps running so
        // it resumes instantly on return, but no request goes out in the
        // background. `refresh` also guards with inFlight, so a catch-up on
        // visibility never double-fetches.
        if (typeof document !== "undefined" && document.hidden) return;
        void this.refresh(id);
      }, topic.interval);
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
      const returned = await topic.fetch();
      const now = Date.now();
      const envelope = normalizePayload(returned);
      const inferred: DataSource =
        envelope.source ??
        (now - state.lastFetch < topic.ttl ? 'CACHED' : 'LIVE');
      state.entry = {
        data: envelope.data,
        source: envelope.data === null ? 'UNAVAILABLE' : inferred,
        updatedAt: now,
        sourceId: envelope.sourceId,
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

  /**
   * Refresh only the topics that currently have listeners. Used when the tab
   * becomes visible again after being hidden, so a backgrounded dashboard
   * catches up exactly the topics on screen — never dormant ones.
   */
  refreshVisible(): void {
    for (const [id, state] of this.topics) {
      if (state.listeners.size > 0) void this.refresh(id);
    }
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

interface CapabilityResponse<T> {
  ok: boolean;
  data: T | null;
  provenance: DataSource;
  source: string;
}

/**
 * Convenience: build a topic over the server capability route
 * (`GET /api/data/[capability]`). The route decides which connector serves the
 * request and reports provenance; the hub passes that through unchanged.
 */
export function capabilityTopic<T = unknown>(
  id: string,
  capability: string,
  params: Record<string, string> = {},
  opts: { ttl?: number; interval?: number } = {},
): HubTopic {
  const query = new URLSearchParams(params).toString();
  const url = `/api/data/${encodeURIComponent(capability.toLowerCase())}${query ? `?${query}` : ''}`;
  return {
    id,
    ttl: opts.ttl ?? DEFAULT_TTL,
    interval: opts.interval,
    fetch: async (): Promise<TopicPayload<T> | null> => {
      const res = await fetch(url);
      if (!res.ok) return null;
      const body = (await res.json()) as CapabilityResponse<T>;
      if (!body.ok || body.data === null) {
        return { data: null, source: body.provenance ?? 'UNAVAILABLE' };
      }
      return { data: body.data, source: body.provenance, sourceId: body.source };
    },
  };
}

export { DEFAULT_TTL };
