'use client';

// ── Live Intelligence — channel selection store ──────────────────────────────
// The user's Live Intelligence channel configuration, persisted to localStorage
// and reactive across components/tabs (the same storage-event pattern as the
// price ribbon and the guest watchlist).
//
// What lives here (shared, app-level):
//   · which built-in channels are enabled
//   · the default channel a new widget opens on
//   · optional custom sources (advanced; validated by parseCustomSource)
//
// What does NOT live here: the channel a specific widget instance is currently
// watching. That is per-instance UI state, persisted by the widget itself under
// its own placement id — two Live Intelligence cards can watch different feeds.

import { useCallback, useEffect, useState } from 'react';
import {
  LIVE_CHANNELS, defaultChannelIds,
  parseCustomSource, customSourceToChannel, type LiveChannel,
} from './live-channels';

const STORAGE_KEY = 'be_live_intelligence_v1';
const EVENT = 'be:live-intelligence-changed';

export interface LiveIntelligenceSettings {
  /** Enabled built-in channel ids. */
  enabledIds: string[];
  /** Default channel id (must be enabled, or a custom source id). */
  defaultId: string;
  /** Advanced: user-supplied sources, already validated on write. */
  custom: LiveChannel[];
}

export function defaultSettings(): LiveIntelligenceSettings {
  const enabledIds = defaultChannelIds();
  return { enabledIds, defaultId: enabledIds[0] ?? LIVE_CHANNELS[0].id, custom: [] };
}

function isCustomChannel(v: unknown): v is LiveChannel {
  if (typeof v !== 'object' || v === null) return false;
  const c = v as Partial<LiveChannel>;
  return typeof c.id === 'string' && typeof c.name === 'string'
    && (c.type === 'youtube' || c.type === 'video' || c.type === 'embed')
    && typeof c.enabled === 'boolean';
}

function normalize(raw: unknown): LiveIntelligenceSettings | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Partial<LiveIntelligenceSettings>;
  const known = new Set(LIVE_CHANNELS.map(c => c.id));
  const enabledIds = Array.isArray(r.enabledIds)
    ? r.enabledIds.filter((id): id is string => typeof id === 'string' && known.has(id))
    : defaultChannelIds();
  const custom = Array.isArray(r.custom) ? r.custom.filter(isCustomChannel) : [];
  const defaultId = typeof r.defaultId === 'string' ? r.defaultId : '';
  // A default that is no longer enabled/custom falls back to the first enabled.
  const validDefault = (known.has(defaultId) ? enabledIds.includes(defaultId) : false)
    || custom.some(c => c.id === defaultId);
  return {
    enabledIds,
    custom,
    defaultId: validDefault ? defaultId : (enabledIds[0] ?? custom[0]?.id ?? ''),
  };
}

/** Read the saved settings, falling back to the shipped defaults. */
export function readSettings(): LiveIntelligenceSettings {
  if (typeof window === 'undefined') return defaultSettings();
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null');
    const normalized = normalize(parsed);
    if (normalized) return normalized;
  } catch { /* corrupt storage — fall through */ }
  return defaultSettings();
}

function write(next: LiveIntelligenceSettings): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch { /* ignore quota/priv-mode errors */ }
}

/** The channels the user has enabled, built-in plus custom, in catalog order. */
export function enabledChannels(settings: LiveIntelligenceSettings): LiveChannel[] {
  const builtIn = LIVE_CHANNELS.filter(c => settings.enabledIds.includes(c.id));
  return [...builtIn, ...settings.custom];
}

/** Reactive settings hook. */
export function useLiveIntelligenceSettings() {
  const [settings, setSettings] = useState<LiveIntelligenceSettings>(defaultSettings);

  useEffect(() => {
    const sync = () => setSettings(readSettings());
    sync();
    window.addEventListener('storage', sync);
    window.addEventListener(EVENT, sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(EVENT, sync);
    };
  }, []);

  const commit = useCallback((next: LiveIntelligenceSettings) => {
    const normalized = normalize(next) ?? defaultSettings();
    write(normalized);
    setSettings(normalized);
  }, []);

  const toggleChannel = useCallback((id: string) => {
    setSettings(prev => {
      const has = prev.enabledIds.includes(id);
      const enabledIds = has ? prev.enabledIds.filter(x => x !== id) : [...prev.enabledIds, id];
      let defaultId = prev.defaultId;
      // Never leave the default pointing at a channel we just disabled.
      if (has && defaultId === id) defaultId = enabledIds[0] ?? prev.custom[0]?.id ?? '';
      const next = { ...prev, enabledIds, defaultId };
      write(next);
      return next;
    });
  }, []);

  const setDefault = useCallback((id: string) => {
    setSettings(prev => { const next = { ...prev, defaultId: id }; write(next); return next; });
  }, []);

  const addCustom = useCallback((raw: string, label: string): { ok: boolean; id?: string } => {
    const parsed = parseCustomSource(raw);
    if (!parsed) return { ok: false };
    const channel = customSourceToChannel(parsed, label.trim() || 'Custom source');
    setSettings(prev => {
      if (prev.custom.some(c => c.id === channel.id)) return prev;
      const next = { ...prev, custom: [...prev.custom, channel] };
      write(next);
      return next;
    });
    return { ok: true, id: channel.id };
  }, []);

  const removeCustom = useCallback((id: string) => {
    setSettings(prev => {
      const custom = prev.custom.filter(c => c.id !== id);
      const defaultId = prev.defaultId === id
        ? (prev.enabledIds[0] ?? custom[0]?.id ?? '')
        : prev.defaultId;
      const next = { ...prev, custom, defaultId };
      write(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => { write(defaultSettings()); setSettings(defaultSettings()); }, []);

  return { settings, enabled: enabledChannels(settings), toggleChannel, setDefault, addCustom, removeCustom, reset, commit };
}

/** Resolve the channel a widget instance should show, given its saved choice. */
export function resolveActiveChannel(
  enabled: LiveChannel[],
  settings: LiveIntelligenceSettings,
  preferredId?: string,
): LiveChannel | null {
  if (enabled.length === 0) return null;
  const wanted = preferredId || settings.defaultId;
  return enabled.find(c => c.id === wanted) ?? enabled[0];
}
