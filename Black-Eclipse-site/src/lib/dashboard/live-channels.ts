// ── Live Intelligence — channel registry ─────────────────────────────────────
// The curated channel catalog for the Command Center's Live Intelligence widget,
// plus pure, dependency-free helpers for embedding and safety.
//
// HONESTY RULES (do not relax these):
//   · Every channel below is a broadcaster's OWN official feed. Every channel id
//     and handle was resolved from that network's own YouTube page — never
//     invented. Nothing was scraped from an unauthorised restream.
//   · We do NOT proxy, restream, scrape media, or redistribute anything. The
//     player embeds the provider's official player directly.
//   · Live/offline status is NOT hardcoded here as fact. YouTube live video ids
//     ROTATE, so the runtime resolver (live-resolver.ts, server-side, cached)
//     determines the current id/status. `lastKnownStatus` is only the state
//     observed the last time these were checked, for the initial badge.
//   · `channelEmbedUrl` prefers a RESOLVED video id. The legacy
//     `live_stream?channel=` endpoint is kept only as a last-resort fallback:
//     it is unreliable and renders "This video is unavailable" for many
//     channels that DO have a live broadcast. That was the original bug.
//
// Scope: financial / market / business / economic / geopolitical news only.
// Entertainment, sport, lifestyle, music and film are intentionally excluded.

export type LiveCategory =
  | 'financial'
  | 'business'
  | 'economics'
  | 'markets'
  | 'geopolitics'
  | 'breaking-news'
  | 'commodities'
  | 'technology'
  | 'pakistan'
  | 'china'
  | 'india'
  | 'us'
  | 'europe'
  | 'asia';

/** How a channel is embedded. */
export type LiveStreamType =
  /** Official YouTube live stream (resolved video id, else channel fallback). */
  | 'youtube'
  /** A direct, progressive media file (mp4/webm) played by <video>. */
  | 'video'
  /** An official embeddable page, loaded in an allowlisted iframe. */
  | 'embed';

/**
 * Last observed state. `live` was verified by actually resolving and playing the
 * stream; `offline` means the official channel had no live broadcast at check
 * time (it may return); `unverified` means it was never confirmed.
 */
export type VerificationStatus = 'live' | 'offline' | 'unverified';

export interface LiveChannel {
  /** Stable id — persisted in user selections. */
  id: string;
  name: string;
  description?: string;
  category: LiveCategory;
  /** Display region label ("US", "UK", "Global", …). */
  region?: string;
  type: LiveStreamType;
  /** YouTube channel id (UC…) — resolved from the network's own page. */
  youtubeChannelId?: string;
  /**
   * YouTube @handle. Preferred for live resolution: YouTube's
   * `/channel/<UC>/live` endpoint silently fails (no canonical video) for many
   * channels whose `/@handle/live` resolves correctly.
   */
  youtubeHandle?: string;
  /** YouTube video id (11 chars), when a channel exposes a fixed stream. */
  youtubeVideoId?: string;
  /** For `video`/`embed` types. */
  url?: string;
  sourceName?: string;
  sourceUrl?: string;
  /** Last observed status. The runtime resolver is authoritative. */
  lastKnownStatus: VerificationStatus;
  /** Whether this channel is on by default for a fresh install. */
  enabled: boolean;
}

/** Category display metadata + the order the picker groups them in. */
export const LIVE_CATEGORIES: { id: LiveCategory; label: string }[] = [
  { id: 'financial', label: 'Financial' },
  { id: 'business', label: 'Business' },
  { id: 'markets', label: 'Markets' },
  { id: 'breaking-news', label: 'Breaking News' },
  { id: 'geopolitics', label: 'Geopolitics' },
  { id: 'economics', label: 'Economics' },
  { id: 'commodities', label: 'Commodities & Energy' },
  { id: 'technology', label: 'Technology' },
  { id: 'us', label: 'US Markets' },
  { id: 'europe', label: 'Europe' },
  { id: 'asia', label: 'Asia' },
  { id: 'india', label: 'India' },
  { id: 'pakistan', label: 'Pakistan' },
  { id: 'china', label: 'China' },
];

export const LIVE_CATEGORY_LABEL: Record<LiveCategory, string> =
  Object.fromEntries(LIVE_CATEGORIES.map(c => [c.id, c.label])) as Record<LiveCategory, string>;

