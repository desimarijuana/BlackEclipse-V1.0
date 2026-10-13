// ── Internet image search: provider abstraction ─────────────────────────────
// Eclipse can search the real internet for images and render them inline. This
// module is the ONE image-search provider layer. It mirrors the connector
// architecture in `web-connectors.ts`: every provider is a small adapter that
// turns one image index into the normalized `ImageSearchResult` contract, and
// the chain is reached through the SSRF-hardened `safeGet` transport.
//
// Providers:
//   - Brave Images Search API  — the primary provider. Requires BRAVE_API_KEY.
//     A text-search key does NOT imply image search; this calls the dedicated
//     `/res/v1/images/search` endpoint.
//   - Openverse               — keyless, license-metadata-rich image index.
//   - Wikimedia Commons       — keyless, direct image URLs via `imageinfo`.
//
// Nothing is fabricated: an empty answer is `zero_results`; a failure is a named
// category. Credentials live only on the backend and never enter a response.
//
// Deterministic application code (not the model) turns these results into the
// rendered gallery. The model never invents an image URL.

import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import {
  failedDiagnostic,
  okDiagnostic,
  zeroResultDiagnostic,
  type RetrievalDiagnostic,
} from "@/lib/retrieval-diagnostics";

export const IMAGE_RESULT_SCHEMA_VERSION = "1.0";

const UA =
  "BlackEclipse/1.0 (open-source financial research; contact@blackeclipse.local)";
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 4 * 1024 * 1024;
const MAX_RETRIES = 2;
const CACHE_TTL_MS = 5 * 60_000;
const CACHE_MAX = 256;
const MAX_CONCURRENCY = 4;

export type ImageSearchType = "any" | "photo" | "illustration" | "diagram" | "chart";
export type SafeSearch = "off" | "moderate" | "strict";
export type ImageValidationStatus = "unvalidated" | "metadata_ok" | "verified" | "rejected";

/**
 * The normalized, versioned image result contract shared between the backend
 * tool and the frontend renderer. Optional values are null (never a fabricated
 * placeholder). `sourceUrl` and `attribution` preserve provenance.
 */
export interface ImageSearchResult {
  id: string;
  imageUrl: string;
  thumbnailUrl: string | null;
  sourceUrl: string | null;
  title: string;
  altText: string | null;
  sourceDomain: string;
  width: number | null;
  height: number | null;
  mimeType: string | null;
  provider: string;
  retrievedAt: string;
  attribution: string | null;
  validationStatus: ImageValidationStatus;
}

export interface ImageSearchOptions {
  count?: number;
  imageType?: ImageSearchType;
  safeSearch?: SafeSearch;
  language?: string;
  region?: string;
  freshness?: string;
}

export interface ImageSearchOutcome {
  results: ImageSearchResult[];
  diagnostics: RetrievalDiagnostic[];
  provider: string | null;
}

export interface ImageProviderAvailability {
  name: string;
  requiresCredentials: boolean;
  available: boolean;
  note?: string;
}

// ── Provider contract ───────────────────────────────────────────────────────

export interface ImageSearchProvider {
  readonly name: string;
  readonly requiresCredentials: boolean;
  available(): Promise<boolean>;
  searchImages(query: string, options: Required<Pick<ImageSearchOptions, "count" | "safeSearch">> & ImageSearchOptions): Promise<ImageSearchResult[]>;
}

function clampCount(n: unknown): number {
  const v = typeof n === "number" && Number.isFinite(n) ? Math.floor(n) : 8;
  return Math.min(Math.max(v, 1), 25);
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== "string" || !value.trim()) return false;
  const check = validateOutboundUrl(value.trim());
  return check.safe;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

/**
 * Build one normalized result. Returns null when the candidate has no usable
 * direct image URL — a source page alone is NOT an image and is never presented
 * as one.
 */
