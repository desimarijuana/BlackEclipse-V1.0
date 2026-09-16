// ── Investor Eye — article metadata extraction ───────────────────────────────
// GDELT publishes no headline, only the article URL, so 54% of the feed has no
// story text. The news-corpus join (enrich.ts) recovers ~1% because the RSS
// corpus and GDELT's article set barely overlap. The only real fix is to read
// the article's own metadata.
//
// This module is the PURE half: given HTML, extract a title and description.
// The network half lives in `article-meta-fetch.ts`, so parsing is unit-testable
// without a socket.
//
// Extraction order matters: Open Graph is what publishers set for syndication
// and is the most reliable, then Twitter's card, then the document <title>,
// then the first usable <h1>. Everything is decoded and whitespace-collapsed.
//
// We never INVENT text: if none of those are present the result is null and the
// UI keeps saying "no headline available".

export interface ArticleMeta {
  title: string;
  description?: string;
  /** Which signal produced the title — shown in the UI so provenance is clear. */
  titleSource: 'og:title' | 'twitter:title' | '<title>' | '<h1>';
  siteName?: string;
}

const HTML_ENTITIES: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
  mdash: '—', ndash: '–', hellip: '…', rsquo: '’', lsquo: '‘',
  rdquo: '”', ldquo: '“', middot: '·', bull: '•', deg: '°',
  eacute: 'é', egrave: 'è', agrave: 'à', ccedil: 'ç', uuml: 'ü',
  ouml: 'ö', auml: 'ä', ntilde: 'ñ', pound: '£', euro: '€', yen: '¥',
};

/** Decode the HTML entities that actually appear in headlines. */
export function decodeEntities(input: string): string {
  return input
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&([a-z]+);/gi, (m, name: string) => HTML_ENTITIES[name.toLowerCase()] ?? m);
}

function clean(input: string | undefined | null): string | undefined {
  if (!input) return undefined;
  const s = decodeEntities(input)
    .replace(/<[^>]*>/g, '')       // strip any inline markup
    .replace(/\s+/g, ' ')
    .trim();
  return s.length > 0 ? s : undefined;
}

/** Read a `<meta>` content value by property/name, tolerant of attribute order. */
function metaContent(html: string, key: string): string | undefined {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // property/name first, content second — and the reverse order.
  const patterns = [
    new RegExp(`<meta[^>]+(?:property|name)=["']${escaped}["'][^>]*content=["']([^"']*)["']`, 'i'),
    new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*(?:property|name)=["']${escaped}["']`, 'i'),
  ];
  for (const re of patterns) {
    const m = html.match(re);
    const v = clean(m?.[1]);
    if (v) return v;
  }
  return undefined;
}

/**
 * Extract article metadata from raw HTML. Returns null when there is no usable
 * title — the caller treats that as "no headline available".
 */
export function extractArticleMeta(html: string): ArticleMeta | null {
  if (!html || typeof html !== 'string') return null;

  // Only look inside <head> for meta, so a body quote mentioning "og:title"
  // can't masquerade as metadata.
  const headEnd = html.search(/<\/head>/i);
  const head = headEnd > 0 ? html.slice(0, headEnd) : html.slice(0, 20000);

  const ogTitle = metaContent(head, 'og:title');
  const twTitle = metaContent(head, 'twitter:title');
  const docTitle = clean((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) ?? [])[1]);
  const h1 = clean((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) ?? [])[1]);

  const title = ogTitle ?? twTitle ?? docTitle ?? h1;
  if (!title) return null;

  const titleSource: ArticleMeta['titleSource'] =
    ogTitle ? 'og:title' : twTitle ? 'twitter:title' : docTitle ? '<title>' : '<h1>';

  const description =
    metaContent(head, 'og:description') ??
    metaContent(head, 'twitter:description') ??
    metaContent(head, 'description');

  const siteName = metaContent(head, 'og:site_name');

  return {
    title,
    ...(description ? { description } : {}),
    titleSource,
    ...(siteName ? { siteName } : {}),
  };
}

/**
 * Is this title just the site's own name or a login/consent wall? Publishers
 * serve those for paywalled or bot-blocked pages, and showing them as the
 * event's headline would be worse than showing nothing.
 */
export function isUninformativeTitle(title: string, siteName?: string): boolean {
  const t = title.toLowerCase().trim();
  if (t.length < 12) return true;
  const noise = [
    'access denied', 'just a moment', 'attention required', 'are you a robot',
    'enable javascript', 'verify you are human', '403 forbidden', '404 not found',
    'page not found', 'subscribe to continue', 'sign in', 'log in', 'cookie',
    'privacy policy', 'terms of service', 'content unavailable',
  ];
  if (noise.some((n) => t.includes(n))) return true;
  if (siteName && t === siteName.toLowerCase().trim()) return true;
  return false;
}

/**
 * Strip a trailing " - Site Name" / " | Site Name" suffix common on <title>.
 *
 * Only strips when the suffix is non-empty and the stripped result is still a
 * meaningful title, so we never turn "Reuters" into "" or eat a real headline
 * that merely contains a dash.
 */
export function stripSiteSuffix(title: string, siteName?: string): string {
  const trimmed = title.trim();
  if (!siteName) return trimmed;
  const escaped = siteName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`\\s*[\\-|–—]\\s*${escaped}\\s*$`, 'i');
  const out = trimmed.replace(re, '').trim();
  // Require the remainder to still look like a title, not a fragment.
  return out.length >= 8 ? out : trimmed;
}
