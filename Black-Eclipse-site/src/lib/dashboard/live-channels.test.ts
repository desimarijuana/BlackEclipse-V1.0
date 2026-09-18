import { describe, it, expect } from 'vitest';
import {
  LIVE_CHANNELS, LIVE_CATEGORIES, channelById, defaultChannelIds,
  channelsByCategory, channelEmbedUrl, channelWatchUrl, safeEmbedUrl,
  parseCustomSource, customSourceToChannel,
} from './live-channels';

// The Live Intelligence channel registry + safety helpers. These pin the rules
// that matter: every channel is a real, well-formed official feed with a
// resolvable handle/id; the embed prefers a RESOLVED video id; and a
// user-supplied source can never load an arbitrary origin in an iframe.

describe('LIVE_CHANNELS integrity', () => {
  it('has unique ids and names', () => {
    const ids = LIVE_CHANNELS.map(c => c.id);
    const names = LIVE_CHANNELS.map(c => c.name);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(names).size).toBe(names.length);
  });

  it('only uses declared categories', () => {
    const valid = new Set(LIVE_CATEGORIES.map(c => c.id));
    for (const c of LIVE_CHANNELS) expect(valid.has(c.category)).toBe(true);
  });

  it('gives every youtube channel a resolvable handle or channel id', () => {
    for (const c of LIVE_CHANNELS) {
      if (c.type !== 'youtube') continue;
      const ok = (c.youtubeChannelId && /^UC[\w-]{22}$/.test(c.youtubeChannelId))
        || (c.youtubeHandle && /^@[\w.-]+$/.test(c.youtubeHandle))
        || (c.youtubeVideoId && /^[\w-]{11}$/.test(c.youtubeVideoId));
      expect(ok, `${c.id} has no resolvable youtube target`).toBeTruthy();
    }
  });

  it('prefers a handle for live resolution (the /channel/<UC>/live trap)', () => {
    // Every built-in youtube channel should carry a handle: YouTube's
    // /channel/<UC>/live endpoint silently fails for many of them.
    const youtube = LIVE_CHANNELS.filter(c => c.type === 'youtube' && !c.youtubeVideoId);
    const withHandle = youtube.filter(c => c.youtubeHandle);
    expect(withHandle.length).toBe(youtube.length);
  });

  it('carries a truthful lastKnownStatus', () => {
    const valid = new Set(['live', 'offline', 'unverified']);
    for (const c of LIVE_CHANNELS) expect(valid.has(c.lastKnownStatus)).toBe(true);
  });

  it('never carries a non-https embed url', () => {
    for (const c of LIVE_CHANNELS) {
      if (c.type === 'embed' && c.url) expect(c.url.startsWith('https://')).toBe(true);
    }
  });

  it('is finance/market-scoped — no entertainment categories', () => {
    const allowed = new Set(LIVE_CATEGORIES.map(c => c.id));
    const banned = ['entertainment', 'sport', 'sports', 'music', 'film', 'lifestyle', 'movies'];
    for (const c of LIVE_CHANNELS) {
      expect(allowed.has(c.category)).toBe(true);
      expect(banned.includes(c.category)).toBe(false);
    }
  });

  it('ships a non-empty default selection of channels that resolved live', () => {
    const defs = defaultChannelIds();
    expect(defs.length).toBeGreaterThan(0);
    for (const id of defs) {
      const c = channelById(id);
      expect(c).toBeDefined();
      // A default that was never observed live would greet the user with an error.
      expect(c!.lastKnownStatus, `${id} is enabled but not known-live`).toBe('live');
    }
  });
});

describe('channelsByCategory', () => {
  it('groups in LIVE_CATEGORIES order and drops empty groups', () => {
    const groups = channelsByCategory();
    const order = groups.map(g => g.category.id);
    const expected = LIVE_CATEGORIES.map(c => c.id).filter(id =>
      LIVE_CHANNELS.some(c => c.category === id));
    expect(order).toEqual(expected);
    expect(groups.every(g => g.channels.length > 0)).toBe(true);
  });
});

