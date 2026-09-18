import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  defaultSettings, readSettings, enabledChannels, resolveActiveChannel,
} from './live-intelligence-store';
import { LIVE_CHANNELS, defaultChannelIds } from './live-channels';

// The selection-store logic. localStorage is stubbed so normalize/fallback rules
// are pinned without a browser.

class MemoryStorage {
  private map = new Map<string, string>();
  getItem(k: string) { return this.map.has(k) ? this.map.get(k)! : null; }
  setItem(k: string, v: string) { this.map.set(k, v); }
  removeItem(k: string) { this.map.delete(k); }
  clear() { this.map.clear(); }
  key(i: number) { return [...this.map.keys()][i] ?? null; }
  get length() { return this.map.size; }
}

const KEY = 'be_live_intelligence_v1';
let store: MemoryStorage;

beforeEach(() => {
  store = new MemoryStorage();
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: store,
    dispatchEvent: () => true,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
});
afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe('defaultSettings', () => {
  it('enables exactly the shipped defaults and points defaultId at one of them', () => {
    const s = defaultSettings();
    expect(s.enabledIds).toEqual(defaultChannelIds());
    expect(s.enabledIds).toContain(s.defaultId);
    expect(s.custom).toEqual([]);
  });
});

describe('readSettings', () => {
  it('falls back to defaults when storage is empty or corrupt', () => {
    expect(readSettings().enabledIds).toEqual(defaultChannelIds());
    store.setItem(KEY, '{not json');
    expect(readSettings().enabledIds).toEqual(defaultChannelIds());
  });

  it('honours an explicit empty selection (user disabled everything)', () => {
    store.setItem(KEY, JSON.stringify({ enabledIds: [], defaultId: '', custom: [] }));
    const s = readSettings();
    expect(s.enabledIds).toEqual([]);
    expect(s.defaultId).toBe('');
  });

  it('drops unknown ids and repairs a default that is not enabled', () => {
    store.setItem(KEY, JSON.stringify({
      enabledIds: ['bloomberg-tv', 'not-a-real-channel'],
      defaultId: 'cnbc-tv', // known, but NOT enabled
      custom: [],
    }));
    const s = readSettings();
    expect(s.enabledIds).toEqual(['bloomberg-tv']);
    expect(s.defaultId).toBe('bloomberg-tv'); // repaired to the first enabled
  });

  it('keeps a valid custom source and allows it as the default', () => {
    store.setItem(KEY, JSON.stringify({
      enabledIds: [],
      defaultId: 'custom:video:dQw4w9WgXcQ',
      custom: [{ id: 'custom:video:dQw4w9WgXcQ', name: 'Mine', category: 'financial', type: 'youtube', youtubeVideoId: 'dQw4w9WgXcQ', enabled: true }],
    }));
    const s = readSettings();
    expect(s.custom).toHaveLength(1);
    expect(s.defaultId).toBe('custom:video:dQw4w9WgXcQ');
  });
});

describe('enabledChannels', () => {
  it('returns catalog order for built-ins, then customs', () => {
    const s = { enabledIds: ['cnbc-tv', 'bloomberg-tv'], defaultId: 'bloomberg-tv', custom: [] };
    const list = enabledChannels(s);
    // Catalog order is bloomberg before cnbc regardless of the enabledIds order.
    expect(list.map(c => c.id)).toEqual(['bloomberg-tv', 'cnbc-tv']);
  });

  it('returns empty when nothing is enabled', () => {
    expect(enabledChannels({ enabledIds: [], defaultId: '', custom: [] })).toEqual([]);
  });
});

describe('resolveActiveChannel — the empty-state guarantee', () => {
  it('returns null when no channel is enabled (widget must show NO LIVE SOURCES)', () => {
    const s = { enabledIds: [], defaultId: '', custom: [] };
    expect(resolveActiveChannel(enabledChannels(s), s)).toBeNull();
  });

  it('prefers the instance choice, then the default, then the first enabled', () => {
    const s = { enabledIds: ['bloomberg-tv', 'cnbc-tv'], defaultId: 'cnbc-tv', custom: [] };
    const enabled = enabledChannels(s);
    expect(resolveActiveChannel(enabled, s, 'bloomberg-tv')!.id).toBe('bloomberg-tv');
    expect(resolveActiveChannel(enabled, s)!.id).toBe('cnbc-tv');
    // An instance choice that is no longer enabled falls back to the first.
    expect(resolveActiveChannel(enabled, s, 'sky-news')!.id).toBe('bloomberg-tv');
  });

  it('never returns a disabled or unknown channel', () => {
    const s = { enabledIds: ['sky-news'], defaultId: 'sky-news', custom: [] };
    const enabled = enabledChannels(s);
    const picked = resolveActiveChannel(enabled, s, 'cnbc-tv')!;
    expect(LIVE_CHANNELS.some(c => c.id === picked.id)).toBe(true);
    expect(picked.id).toBe('sky-news');
  });
});