function toResult(
  provider: string,
  raw: {
    imageUrl?: unknown;
    thumbnailUrl?: unknown;
    sourceUrl?: unknown;
    title?: unknown;
    altText?: unknown;
    width?: unknown;
    height?: unknown;
    mimeType?: unknown;
    attribution?: unknown;
  },
): ImageSearchResult | null {
  if (!isHttpUrl(raw.imageUrl)) return null;
  const imageUrl = (raw.imageUrl as string).trim();
  const thumbnail = isHttpUrl(raw.thumbnailUrl) ? (raw.thumbnailUrl as string).trim() : null;
  const sourceUrl = isHttpUrl(raw.sourceUrl) ? (raw.sourceUrl as string).trim() : null;
  const sourceDomain = domainOf(imageUrl) || (sourceUrl ? domainOf(sourceUrl) : "");
  const width = typeof raw.width === "number" && Number.isFinite(raw.width) && raw.width > 0 ? Math.round(raw.width) : null;
  const height = typeof raw.height === "number" && Number.isFinite(raw.height) && raw.height > 0 ? Math.round(raw.height) : null;
  const title = typeof raw.title === "string" && raw.title.trim() ? raw.title.trim().slice(0, 300) : sourceDomain || "Image";
  const alt = typeof raw.altText === "string" && raw.altText.trim() ? raw.altText.trim().slice(0, 500) : null;
  const mime = typeof raw.mimeType === "string" && raw.mimeType.trim() ? raw.mimeType.trim().toLowerCase() : null;
  const attribution = typeof raw.attribution === "string" && raw.attribution.trim() ? raw.attribution.trim().slice(0, 500) : null;
  return {
    id: "",
    imageUrl,
    thumbnailUrl: thumbnail,
    sourceUrl,
    title,
    altText: alt,
    sourceDomain,
    width,
    height,
    mimeType: mime,
    provider,
    retrievedAt: nowIso(),
    attribution,
    // URL safety already checked here; network/format validation is a separate,
    // explicit step (validate_image_result) so search never blocks on probing.
    validationStatus: "metadata_ok",
  };
}

function withIds(provider: string, results: ImageSearchResult[]): ImageSearchResult[] {
  return results.map((r, i) => ({ ...r, id: `${provider}:${i + 1}:${hash(r.imageUrl)}` }));
}

function hash(input: string): string {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36);
}

// ── Transport with bounded retries + jittered backoff ───────────────────────

class ImageProviderError extends Error {
  code: string;
  retryable: boolean;
  constructor(code: string, message: string, retryable: boolean) {
    super(message);
    this.code = code;
    this.retryable = retryable;
  }
}

async function getJson(url: string, headers: Record<string, string>): Promise<unknown> {
  const check = validateOutboundUrl(url);
  if (!check.safe) throw new ImageProviderError("blocked", `URL rejected: ${check.reason ?? "unsafe"}`, false);

  let lastErr: unknown;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const res = await safeGet({
        url,
        timeoutMs: TIMEOUT_MS,
        maxBytes: MAX_BYTES,
        headers: { "user-agent": UA, accept: "application/json", ...headers },
      });
      if (res.status === 429 || res.status >= 500) {
        throw new ImageProviderError(
          res.status === 429 ? "rate_limited" : "http_error",
          `provider returned HTTP ${res.status}`,
          true,
        );
      }
      if (res.status < 200 || res.status >= 300) {
        throw new ImageProviderError("http_error", `provider returned HTTP ${res.status}`, false);
      }
      return JSON.parse(res.text) as unknown;
    } catch (err) {
      lastErr = err;
      const retryable = err instanceof ImageProviderError ? err.retryable : true;
      if (!retryable || attempt === MAX_RETRIES) break;
      const backoff = Math.min(250 * 2 ** attempt, 2000) + Math.random() * 200;
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  if (lastErr instanceof ImageProviderError) throw lastErr;
  const code = lastErr instanceof OutboundError ? lastErr.code : "transport_error";
  const timedOut = code === "timeout";
  throw new ImageProviderError(
    code === "blocked_host" || code === "blocked_protocol" ? "blocked" : timedOut ? "timeout" : "transport_error",
    timedOut ? `provider timed out after ${TIMEOUT_MS} ms` : "provider request failed",
    false,
  );
}

// ── Brave Images Search API (primary, credential-required) ───────────────────

class BraveImageProvider implements ImageSearchProvider {
  readonly name = "brave-images";
  readonly requiresCredentials = true;

