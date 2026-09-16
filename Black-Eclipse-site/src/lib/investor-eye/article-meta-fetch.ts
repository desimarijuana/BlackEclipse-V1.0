// ── Investor Eye — article metadata fetch (network + cache) ──────────────────
// The network half of headline recovery: fetch an article's HTML through the
// shared `safeGet` transport and extract its metadata.
//
// Why on-demand rather than at ingestion: assembly already takes ~15s, and
// fetching hundreds of publisher pages inside it would make it minutes. The
// dossier requests one event's metadata when it opens, and the result is cached
// permanently, so any given URL is fetched at most once, ever.
//
// Caching is `SystemConfig` JSON (the repo's convention for operator data) in
// bounded LRU-ish buckets — no schema change, no new store.
//
// Honest by construction: paywalls, bot walls, non-HTML responses and timeouts
// all resolve to `null`, and the UI keeps saying "no headline available".
// Nothing is ever synthesized.

import { safeGet, OutboundError, validateOutboundUrl } from '@/lib/connectors/security';
import { getConfigJSON, setConfigJSON } from '@/lib/settings';
import { extractArticleMeta, isUninformativeTitle, stripSiteSuffix, type ArticleMeta } from './article-meta';
import { articleKey } from './enrich';

/** Cached resolution for an article URL. `meta: null` = "tried, nothing usable". */
interface CacheEntry {
  meta: ArticleMeta | null;
  at: string;
  /** The URL actually fetched (after choosing among an event's sources). */
  fetchedUrl: string;
}

const CACHE_KEY = 'investor-eye:article-meta';
/** Bounded so the JSON blob cannot grow without limit. */
const MAX_CACHE_ENTRIES = 800;
const BUCKETS = 8;

/**
 * A publisher page is a few hundred KB. 512 KB is enough for the <head> plus
 * some body (needed for the <h1> fallback) while staying well inside the
 * transport's cap and keeping the read fast.
 */
const MAX_HTML_BYTES = 512 * 1024;
const FETCH_TIMEOUT_MS = 7_000;
/** Give up on a whole event after this many source attempts. */
const MAX_ATTEMPTS_PER_EVENT = 3;

type Cache = Record<string, CacheEntry>;

/** Stable bucket for a cache key, so writers to other buckets don't clobber. */
function bucketOf(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return h % BUCKETS;
}

/** Read every bucket and merge. 8 small reads; negligible against a fetch. */
async function readCache(key: string): Promise<CacheEntry | null> {
  const b = bucketOf(key);
  try {
    const part = await getConfigJSON<Cache>(`${CACHE_KEY}:${b}`, {});
    return part[key] ?? null;
  } catch {
    return null;
  }
}

/** Trim the cache to the newest N entries (keyed by `at`). */
function prune(cache: Cache): Cache {
  const entries = Object.entries(cache);
  if (entries.length <= MAX_CACHE_ENTRIES) return cache;
  entries.sort((a, b) => Date.parse(b[1].at) - Date.parse(a[1].at));
  return Object.fromEntries(entries.slice(0, MAX_CACHE_ENTRIES));
}

/**
 * Persist new entries into their buckets. Only the touched buckets are read,
 * merged and written, so a concurrent writer in another bucket is not lost.
 */
async function saveCache(newEntries: Cache): Promise<void> {
  if (Object.keys(newEntries).length === 0) return;
  const byBucket = new Map<number, Cache>();
  for (const [k, v] of Object.entries(newEntries)) {
    const b = bucketOf(k);
    const arr = byBucket.get(b) ?? {};
    arr[k] = v;
    byBucket.set(b, arr);
  }
  try {
    for (const [b, entries] of byBucket) {
      const existing = await getConfigJSON<Cache>(`${CACHE_KEY}:${b}`, {});
      await setConfigJSON(`${CACHE_KEY}:${b}`, prune({ ...existing, ...entries }));
    }
  } catch (err) {
    // Caching is best-effort; a failure only costs a refetch.
    console.warn('[investor-eye] article-meta cache write skipped:', err instanceof Error ? err.message : err);
  }
}

/**
 * Fetch and extract metadata for one article URL.
 * Returns null for anything unusable — never throws.
 */
export async function fetchArticleMeta(url: string): Promise<ArticleMeta | null> {
  const urlCheck = validateOutboundUrl(url);
  if (!urlCheck.safe) return null;

  try {
    const res = await safeGet({
      url,
      timeoutMs: FETCH_TIMEOUT_MS,
      maxBytes: MAX_HTML_BYTES,
      headers: {
        // Some publishers 403 an unknown agent; identify honestly.
        'user-agent': 'Mozilla/5.0 (compatible; BlackEclipse/1.0; +https://github.com/)',
        accept: 'text/html,application/xhtml+xml',
      },
    });
    if (res.status < 200 || res.status >= 300) return null;
    const type = (res.contentType ?? '').toLowerCase();
    // A PDF/image/JSON "article" has no metadata to read.
    if (type && !type.includes('html') && !type.includes('xml')) return null;

    const meta = extractArticleMeta(res.text);
    if (!meta) return null;
    if (isUninformativeTitle(meta.title, meta.siteName)) return null;

    return { ...meta, title: stripSiteSuffix(meta.title, meta.siteName) };
  } catch (err) {
    // Blocked host, timeout, size cap — all simply mean "no metadata".
    if (!(err instanceof OutboundError)) {
      console.warn('[investor-eye] article fetch failed:', url.slice(0, 80), err instanceof Error ? err.message : err);
    }
    return null;
  }
}

/**
 * Resolve metadata for an event, trying its sources in order until one yields
 * something. Cached per URL, so repeat opens are instant.
 *
 * `urls` should be the event's source URLs, best-first (GDELT puts the primary
 * article first).
 */
export async function resolveEventArticleMeta(
  urls: Array<string | undefined>,
): Promise<{ meta: ArticleMeta | null; url: string | null; cached: boolean }> {
  const candidates: Array<{ url: string; key: string }> = [];
  const seen = new Set<string>();
  for (const u of urls) {
    const key = articleKey(u);
    if (!u || !key || seen.has(key)) continue;
    seen.add(key);
    candidates.push({ url: u, key });
  }
  const usable = candidates.slice(0, MAX_ATTEMPTS_PER_EVENT);
  if (usable.length === 0) return { meta: null, url: null, cached: false };

  // 1. Cache hits first (cheap, and avoids any network).
  for (const c of usable) {
    const hit = await readCache(c.key);
    if (hit) {
      return hit.meta
        ? { meta: hit.meta, url: hit.fetchedUrl, cached: true }
        : { meta: null, url: null, cached: true };
    }
  }

  // 2. Fetch the first candidate that yields metadata.
  const fresh: Cache = {};
  for (const c of usable) {
    const meta = await fetchArticleMeta(c.url);
    fresh[c.key] = { meta, at: new Date().toISOString(), fetchedUrl: c.url };
    if (meta) {
      await saveCache(fresh);
      return { meta, url: c.url, cached: false };
    }
  }

  // Nothing usable — remember that, so we don't retry on every open.
  await saveCache(fresh);
  return { meta: null, url: null, cached: false };
}

/** Test seam / diagnostics. */
export const ARTICLE_META_CACHE_KEY = CACHE_KEY;
