// ── Live Intelligence — server-side live-stream resolver ─────────────────────
// Resolves a YouTube channel's CURRENT live video id and embeddability from
// YouTube's own channel page, server-side, and caches the result.
//
// WHY THIS EXISTS (the bug it fixes): embedding
// `youtube-nocookie.com/embed/live_stream?channel=<UC>` is unreliable — YouTube
// serves "This video is unavailable" inside the frame for many channels that DO
// have a live broadcast. Embedding `/embed/<resolved-video-id>` plays correctly.
// Live video ids rotate, so they cannot be hardcoded in the registry.
//
// HONESTY: we only report `live` when YouTube's own page provides a canonical
// live video AND reports isLive=true AND playableInEmbed!=false. Everything else
// is `offline` (no live broadcast right now) or `unavailable` (cannot embed) —
// never a fabricated "LIVE".
//
// NO PROXYING: this reads a public page's metadata; it does not fetch, relay or
// rebroadcast any media.

export type StreamStatus = 'live' | 'offline' | 'unavailable' | 'unknown';

export interface ResolvedStream {
  /** The current live/embeddable YouTube video id, when there is one. */
  videoId: string | null;
  status: StreamStatus;
  /** Why, for diagnostics (developer view only). */
  reason?: string;
  /** When this result was produced (ISO). */
  checkedAt: string;
  /** True when served from cache rather than a fresh fetch. */
  cached: boolean;
}

/** YouTube's page metadata carries these; we never guess. */
const CANONICAL_LIVE = /<link rel="canonical" href="https:\/\/www\.youtube\.com\/watch\?v=([\w-]{11})"/;
const IS_LIVE = /"isLive":true/;
const EMBED_OK = /"playableInEmbed":true/;
const EMBED_NO = /"playableInEmbed":false/;

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

/** Parse the resolver's HTTP response body. Pure — unit tested. */
export function parseChannelLivePage(html: string): { videoId: string | null; status: StreamStatus; reason?: string } {
  const canonical = CANONICAL_LIVE.exec(html);
  const videoId = canonical ? canonical[1] : null;
  const isLive = IS_LIVE.test(html);
  const embedOk = EMBED_OK.test(html);
  const embedNo = EMBED_NO.test(html);

  if (!videoId || !isLive) {
    return { videoId: null, status: 'offline', reason: 'no live broadcast' };
  }
  if (embedNo && !embedOk) {
    return { videoId, status: 'unavailable', reason: 'not embeddable' };
  }
  return { videoId, status: 'live' };
}

const CACHE_TTL_MS = 3 * 60 * 1000;

interface CacheEntry { t: number; value: ResolvedStream }
interface CacheState {
  cache: Map<string, CacheEntry>;
  inflight: Map<string, Promise<ResolvedStream>>;
}

// Anchored on globalThis (like lib/db.ts and investor-eye/cache.ts): Next.js
// evaluates each route handler in its own module instance, so a plain module
// `let` would give every route a separate cache and stampede YouTube.
const g = globalThis as unknown as { liveResolveCache?: CacheState };
const state: CacheState = g.liveResolveCache ?? { cache: new Map(), inflight: new Map() };
g.liveResolveCache = state;

/**
 * Resolve using YouTube's `/@handle/live` endpoint, falling back to
 * `/channel/<UC>/live`.
 *
 * WHY HANDLE FIRST: YouTube's `/channel/<UC>/live` page silently fails to expose
 * a canonical live video for many channels whose `/@handle/live` resolves
 * correctly (verified against Sky News, DW News, ABC AU, Geo News, Samaa TV).
 * Trying the handle first is what makes the resolver actually work.
 */
async function fetchChannelLive(target: { handle?: string; channelId?: string }): Promise<ResolvedStream> {
  const checkedAt = new Date().toISOString();
  const urls: string[] = [];
  if (target.handle) urls.push(`https://www.youtube.com/${target.handle}/live`);
  if (target.channelId) urls.push(`https://www.youtube.com/channel/${encodeURIComponent(target.channelId)}/live`);

  let lastReason = 'not resolved';
  for (const url of urls) {
    try {
      const res = await fetch(url, {
        headers: { 'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9' },
        redirect: 'follow',
        signal: AbortSignal.timeout(12_000),
      });
      if (!res.ok) { lastReason = `http ${res.status}`; continue; }
      const html = await res.text();
      // A live page redirects to the watch URL; trust that as an extra signal.
      const redirectedId = /watch\?v=([\w-]{11})/.exec(res.url)?.[1] ?? null;
      const parsed = parseChannelLivePage(html);
      const videoId = parsed.videoId ?? (parsed.status === 'live' ? redirectedId : null);
      if (parsed.status === 'live' && videoId) {
        return { videoId, status: 'live', checkedAt, cached: false };
      }
      // Remember an explicit offline verdict; keep trying other forms.
      lastReason = parsed.reason ?? lastReason;
    } catch (err) {
      lastReason = String((err as Error)?.message || err).slice(0, 120);
    }
  }
  // No form produced a live video: report honestly rather than guessing.
  const status: StreamStatus = /http \d{3}/.test(lastReason) ? 'unknown' : 'offline';
  return { videoId: null, status, reason: lastReason, checkedAt, cached: false };
}

/**
 * Resolve a channel's live stream, served from a 3-minute cache when fresh.
 * Concurrent callers share one in-flight fetch (no stampede).
 */
export async function resolveLiveStream(
  target: { handle?: string; channelId?: string } | string,
): Promise<ResolvedStream> {
  const key = typeof target === 'string' ? `uc:${target}` : `h:${target.handle ?? ''}|c:${target.channelId ?? ''}`;
  const hit = state.cache.get(key);
  if (hit && Date.now() - hit.t < CACHE_TTL_MS) {
    return { ...hit.value, cached: true };
  }
  const running = state.inflight.get(key);
  if (running) return running;

  const spec = typeof target === 'string' ? { channelId: target } : target;
  const promise = fetchChannelLive(spec)
    .then((value) => {
      state.cache.set(key, { t: Date.now(), value });
      return value;
    })
    .finally(() => { state.inflight.delete(key); });

  state.inflight.set(key, promise);
  return promise;
}

/** Resolve many channels concurrently, keyed by a caller-supplied id. */
export async function resolveLiveStreams(
  targets: { key: string; handle?: string; channelId?: string }[],
): Promise<Record<string, ResolvedStream>> {
  const settled = await Promise.all(
    targets.map(async (t) => [t.key, await resolveLiveStream(t)] as const),
  );
  return Object.fromEntries(settled);
}

/** Test seam. */
export function clearResolverCache(): void {
  state.cache.clear();
  state.inflight.clear();
}