  async available(): Promise<boolean> {
    return Boolean(await resolveProviderKey("BRAVE_API_KEY"));
  }

  async searchImages(query: string, options: { count: number; safeSearch: SafeSearch; language?: string }): Promise<ImageSearchResult[]> {
    const key = await resolveProviderKey("BRAVE_API_KEY");
    if (!key) throw new ImageProviderError("not_configured", "BRAVE_API_KEY is not configured", false);
    const params = new URLSearchParams({
      q: query,
      count: String(Math.min(options.count, 20)),
      safesearch: options.safeSearch === "off" ? "off" : options.safeSearch === "strict" ? "strict" : "moderate",
      country: "us",
    });
    if (options.language) params.set("search_lang", options.language);
    const url = `https://api.search.brave.com/res/v1/images/search?${params.toString()}`;
    const payload = (await getJson(url, { "x-subscription-token": key })) as {
      results?: Array<Record<string, unknown>>;
    };
    const rows = Array.isArray(payload?.results) ? payload.results : [];
    const out: ImageSearchResult[] = [];
    for (const row of rows) {
      const thumbnail = row.thumbnail as Record<string, unknown> | undefined;
      const properties = row.properties as Record<string, unknown> | undefined;
      const built = toResult(this.name, {
        imageUrl: properties?.url ?? thumbnail?.src,
        thumbnailUrl: thumbnail?.src,
        sourceUrl: row.url,
        title: row.title,
        altText: row.title,
      });
      if (built) out.push(built);
      if (out.length >= options.count) break;
    }
    return withIds(this.name, out);
  }
}

// ── Openverse (keyless) ──────────────────────────────────────────────────────

class OpenverseImageProvider implements ImageSearchProvider {
  readonly name = "openverse";
  readonly requiresCredentials = false;

  async available(): Promise<boolean> {
    return true;
  }

  async searchImages(query: string, options: { count: number }): Promise<ImageSearchResult[]> {
    const params = new URLSearchParams({ q: query, page_size: String(Math.min(options.count, 20)) });
    const url = `https://api.openverse.org/v1/images/?${params.toString()}`;
    const payload = (await getJson(url, {})) as { results?: Array<Record<string, unknown>> };
    const rows = Array.isArray(payload?.results) ? payload.results : [];
    const out: ImageSearchResult[] = [];
    for (const row of rows) {
      const license = [row.license, row.license_version].filter(Boolean).join(" ");
      const creator = typeof row.creator === "string" ? row.creator : "";
      const built = toResult(this.name, {
        imageUrl: row.url,
        thumbnailUrl: row.thumbnail,
        sourceUrl: row.foreign_landing_url,
        title: row.title,
        altText: row.title,
        width: row.width,
        height: row.height,
        mimeType: row.filetype ? `image/${String(row.filetype).toLowerCase()}` : null,
        attribution: [creator && `by ${creator}`, license && `(${license})`, "Openverse"].filter(Boolean).join(" "),
      });
      if (built) out.push(built);
      if (out.length >= options.count) break;
    }
    return withIds(this.name, out);
  }
}

// ── Wikimedia Commons (keyless, direct image URLs) ───────────────────────────

class CommonsImageProvider implements ImageSearchProvider {
  readonly name = "wikimedia-commons";
  readonly requiresCredentials = false;

  async available(): Promise<boolean> {
    return true;
  }