/**
 * Curated channels. Ids and handles were scraped from each network's own
 * YouTube page; `lastKnownStatus` records what a real playback test observed.
 */
export const LIVE_CHANNELS: LiveChannel[] = [
  // ── Financial ──
  { id: 'bloomberg-tv', name: 'Bloomberg Television', category: 'financial', region: 'US', type: 'youtube', youtubeChannelId: 'UCIALMKvObZNtJ6AmdCLP7Lg', youtubeHandle: '@markets', sourceName: 'Bloomberg', sourceUrl: 'https://www.youtube.com/@markets', lastKnownStatus: 'live', enabled: true },
  { id: 'cnbc-tv', name: 'CNBC Television', category: 'financial', region: 'US', type: 'youtube', youtubeChannelId: 'UCvJJ_dzjViJCoLf5uKUTwoA', youtubeHandle: '@CNBC', sourceName: 'CNBC', sourceUrl: 'https://www.youtube.com/@CNBC', lastKnownStatus: 'live', enabled: true },
  { id: 'yahoo-finance', name: 'Yahoo Finance', category: 'financial', region: 'US', type: 'youtube', youtubeChannelId: 'UCEAZeUIeJs0IjQiqTCdVSIg', youtubeHandle: '@YahooFinance', sourceName: 'Yahoo Finance', sourceUrl: 'https://www.youtube.com/@YahooFinance', lastKnownStatus: 'live', enabled: true },
  { id: 'moneycontrol', name: 'Moneycontrol', category: 'financial', region: 'India', type: 'youtube', youtubeChannelId: 'UChftTVI0QJmyXkajQYt2tiQ', youtubeHandle: '@moneycontrol', sourceName: 'Moneycontrol', sourceUrl: 'https://www.youtube.com/@moneycontrol', lastKnownStatus: 'live', enabled: true },
  { id: 'fox-business', name: 'Fox Business', category: 'business', region: 'US', type: 'youtube', youtubeChannelId: 'UCXIJgqnII2ZOINSWNOGFThA', youtubeHandle: '@FoxBusiness', sourceName: 'Fox Business', sourceUrl: 'https://www.youtube.com/@FoxBusiness', lastKnownStatus: 'offline', enabled: false },

  // ── Breaking / world news ──
  { id: 'sky-news', name: 'Sky News', category: 'breaking-news', region: 'UK', type: 'youtube', youtubeChannelId: 'UCkFclpi8U9VJjfxLYoms7Aw', youtubeHandle: '@SkyNews', sourceName: 'Sky News', sourceUrl: 'https://www.youtube.com/@SkyNews', lastKnownStatus: 'live', enabled: true },
  { id: 'al-jazeera-en', name: 'Al Jazeera English', category: 'breaking-news', region: 'Global', type: 'youtube', youtubeChannelId: 'UCNye-wNBqNL5ZzHSJj3l8Bg', youtubeHandle: '@aljazeeraenglish', sourceName: 'Al Jazeera', sourceUrl: 'https://www.youtube.com/@aljazeeraenglish', lastKnownStatus: 'live', enabled: true },
  { id: 'dw-news', name: 'DW News', category: 'breaking-news', region: 'Europe', type: 'youtube', youtubeChannelId: 'UCbbS1GE942k3UVqpLklyhIA', youtubeHandle: '@dwnews', sourceName: 'DW', sourceUrl: 'https://www.youtube.com/@dwnews', lastKnownStatus: 'live', enabled: true },
  { id: 'france24-en', name: 'France 24 English', category: 'breaking-news', region: 'Europe', type: 'youtube', youtubeChannelId: 'UCCCPCZNChQdGa9EkATeye4g', youtubeHandle: '@FRANCE24English', sourceName: 'France 24', sourceUrl: 'https://www.youtube.com/@FRANCE24English', lastKnownStatus: 'offline', enabled: false },
  { id: 'abc-news-au', name: 'ABC News (Australia)', category: 'breaking-news', region: 'APAC', type: 'youtube', youtubeChannelId: 'UCxcrzzhQDj5zKJbXfIscCtg', youtubeHandle: '@abcnewsaustralia', sourceName: 'ABC News', sourceUrl: 'https://www.youtube.com/@abcnewsaustralia', lastKnownStatus: 'live', enabled: false },
  { id: 'trt-world', name: 'TRT World', category: 'breaking-news', region: 'Türkiye', type: 'youtube', youtubeChannelId: 'UCnyCrv8b7bu0oWFXGyHaPzg', youtubeHandle: '@trtworld', sourceName: 'TRT World', sourceUrl: 'https://www.youtube.com/@trtworld', lastKnownStatus: 'offline', enabled: false },

  // ── Europe / Asia ──
  { id: 'euronews-en', name: 'Euronews English', category: 'europe', region: 'Europe', type: 'youtube', youtubeChannelId: 'UCSrZ3UV4jOidv8ppoVuvW9Q', youtubeHandle: '@euronews', sourceName: 'Euronews', sourceUrl: 'https://www.youtube.com/@euronews', lastKnownStatus: 'live', enabled: true },
  { id: 'nhk-world', name: 'NHK WORLD-JAPAN', category: 'asia', region: 'Japan', type: 'youtube', youtubeChannelId: 'UCSPEjw8F2nQDtmUKPFNF7_A', youtubeHandle: '@NHKWORLDJAPAN', sourceName: 'NHK', sourceUrl: 'https://www.youtube.com/@NHKWORLDJAPAN', lastKnownStatus: 'live', enabled: true },
  { id: 'cna', name: 'CNA', category: 'asia', region: 'Singapore', type: 'youtube', youtubeChannelId: 'UC83jt4dlz1Gjl58fzQrrKZg', youtubeHandle: '@channelnewsasia', sourceName: 'CNA', sourceUrl: 'https://www.youtube.com/@channelnewsasia', lastKnownStatus: 'live', enabled: true },

  // ── India ──
  { id: 'cnbc-tv18', name: 'CNBC-TV18', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCmRbHAgG2k2vDUvb3xsEunQ', youtubeHandle: '@CNBC-TV18', sourceName: 'CNBC-TV18', sourceUrl: 'https://www.youtube.com/@CNBC-TV18', lastKnownStatus: 'live', enabled: true },
  { id: 'et-now', name: 'ET Now', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCI_mwTKUhicNzFrhm33MzBQ', youtubeHandle: '@ETNow', sourceName: 'ET Now', sourceUrl: 'https://www.youtube.com/@ETNow', lastKnownStatus: 'live', enabled: true },
  { id: 'zee-business', name: 'Zee Business', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCkXopQ3ubd-rnXnStZqCl2w', youtubeHandle: '@ZeeBusiness', sourceName: 'Zee Business', sourceUrl: 'https://www.youtube.com/@ZeeBusiness', lastKnownStatus: 'live', enabled: false },
  { id: 'cnbc-awaaz', name: 'CNBC Awaaz', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCQIycDaLsBpMKjOCeaKUYVg', youtubeHandle: '@cnbcawaaz', sourceName: 'CNBC Awaaz', sourceUrl: 'https://www.youtube.com/@cnbcawaaz', lastKnownStatus: 'live', enabled: false },
  { id: 'india-today', name: 'India Today', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCYPvAwZP8pZhSMW8qs7cVCw', youtubeHandle: '@IndiaToday', sourceName: 'India Today', sourceUrl: 'https://www.youtube.com/@IndiaToday', lastKnownStatus: 'live', enabled: false },
  { id: 'wion', name: 'WION', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UC_gUM8rL-Lrg6O3adPW9K1g', youtubeHandle: '@WION', sourceName: 'WION', sourceUrl: 'https://www.youtube.com/@WION', lastKnownStatus: 'live', enabled: false },
  { id: 'ndtv-profit', name: 'NDTV Profit', category: 'india', region: 'India', type: 'youtube', youtubeChannelId: 'UCJEtD6JDgNKxcPJPBOAf-Tg', youtubeHandle: '@ndtvprofit', sourceName: 'NDTV Profit', sourceUrl: 'https://www.youtube.com/@ndtvprofit', lastKnownStatus: 'offline', enabled: false },

  // ── Pakistan ──
  { id: 'geo-news', name: 'Geo News', category: 'pakistan', region: 'Pakistan', type: 'youtube', youtubeChannelId: 'UCe9JSDmyqNgA_l2BzGHq1Ug', youtubeHandle: '@geonews', sourceName: 'Geo News', sourceUrl: 'https://www.youtube.com/@geonews', lastKnownStatus: 'live', enabled: true },
  { id: 'samaa-tv', name: 'Samaa TV', category: 'pakistan', region: 'Pakistan', type: 'youtube', youtubeChannelId: 'UCeBBZIOxTImZ_8sabWVQwBA', youtubeHandle: '@SamaaTV', sourceName: 'Samaa TV', sourceUrl: 'https://www.youtube.com/@SamaaTV', lastKnownStatus: 'live', enabled: true },
  { id: 'ptv-news', name: 'PTV News', category: 'pakistan', region: 'Pakistan', type: 'youtube', youtubeChannelId: 'UC5RvV_LtR1dxPCVFGw6dxXA', youtubeHandle: '@PTVNewsOfficial', sourceName: 'PTV News', sourceUrl: 'https://www.youtube.com/@PTVNewsOfficial', lastKnownStatus: 'live', enabled: false },
  { id: 'ary-news', name: 'ARY News', category: 'pakistan', region: 'Pakistan', type: 'youtube', youtubeChannelId: 'UCwQjXDfumjqAXnkqi2AtsNQ', youtubeHandle: '@ARYNews', sourceName: 'ARY News', sourceUrl: 'https://www.youtube.com/@ARYNews', lastKnownStatus: 'offline', enabled: false },
  { id: 'dunya-news', name: 'Dunya News', category: 'pakistan', region: 'Pakistan', type: 'youtube', youtubeChannelId: 'UCG7xCQTxgy93j6r49wl48rw', youtubeHandle: '@DunyaNews', sourceName: 'Dunya News', sourceUrl: 'https://www.youtube.com/@DunyaNews', lastKnownStatus: 'offline', enabled: false },
];

export function channelById(id: string): LiveChannel | undefined {
  return LIVE_CHANNELS.find(c => c.id === id);
}

/** Channel ids enabled for a fresh install. */
export function defaultChannelIds(): string[] {
  return LIVE_CHANNELS.filter(c => c.enabled).map(c => c.id);
}

/** Channels grouped by category, in LIVE_CATEGORIES order. Empty groups dropped. */
export function channelsByCategory(channels: LiveChannel[] = LIVE_CHANNELS) {
  return LIVE_CATEGORIES
    .map(cat => ({ category: cat, channels: channels.filter(c => c.category === cat.id) }))
    .filter(group => group.channels.length > 0);
}

// ── Embedding ────────────────────────────────────────────────────────────────

/** Privacy-preserving YouTube embed host (no tracking cookies before playback). */
export const YOUTUBE_EMBED_HOST = 'https://www.youtube-nocookie.com';

/** Hosts we will load in an iframe for a user-supplied custom source. */
export const EMBED_ALLOWLIST = [
  'www.youtube.com',
  'youtube.com',
  'www.youtube-nocookie.com',
  'youtube-nocookie.com',
  'player.vimeo.com',
  'player.twitch.tv',
];

const VIDEO_ID_RE = /^[\w-]{11}$/;
const CHANNEL_ID_RE = /^UC[\w-]{22}$/;

/**
 * Validate a URL for use in an iframe. Only https and only allowlisted hosts —
 * a user-supplied source must never be able to load arbitrary origins, and this
 * must never be able to become a proxy. Returns the normalised URL or null.
 */
export function safeEmbedUrl(raw: string): string | null {
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== 'https:') return null;
    if (!EMBED_ALLOWLIST.includes(url.hostname)) return null;
    return url.toString();
  } catch {
    return null;
  }
}

/**
 * Build the embed URL for a channel.
 *
 * PREFERRED: a `resolvedVideoId` from the server resolver →
 * `/embed/<id>` — this is the form that actually plays.
 *
 * FALLBACK: `live_stream?channel=<id|handle>` — unreliable (YouTube often renders
 * "This video is unavailable" inside the frame even when the channel is live),
 * so it is used only when no resolved id is available.
 */
export function channelEmbedUrl(
  channel: LiveChannel,
  opts: { muted: boolean; autoplay: boolean; resolvedVideoId?: string | null },
): string | null {
  if (channel.type === 'youtube') {
    const params = new URLSearchParams({
      autoplay: opts.autoplay ? '1' : '0',
      mute: opts.muted ? '1' : '0',
      playsinline: '1',
      rel: '0',
      modestbranding: '1',
    });
    const videoId = opts.resolvedVideoId ?? channel.youtubeVideoId ?? null;
    if (videoId && VIDEO_ID_RE.test(videoId)) {
      return `${YOUTUBE_EMBED_HOST}/embed/${videoId}?${params}`;
    }
    const target = channel.youtubeHandle ?? channel.youtubeChannelId;
    if (target) {
      return `${YOUTUBE_EMBED_HOST}/embed/live_stream?channel=${encodeURIComponent(target)}&${params}`;
    }
    return null;
  }
  if (channel.type === 'embed' && channel.url) return safeEmbedUrl(channel.url);
  return null;
}

/** Where a user can watch the channel at its source (escape hatch when an
 *  embed is blocked or offline). */
export function channelWatchUrl(channel: LiveChannel): string {
  if (channel.youtubeVideoId) return `https://www.youtube.com/watch?v=${channel.youtubeVideoId}`;
  if (channel.youtubeHandle) return `https://www.youtube.com/${channel.youtubeHandle}/live`;
  if (channel.youtubeChannelId) return `https://www.youtube.com/channel/${channel.youtubeChannelId}/live`;
  return channel.url ?? channel.sourceUrl ?? 'https://www.youtube.com';
}

export function channelTypeLabel(channel: LiveChannel): string {
  if (channel.type === 'youtube') return 'YouTube';
  if (channel.type === 'video') return 'Media';
  return 'Embed';
}

// ── Custom sources (advanced) ────────────────────────────────────────────────

export type CustomSource =
  | { kind: 'channel'; id: string }        // YouTube channel id or @handle
  | { kind: 'video'; id: string }          // YouTube video id
  | { kind: 'embed'; url: string };        // allowlisted embed URL

/**
 * Parse an advanced user-supplied source. Returns null when the input is not a
 * recognised, safe source — the caller then keeps the current channel instead of
 * rendering a broken frame.
 */
export function parseCustomSource(raw: string): CustomSource | null {
  const s = raw.trim();
  if (!s) return null;
  if (VIDEO_ID_RE.test(s)) return { kind: 'video', id: s };
  if (CHANNEL_ID_RE.test(s)) return { kind: 'channel', id: s };
  if (/^@[\w.-]+$/.test(s)) return { kind: 'channel', id: s };

  // Parse YouTube URLs STRUCTURALLY before the generic embed allowlist: a
  // youtube.com/@handle or /channel/… URL shares a host with the allowlist but
  // is NOT itself embeddable — YouTube refuses to frame a channel page.
  try {
    const url = new URL(s.startsWith('http') ? s : `https://${s}`);
    if (/(^|\.)youtube\.com$/.test(url.hostname) || /(^|\.)youtu\.be$/.test(url.hostname)) {
      const v = url.searchParams.get('v');
      if (v && VIDEO_ID_RE.test(v)) return { kind: 'video', id: v };
      if (/(^|\.)youtu\.be$/.test(url.hostname)) {
        const short = url.pathname.match(/^\/([\w-]{11})$/);
        if (short) return { kind: 'video', id: short[1] };
      }
      const ch = url.pathname.match(/\/channel\/(UC[\w-]{22})/);
      if (ch) return { kind: 'channel', id: ch[1] };
      const handle = url.pathname.match(/^\/@([\w.-]+)/);
      if (handle) return { kind: 'channel', id: `@${handle[1]}` };
      const embed = url.pathname.match(/\/embed\/([\w-]{11})/);
      if (embed) return { kind: 'video', id: embed[1] };
      return null;
    }
  } catch { /* not a URL — try the embed allowlist below */ }

  const asEmbed = safeEmbedUrl(s);
  if (asEmbed) return { kind: 'embed', url: asEmbed };
  return null;
}

/** Turn a parsed custom source into a playable ad-hoc channel. */
export function customSourceToChannel(source: CustomSource, label = 'Custom source'): LiveChannel {
  if (source.kind === 'video') {
    return { id: `custom:video:${source.id}`, name: label, category: 'financial', type: 'youtube', youtubeVideoId: source.id, lastKnownStatus: 'unverified', enabled: true };
  }
  if (source.kind === 'channel') {
    const isHandle = source.id.startsWith('@');
    return {
      id: `custom:channel:${source.id}`, name: label, category: 'financial', type: 'youtube',
      youtubeHandle: isHandle ? source.id : undefined,
      youtubeChannelId: isHandle ? undefined : source.id,
      lastKnownStatus: 'unverified', enabled: true,
    };
  }
  return { id: `custom:embed:${source.url}`, name: label, category: 'financial', type: 'embed', url: source.url, lastKnownStatus: 'unverified', enabled: true };
}