describe('channelEmbedUrl', () => {
  const bloomberg = channelById('bloomberg-tv')!;

  it('prefers a RESOLVED video id (the form that actually plays)', () => {
    const url = channelEmbedUrl(bloomberg, { muted: true, autoplay: true, resolvedVideoId: 'QB5BNdBFujE' })!;
    expect(url.startsWith('https://www.youtube-nocookie.com/embed/QB5BNdBFujE?')).toBe(true);
    expect(url).toContain('autoplay=1');
    expect(url).toContain('mute=1');
    expect(url).not.toContain('live_stream');
  });

  it('falls back to live_stream with the HANDLE when unresolved', () => {
    const url = channelEmbedUrl(bloomberg, { muted: false, autoplay: false })!;
    expect(url).toContain('/embed/live_stream?channel=');
    expect(url).toContain(encodeURIComponent('@markets'));
    expect(url).toContain('autoplay=0');
  });

  it('ignores a malformed resolved id and falls back safely', () => {
    const url = channelEmbedUrl(bloomberg, { muted: true, autoplay: true, resolvedVideoId: 'nope' });
    expect(url).toContain('live_stream');
  });

  it('returns null for a youtube channel with no target at all', () => {
    expect(channelEmbedUrl(
      { id: 'x', name: 'x', category: 'financial', type: 'youtube', lastKnownStatus: 'unverified', enabled: true },
      { muted: true, autoplay: true },
    )).toBeNull();
  });

  it('routes embed channels through the allowlist', () => {
    const embed = customSourceToChannel({ kind: 'embed', url: 'https://player.vimeo.com/video/123' });
    expect(channelEmbedUrl(embed, { muted: true, autoplay: true }))
      .toBe('https://player.vimeo.com/video/123');
  });
});

describe('safeEmbedUrl — SSRF/host allowlist', () => {
  it('accepts https allowlisted hosts', () => {
    expect(safeEmbedUrl('https://www.youtube.com/embed/abc')).toBeTruthy();
    expect(safeEmbedUrl('https://player.vimeo.com/video/1')).toBeTruthy();
  });

  it('rejects non-https, unknown hosts, and garbage', () => {
    expect(safeEmbedUrl('http://www.youtube.com/embed/abc')).toBeNull();
    expect(safeEmbedUrl('https://evil.example.com/x')).toBeNull();
    expect(safeEmbedUrl('javascript:alert(1)')).toBeNull();
    expect(safeEmbedUrl('data:text/html,<script>')).toBeNull();
    expect(safeEmbedUrl('not a url')).toBeNull();
  });

  it('rejects a lookalike host', () => {
    expect(safeEmbedUrl('https://www.youtube.com.evil.com/x')).toBeNull();
  });
});

describe('parseCustomSource', () => {
  it('accepts ids, handles, URLs, and safe embeds', () => {
    expect(parseCustomSource('UCIALMKvObZNtJ6AmdCLP7Lg')).toEqual({ kind: 'channel', id: 'UCIALMKvObZNtJ6AmdCLP7Lg' });
    expect(parseCustomSource('@SkyNews')).toEqual({ kind: 'channel', id: '@SkyNews' });
    expect(parseCustomSource('dQw4w9WgXcQ')).toEqual({ kind: 'video', id: 'dQw4w9WgXcQ' });
    expect(parseCustomSource('https://youtu.be/dQw4w9WgXcQ')).toEqual({ kind: 'video', id: 'dQw4w9WgXcQ' });
    expect(parseCustomSource('https://www.youtube.com/@SkyNews')).toEqual({ kind: 'channel', id: '@SkyNews' });
    expect(parseCustomSource('https://player.vimeo.com/video/123')).toEqual({ kind: 'embed', url: 'https://player.vimeo.com/video/123' });
  });

  it('treats a YouTube channel page as a channel, never as an embed', () => {
    // Regression: a youtube.com/@handle URL shares a host with the embed
    // allowlist but is NOT embeddable — YouTube refuses to frame channel pages.
    const parsed = parseCustomSource('https://www.youtube.com/@geonews');
    expect(parsed).toEqual({ kind: 'channel', id: '@geonews' });
  });

  it('rejects unusable or unsafe input', () => {
    expect(parseCustomSource('')).toBeNull();
    expect(parseCustomSource('not a source')).toBeNull();
    expect(parseCustomSource('https://evil.example.com/x')).toBeNull();
  });
});

describe('channelWatchUrl', () => {
  it('links a handle to /live and a video to /watch', () => {
    expect(channelWatchUrl(channelById('bloomberg-tv')!)).toBe('https://www.youtube.com/@markets/live');
    expect(channelWatchUrl(customSourceToChannel({ kind: 'video', id: 'dQw4w9WgXcQ' })))
      .toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  });
});