  async searchImages(query: string, options: { count: number }): Promise<ImageSearchResult[]> {
    const max = Math.min(options.count, 25);
    const searchUrl =
      `https://commons.wikimedia.org/w/api.php?action=query&list=search&format=json&srnamespace=6` +
      `&srlimit=${max}&srsearch=${encodeURIComponent(`filetype:bitmap ${query}`)}`;
    const found = (await getJson(searchUrl, {})) as { query?: { search?: Array<Record<string, unknown>> } };
    const titles = (found?.query?.search ?? [])
      .map((r) => String(r.title ?? ""))
      .filter((t) => t.startsWith("File:"))
      .slice(0, max);
    if (titles.length === 0) return [];
    const infoUrl =
      `https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo` +
      `&iiprop=url|size|mime|extmetadata&iiurlwidth=480&titles=${encodeURIComponent(titles.join("|"))}`;
    const info = (await getJson(infoUrl, {})) as { query?: { pages?: Record<string, Record<string, unknown>> } };
    const pages = info?.query?.pages ?? {};
    const out: ImageSearchResult[] = [];
    for (const page of Object.values(pages)) {
      const imageinfo = Array.isArray(page.imageinfo) ? (page.imageinfo[0] as Record<string, unknown>) : undefined;
      if (!imageinfo) continue;
      const meta = (imageinfo.extmetadata ?? {}) as Record<string, { value?: unknown }>;
      const artist = typeof meta.Artist?.value === "string" ? stripHtml(meta.Artist.value) : "";
      const license = typeof meta.LicenseShortName?.value === "string" ? String(meta.LicenseShortName.value) : "";
      const built = toResult(this.name, {
        imageUrl: imageinfo.url,
        thumbnailUrl: imageinfo.thumburl,
        sourceUrl: imageinfo.descriptionurl,
        title: String(page.title ?? "").replace(/^File:/, "").replace(/\.[a-z0-9]+$/i, ""),
        altText: String(page.title ?? "").replace(/^File:/, ""),
        width: imageinfo.width,
        height: imageinfo.height,
        mimeType: imageinfo.mime,
        attribution: [artist && `by ${stripHtml(artist)}`, license, "Wikimedia Commons"].filter(Boolean).join(" "),
      });
      if (built) out.push(built);
      if (out.length >= options.count) break;
    }
    return withIds(this.name, out);
  }
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

// ── Registry, chain and cache ────────────────────────────────────────────────

function base(provider: string): Pick<RetrievalDiagnostic, "capability" | "provider" | "tier"> {
  return { capability: "web_search", provider, tier: "secondary" };
}

export function imageProviders(): ImageSearchProvider[] {
  return [new BraveImageProvider(), new OpenverseImageProvider(), new CommonsImageProvider()];
}

export async function imageProviderHealth(): Promise<ImageProviderAvailability[]> {
  const out: ImageProviderAvailability[] = [];
  for (const provider of imageProviders()) {
    let available = false;
    try {
      available = await provider.available();
    } catch {
      available = false;
    }
    out.push({
      name: provider.name,
      requiresCredentials: provider.requiresCredentials,
      available,
      note: provider.requiresCredentials && !available ? "BRAVE_API_KEY is not configured" : undefined,
    });
  }
  return out;
}

interface CacheEntry {
  expires: number;
  value: ImageSearchOutcome;
}
const CACHE = new Map<string, CacheEntry>();
const INFLIGHT = new Map<string, Promise<ImageSearchOutcome>>();
const SEMAPHORE: { active: number; queue: Array<() => void> } = { active: 0, queue: [] };

function cacheKey(query: string, opts: ImageSearchOptions): string {
  const norm = query.trim().toLowerCase().replace(/\s+/g, " ");
  return `${IMAGE_RESULT_SCHEMA_VERSION}|${norm}|${opts.count ?? 8}|${opts.imageType ?? "any"}|${opts.safeSearch ?? "moderate"}|${opts.language ?? ""}|${opts.region ?? ""}`;
}

async function withSemaphore<T>(fn: () => Promise<T>): Promise<T> {
  if (SEMAPHORE.active >= MAX_CONCURRENCY) {
    await new Promise<void>((resolve) => SEMAPHORE.queue.push(resolve));
  }
  SEMAPHORE.active++;
  try {
    return await fn();
  } finally {
    SEMAPHORE.active--;
    const next = SEMAPHORE.queue.shift();
    if (next) next();
  }
}

function dedupe(results: ImageSearchResult[]): ImageSearchResult[] {
  const seen = new Set<string>();
  const out: ImageSearchResult[] = [];
  for (const r of results) {
    const key = r.imageUrl.replace(/^https?:\/\//, "").replace(/\/$/, "").toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(r);
  }
  return out;
}

function pruneCache(): void {
  const now = Date.now();
  for (const [key, entry] of CACHE) {
    if (entry.expires <= now) CACHE.delete(key);
  }
  while (CACHE.size > CACHE_MAX) {
    const oldest = CACHE.keys().next().value;
    if (oldest === undefined) break;
    CACHE.delete(oldest);
  }
}

/**
 * Search the internet for images. Runs the provider chain (Brave → Openverse →
 * Commons), normalizes, deduplicates, and caches. An identical in-flight search
 * is coalesced. Never fabricates: a genuine miss is `zero_results`.
 */
export async function searchImages(query: string, options: ImageSearchOptions = {}): Promise<ImageSearchOutcome> {
  const trimmed = query.trim();
  if (!trimmed) {
    return {
      results: [],
      provider: null,
      diagnostics: [failedDiagnostic(base("image_search"), "invalid_request", "query is required")],
    };
  }
  const count = clampCount(options.count);
  const safeSearch: SafeSearch = options.safeSearch ?? "moderate";
  const normalized: ImageSearchOptions = { ...options, count, safeSearch };

  pruneCache();
  const key = cacheKey(trimmed, normalized);
  const cached = CACHE.get(key);
  if (cached && cached.expires > Date.now()) {
    return {
      ...cached.value,
      diagnostics: [
        ...cached.value.diagnostics,
        okDiagnostic(base(cached.value.provider ?? "image-cache"), {
          category: "ok",
          detail: "served from the in-process image-search cache",
        }),
      ],
    };
  }
  const inflight = INFLIGHT.get(key);
  if (inflight) return inflight;

  const promise = withSemaphore(async () => {
    const diagnostics: RetrievalDiagnostic[] = [];
    let anyAvailable = false;
    for (const provider of imageProviders()) {
      let available = false;
      try {
        available = await provider.available();
      } catch {
        available = false;
      }
      if (!available) {
        diagnostics.push(
          failedDiagnostic(base(provider.name), "not_configured", `${provider.name} is not configured`, { retryable: false }),
        );
        continue;
      }
      anyAvailable = true;
      const started = Date.now();
      try {
        const results = await provider.searchImages(trimmed, { ...normalized, count, safeSearch });
        const latencyMs = Date.now() - started;
        if (results.length > 0) {
          diagnostics.push(okDiagnostic(base(provider.name), { latencyMs, resultCount: results.length }));
          const outcome: ImageSearchOutcome = { results: dedupe(results), provider: provider.name, diagnostics };
          CACHE.set(key, { expires: Date.now() + CACHE_TTL_MS, value: outcome });
          return outcome;
        }
        diagnostics.push(zeroResultDiagnostic(base(provider.name), `${provider.name} returned no image matches`, { latencyMs }));
      } catch (err) {
        const latencyMs = Date.now() - started;
        const code = err instanceof ImageProviderError ? err.code : "transport_error";
        const category: RetrievalDiagnostic["category"] =
          code === "rate_limited"
            ? "http_error"
            : code === "timeout"
              ? "timeout"
              : code === "blocked"
                ? "blocked"
                : code === "not_configured"
                  ? "not_configured"
                  : "transport_error";
        diagnostics.push(
          failedDiagnostic(base(provider.name), category, err instanceof Error ? err.message : `${provider.name} failed`, {
            latencyMs,
            ...(code === "rate_limited" ? { httpStatus: 429, retryable: true } : {}),
          }),
        );
      }
    }
    const allUnavailable = diagnostics.every((d) => d.category === "not_configured");
    const outcome: ImageSearchOutcome = {
      results: [],
      provider: null,
      diagnostics:
        diagnostics.length > 0
          ? diagnostics
          : [failedDiagnostic(base("image_search"), "not_configured", "no image provider is configured", { retryable: false })],
    };
    if (anyAvailable && !allUnavailable) CACHE.set(key, { expires: Date.now() + 60_000, value: outcome });
    return outcome;
  });

  INFLIGHT.set(key, promise);
  try {
    return await promise;
  } finally {
    INFLIGHT.delete(key);
  }
}

/** Test/diagnostic hook: clear the in-process search cache. */
export function clearImageSearchCache(): void {
  CACHE.clear();
}
