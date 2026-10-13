// ── Inline image gallery view model ─────────────────────────────────────────
// Pure coercion of the two shapes an image gallery can arrive in:
//   1. A response `gallery` block (validated by the response contract).
//   2. The runtime's collected `images` run blob (validated in Python).
// Both are untrusted until coerced here. Only http(s) image URLs survive — a
// `javascript:`/`data:` URL can never reach an `<img src>`.

export interface GalleryItem {
  id: string;
  imageUrl: string;
  thumbnailUrl: string | null;
  sourceUrl: string | null;
  title: string;
  alt: string;
  sourceDomain: string;
  width: number | null;
  height: number | null;
  attribution: string | null;
}

export interface GalleryView {
  items: GalleryItem[];
  count: number;
  failures: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  try {
    const protocol = new URL(value.trim()).protocol;
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
  }
}

function str(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function dim(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.round(value) : null;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return '';
  }
}

/** Coerce ONE raw candidate into a `GalleryItem`, or null when unusable. */
export function coerceGalleryItem(raw: unknown, index: number): GalleryItem | null {
  if (!isRecord(raw)) return null;
  const imageUrl = raw.imageUrl ?? raw.url ?? raw.src;
  if (!isHttpUrl(imageUrl)) return null;
  const thumbnail = isHttpUrl(raw.thumbnailUrl) ? (raw.thumbnailUrl as string).trim() : null;
  const sourceUrlCandidate = raw.sourceUrl ?? raw.sourcePage ?? raw.landingUrl;
  const sourceUrl = isHttpUrl(sourceUrlCandidate) ? (sourceUrlCandidate as string).trim() : null;
  const sourceDomain =
    str(raw.sourceDomain) ?? str(raw.domain) ?? domainOf(sourceUrl ?? (imageUrl as string));
  const title = str(raw.title) ?? sourceDomain ?? 'Image';
  const alt = str(raw.alt) ?? str(raw.altText) ?? title;
  return {
    id: str(raw.id) ?? `img-${index}`,
    imageUrl: (imageUrl as string).trim(),
    thumbnailUrl: thumbnail,
    sourceUrl,
    title,
    alt,
    sourceDomain,
    width: dim(raw.width),
    height: dim(raw.height),
    attribution: str(raw.attribution) ?? null,
  };
}

/** Coerce a list of raw candidates, de-duplicating by image URL. */
export function coerceGalleryImages(raw: unknown): GalleryItem[] {
  if (!Array.isArray(raw)) return [];
  const out: GalleryItem[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < raw.length; i++) {
    const item = coerceGalleryItem(raw[i], i);
    if (!item) continue;
    const key = item.imageUrl.toLowerCase().replace(/\/$/, '');
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
    if (out.length >= 24) break;
  }
  return out;
}

/**
 * Coerce the runtime `images` run blob (`ImageCollector.to_blob()`) into a
 * view. Returns an empty view for an absent/odd blob so nothing is rendered.
 */
export function coerceGalleryBlob(blob: unknown): GalleryView {
  if (!isRecord(blob)) return { items: [], count: 0, failures: [] };
  const items = coerceGalleryImages(blob.results);
  const failures = Array.isArray(blob.failures)
    ? blob.failures
        .map((f) => (isRecord(f) ? str(f.reason) ?? 'rejected' : undefined))
        .filter((f): f is string => Boolean(f))
    : [];
  return { items, count: items.length, failures };
}
