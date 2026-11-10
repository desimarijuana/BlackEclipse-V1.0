// ── Web search providers (independent, configurable) ────────────────────────
// Search is not one hard-wired DuckDuckGo call. Each provider is a small,
// isolated adapter behind a common interface so it can be disabled or replaced
// independently. The FIRST configured provider wins; the keyless DuckDuckGo HTML
// provider is the always-present default, and an operator may add ANY JSON search
// API through the settings vault (URL + key + field mapping) without code changes.
//
// Every attempt returns a `RetrievalDiagnostic` that distinguishes a genuine
// zero-result answer from a block, a timeout, an HTTP error and a parse failure.
// Nothing is fabricated: a provider that cannot answer returns no results and a
// failure diagnostic, never a guessed result.

import * as cheerio from "cheerio";
import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import {
  failedDiagnostic,
  okDiagnostic,
  zeroResultDiagnostic,
  type RetrievalDiagnostic,
} from "@/lib/retrieval-diagnostics";

export interface WebSearchResult {
  title: string;
  url: string;
  snippet: string;
  publishedAt?: string | null;
  /** A direct open-access PDF when the provider discloses one. */
  pdfUrl?: string | null;
  /** True when the provider marks the work as open access. */
  isOpenAccess?: boolean;
  /** Reference pointers disclosed by the provider (title + DOI). */
  references?: Array<{ title: string; doi?: string | null }>;
}

export interface SearchAttempt {
  provider: string;
  tier: "primary" | "official" | "secondary" | "unknown";
  results: WebSearchResult[];
  diagnostic: RetrievalDiagnostic;
}

export interface SearchProvider {
  readonly id: string;
  readonly tier: "primary" | "official" | "secondary" | "unknown";
  /** True when this provider can attempt a search (e.g. has a base URL/key). */
  configured(): Promise<boolean> | boolean;
  /** Search. Never throws; a failure is a diagnostic + empty results. */
  search(query: string, limit: number): Promise<SearchAttempt>;
}

// The declared bot identity (matches `OUTBOUND_USER_AGENT` in web-research.ts).
// Verified to work for DuckDuckGo HTML and — unlike a spoofed browser UA — for
// SEC / regulator / company-IR hosts (which require an email-shaped contact).
const UA = "BlackEclipse/1.0 (open-source financial research; contact@blackeclipse.local)";

// ── Keyless HTML search providers (the zero-config fallback chain) ──────────
// A single keyless endpoint is a single point of failure: DuckDuckGo's HTML
// endpoint now frequently answers with HTTP 202 / an anti-bot page. So the
// keyless default is a CHAIN of independent HTML endpoints, tried in order by
// the transport until one returns results. Each is a plain, declared-identity
// GET to a fixed https host — no key, no configuration. A block is diagnosed as
// `blocked`, never confused with `zero_results`.

const KEYLESS_SEARCH_TIMEOUT_MS = 10_000;

/** Anti-bot / challenge detection shared by every keyless HTML provider. */
function looksBlocked(html: string, status: number): boolean {
  if (status === 202 || status === 429) return true;
  return /anomaly|unusual traffic|are you a robot|not a robot|enable javascript and cookies|verify you are human|captcha|access denied|too many requests/i.test(
    html
  );
}

/**
 * Shared machinery for a keyless HTML endpoint: fixed timeout, declared UA,
 * block/zero-result distinction. Subclasses supply the endpoint and the parser.
 */
abstract class KeylessHtmlSearchProvider implements SearchProvider {
  readonly tier = "secondary" as const;
  abstract readonly id: string;

  protected abstract endpoint(query: string): string;
  protected abstract parse(html: string, limit: number): WebSearchResult[];

  configured(): boolean {
    return true;
  }

  async search(query: string, limit: number): Promise<SearchAttempt> {
    const base = { capability: "web_search" as const, provider: this.id, tier: this.tier };
    const q = (query ?? "").trim();
    if (!q) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "invalid_request", "query is required"),
      };
    }
    const started = Date.now();
    let res: Response;
    try {
      res = await fetch(this.endpoint(q), {
        headers: { "User-Agent": UA },
        signal: AbortSignal.timeout(KEYLESS_SEARCH_TIMEOUT_MS),
      });
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      const timedOut = name === "TimeoutError" || name === "AbortError";
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(
          base,
          timedOut ? "timeout" : "transport_error",
          timedOut
            ? `search request timed out after ${KEYLESS_SEARCH_TIMEOUT_MS} ms`
            : "search request failed",
          { latencyMs: Date.now() - started, timedOut }
        ),
      };
    }

    const latencyMs = Date.now() - started;
    const httpStatus = res.status;
    let html: string;
    try {
      html = await res.text();
    } catch {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "transport_error", "search response could not be read", {
          latencyMs,
          httpStatus,
        }),
      };
    }
    const bytes = html.length;

    // A non-2xx status is an HTTP error, not "no results".
    if (httpStatus < 200 || httpStatus >= 300) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "http_error", `search provider returned HTTP ${httpStatus}`, {
          latencyMs,
          httpStatus,
          bytes,
        }),
      };
    }

    const results = this.parse(html, limit);
    if (results.length === 0) {
      // A challenge/anti-bot page is a BLOCK, not an empty result set — the
      // caller must be able to tell these apart.
      const blocked = looksBlocked(html, httpStatus);
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: blocked
          ? failedDiagnostic(
              base,
              "blocked",
              `the keyless search provider challenged the request (HTTP ${httpStatus}); ` +
                "no results were served. Configure a search provider in Settings for reliable coverage " +
                "(a key from Tavily, Brave, Exa, Serper or SerpApi, a Bing key, or a self-hosted SearXNG).",
              { latencyMs, httpStatus, bytes, parseOutcome: "empty", retryable: false }
            )
          : zeroResultDiagnostic(base, "the search provider answered but returned no matches", {
              latencyMs,
              httpStatus,
              bytes,
            }),
      };
    }

    return {
      provider: this.id,
      tier: this.tier,
      results,
      diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, resultCount: results.length }),
    };
  }
}

/** DuckDuckGo HTML — the original keyless default. */
export class DuckDuckGoHtmlProvider extends KeylessHtmlSearchProvider {
  readonly id = "duckduckgo-html";

  protected endpoint(query: string): string {
    return `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  }

  protected parse(html: string, limit: number): WebSearchResult[] {
    const $ = cheerio.load(html);
    const out: WebSearchResult[] = [];
    $("a.result__a").each((_i, el) => {
      if (out.length >= limit) return;
      const href = $(el).attr("href") || "";
      const title = $(el).text().replace(/\s+/g, " ").trim();
      const snippet = $(el).closest(".result").find(".result__snippet").text().replace(/\s+/g, " ").trim();
      const url = unwrapDuckDuckGo(href);
      if (!url || !title) return;
      out.push({ title, url, snippet, publishedAt: null });
    });
    return out;
  }
}

/** DuckDuckGo Lite — a second, simpler HTML surface of the same engine. */
export class DuckDuckGoLiteProvider extends KeylessHtmlSearchProvider {
  readonly id = "duckduckgo-lite";

  protected endpoint(query: string): string {
    return `https://lite.duckduckgo.com/lite/?q=${encodeURIComponent(query)}`;
  }

  protected parse(html: string, limit: number): WebSearchResult[] {
    const $ = cheerio.load(html);
    const out: WebSearchResult[] = [];
    $("a.result-link").each((_i, el) => {
      if (out.length >= limit) return;
      const href = $(el).attr("href") || "";
      const title = $(el).text().replace(/\s+/g, " ").trim();
      const snippet = $(el)
        .closest("tr")
        .next("tr")
        .find(".result-snippet")
        .text()
        .replace(/\s+/g, " ")
        .trim();
      const url = unwrapDuckDuckGo(href);
      if (!url || !title || !/^https?:/i.test(url)) return;
      out.push({ title, url, snippet, publishedAt: null });
    });
    return out;
  }
}

/** Recover the real URL from Bing's `bing.com/ck/a` click tracker. */
export function unwrapBing(href: string): string {
  if (!href) return "";
  try {
    const u = new URL(href, "https://www.bing.com");
    if (!/(^|\.)bing\.com$/i.test(u.hostname)) return href;
    const encoded = u.searchParams.get("u");
    if (!encoded) return href;
    let s = encoded.startsWith("a1") ? encoded.slice(2) : encoded;
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    const pad = s.length % 4 ? "=".repeat(4 - (s.length % 4)) : "";
    const decoded = Buffer.from(s + pad, "base64").toString("utf8");
    return /^https?:\/\//i.test(decoded) ? decoded : href;
  } catch {
    return href;
  }
}

/** Bing — keyless HTML results from a distinct index. */
export class BingHtmlProvider extends KeylessHtmlSearchProvider {
  readonly id = "bing-html";

  protected endpoint(query: string): string {
    return `https://www.bing.com/search?q=${encodeURIComponent(query)}&count=20`;
  }

  protected parse(html: string, limit: number): WebSearchResult[] {
    const $ = cheerio.load(html);
    const out: WebSearchResult[] = [];
    $("li.b_algo").each((_i, el) => {
      if (out.length >= limit) return;
      const anchor = $(el).find("h2 a").first();
      const href = anchor.attr("href") || "";
      const title = anchor.text().replace(/\s+/g, " ").trim();
      const snippet = $(el)
        .find(".b_caption p, .b_lineclamp2, p")
        .first()
        .text()
        .replace(/\s+/g, " ")
        .trim();
      const url = unwrapBing(href);
      if (!url || !title || !/^https?:\/\//i.test(url)) return;
      out.push({ title, url, snippet, publishedAt: null });
    });
    return out;
  }
}

/** Mojeek — an independent keyless index (no DuckDuckGo/Bing upstream). */
export class MojeekProvider extends KeylessHtmlSearchProvider {
  readonly id = "mojeek";

  protected endpoint(query: string): string {
    return `https://www.mojeek.com/search?q=${encodeURIComponent(query)}`;
  }

  protected parse(html: string, limit: number): WebSearchResult[] {
    const $ = cheerio.load(html);
    const out: WebSearchResult[] = [];
    $("ul.results-standard > li").each((_i, el) => {
      if (out.length >= limit) return;
      const anchor = $(el).find("a.title, h2 a").first();
      const href = anchor.attr("href") || "";
      const title = anchor.text().replace(/\s+/g, " ").trim();
      const snippet = $(el).find("p.s, .s").first().text().replace(/\s+/g, " ").trim();
      if (!href || !title) return;
      const url = href.startsWith("http") ? href : `https://www.mojeek.com${href}`;
      out.push({ title, url, snippet, publishedAt: null });
    });
    return out;
  }
}

/** DuckDuckGo wraps outbound links in a redirect; recover the real URL. */
export function unwrapDuckDuckGo(href: string): string {
  if (!href) return "";
  if (href.startsWith("//")) href = `https:${href}`;
  try {
    const parsed = new URL(href);
    const target = parsed.searchParams.get("uddg");
    if (target) return decodeURIComponent(target);
    return href;
  } catch {
    return "";
  }
}

// ── Operator-configured JSON search API ─────────────────────────────────────

export interface CustomSearchConfig {
  /** Base endpoint. `{query}` and `{limit}` placeholders are substituted. */
  url: string;
  /** Secret value; sent per `auth`. Null for keyless endpoints. */
  apiKey: string | null;
  /**
   * How the key is presented:
   *   query  → append as a query parameter (default param name `key`)
   *   bearer → `Authorization: Bearer <key>`
   *   header → a named header (default `x-api-key`)
   */
  authKind: "query" | "bearer" | "header";
  authParam: string;
  /** Dot path to the results array, e.g. `web.results` or `results`. */
  resultsPath: string;
  /** Dot path within a result to each field. */
  titlePath: string;
  urlPath: string;
  snippetPath: string;
}

const CUSTOM_SEARCH_TIMEOUT_MS = 12_000;

/**
 * Ready-made search-provider presets. The operator picks a name and supplies a
 * key; the correct endpoint + response shape (the `CustomSearchConfig` fields) are
 * filled in here so nobody hand-writes JSON. Each maps one real API's response
 * envelope into the normalised `title/url/snippet`. The key is read from the
 * settings vault (`SEARCH_API_KEY`); nothing here hard-codes a credential.
 */
export interface SearchProviderPreset {
  id: string;
  name: string;
  /** Where to get a key (operator-facing, shown in Settings). */
  keyUrl: string;
  /**
   * The env var / vault key that holds THIS provider's credential. Each named
   * provider has its own key so a user can add one in Settings without editing
   * `SEARCH_API_CONFIG` JSON; `resolveNamedSearchProvider` auto-selects the first
   * preset whose key is configured. `searxng` is keyless and instead needs a base
   * URL (a public value).
   */
  keyEnv: string;
  /** True when the stored value is not secret (a base URL, e.g. SearXNG). */
  publicValue?: boolean;
  config: Omit<CustomSearchConfig, "apiKey">;
}

export const SEARCH_PROVIDER_PRESETS: SearchProviderPreset[] = [
  {
    id: "tavily",
    name: "Tavily",
    keyUrl: "https://tavily.com",
    keyEnv: "TAVILY_API_KEY",
    config: {
      url: "https://api.tavily.com/search?query={query}&max_results={limit}",
      authKind: "query",
      authParam: "api_key",
      resultsPath: "results",
      titlePath: "title",
      urlPath: "url",
      snippetPath: "content",
    },
  },
  {
    id: "brave",
    name: "Brave Search",
    keyUrl: "https://brave.com/search/api/",
    keyEnv: "BRAVE_API_KEY",
    config: {
      url: "https://api.search.brave.com/res/v1/web/search?q={query}&count={limit}",
      authKind: "header",
      authParam: "X-Subscription-Token",
      resultsPath: "web.results",
      titlePath: "title",
      urlPath: "url",
      snippetPath: "description",
    },
  },
  {
    id: "exa",
    name: "Exa",
    keyUrl: "https://exa.ai",
    keyEnv: "EXA_API_KEY",
    config: {
      url: "https://api.exa.ai/search?query={query}&numResults={limit}",
      authKind: "header",
      authParam: "x-api-key",
      resultsPath: "results",
      titlePath: "title",
      urlPath: "url",
      snippetPath: "text",
    },
  },
  {
    id: "serper",
    name: "Serper (Google)",
    keyUrl: "https://serper.dev",
    keyEnv: "SERPER_API_KEY",
    config: {
      url: "https://google.serper.dev/search?q={query}&num={limit}",
      authKind: "header",
      authParam: "X-API-KEY",
      resultsPath: "organic",
      titlePath: "title",
      urlPath: "link",
      snippetPath: "snippet",
    },
  },
  {
    id: "serpapi",
    name: "SerpApi (multi-engine)",
    keyUrl: "https://serpapi.com",
    keyEnv: "SERPAPI_API_KEY",
    config: {
      url: "https://serpapi.com/search.json?q={query}&num={limit}&engine=google",
      authKind: "query",
      authParam: "api_key",
      resultsPath: "organic_results",
      titlePath: "title",
      urlPath: "link",
      snippetPath: "snippet",
    },
  },
  {
    id: "bing",
    name: "Bing Web Search (Azure)",
    keyUrl: "https://www.microsoft.com/en-us/bing/apis/bing-web-search-api",
    keyEnv: "BING_SEARCH_API_KEY",
    config: {
      url: "https://api.bing.microsoft.com/v7.0/search?q={query}&count={limit}",
      authKind: "header",
      authParam: "Ocp-Apim-Subscription-Key",
      resultsPath: "webPages.value",
      titlePath: "name",
      urlPath: "url",
      snippetPath: "snippet",
    },
  },
  {
    id: "google-cse",
    name: "Google Custom Search JSON API",
    keyUrl: "https://developers.google.com/custom-search/v1/overview",
    keyEnv: "GOOGLE_CSE_API_KEY",
    config: {
      // The engine id (`cx`) is supplied as an override together with the key;
      // the API key is the query credential.
      url: "https://www.googleapis.com/customsearch/v1?q={query}&num={limit}",
      authKind: "query",
      authParam: "key",
      resultsPath: "items",
      titlePath: "title",
      urlPath: "link",
      snippetPath: "snippet",
    },
  },
  {
    id: "searxng",
    name: "SearXNG (self-hosted, keyless)",
    keyUrl: "https://docs.searxng.org",
    keyEnv: "SEARXNG_URL",
    publicValue: true,
    config: {
      url: "{url}/search?q={query}&format=json",
      authKind: "query",
      authParam: "key",
      resultsPath: "results",
      titlePath: "title",
      urlPath: "url",
      snippetPath: "content",
    },
  },
];

export function searchProviderPreset(id: string): SearchProviderPreset | null {
  return SEARCH_PROVIDER_PRESETS.find((p) => p.id === id) ?? null;
}

/**
 * Build a `CustomJsonSearchProvider` for a named preset, substituting its
 * credential and (for SearXNG) its self-hosted base URL. Used when a user adds a
 * provider key directly in Settings — no `SEARCH_API_CONFIG` JSON required.
 */
export function buildPresetSearchProvider(
  preset: SearchProviderPreset,
  value: string | null
): CustomJsonSearchProvider | null {
  if (!value || !value.trim()) return null;
  let config = preset.config;
  if (preset.id === "searxng") {
    // SearXNG is keyless: the stored value is the base URL. Fill `{url}`.
    const base = value.trim().replace(/\/+$/, "");
    config = { ...config, url: config.url.replace("{url}", base) };
    return new CustomJsonSearchProvider({ ...config, apiKey: null });
  }
  return new CustomJsonSearchProvider({ ...config, apiKey: value.trim() });
}

/**
 * The first named provider whose key/URL is configured, in catalogue order.
 * `lookup` returns the stored value for an env var (or null). The custom
 * `SEARCH_API_CONFIG` JSON, when present, still wins at the caller — this is the
 * no-JSON path a user gets by adding one provider key in Settings.
 */
export function firstConfiguredPreset(
  lookup: (envVar: string) => string | null
): { preset: SearchProviderPreset; value: string } | null {
  for (const preset of SEARCH_PROVIDER_PRESETS) {
    const value = lookup(preset.keyEnv);
    if (value && value.trim()) return { preset, value };
  }
  return null;
}

/**
 * Resolve the operator's `SEARCH_API_CONFIG` into a full config.
 *
 * Two accepted shapes, so an operator can add a provider WITHOUT hand-writing
 * JSON:
 *   - a preset name, e.g. `"tavily"`, or `{"preset":"tavily"}` — the endpoint and
 *     field paths come from `SEARCH_PROVIDER_PRESETS`;
 *   - a full `{"url":…,"resultsPath":…}` object (any JSON search API).
 *
 * Returns the merged config (minus the key) or null when the value is neither a
 * known preset nor a usable object. Never invents a URL.
 */
export function resolveSearchApiConfig(raw: unknown): Omit<CustomSearchConfig, "apiKey"> | null {
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    const text = raw.trim();
    if (!text) return null;
    try {
      parsed = JSON.parse(text);
    } catch {
      // A bare string is treated as a preset name (e.g. "tavily").
      parsed = { preset: text };
    }
  }
  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;

  // A preset name (optionally with an overridden url, e.g. a self-hosted SearXNG
  // base) fills every field; explicit fields in the object still win.
  if (typeof obj.preset === "string") {
    const preset = searchProviderPreset(obj.preset);
    if (!preset) return null;
    const merged = { ...preset.config, ...cleanOverrides(obj) };
    return merged.url ? merged : null;
  }
  if (typeof obj.url === "string" && obj.url.trim()) {
    return {
      url: obj.url.trim(),
      authKind: (obj.authKind as CustomSearchConfig["authKind"]) ?? "query",
      authParam: typeof obj.authParam === "string" ? obj.authParam : "key",
      resultsPath: typeof obj.resultsPath === "string" ? obj.resultsPath : "results",
      titlePath: typeof obj.titlePath === "string" ? obj.titlePath : "title",
      urlPath: typeof obj.urlPath === "string" ? obj.urlPath : "url",
      snippetPath: typeof obj.snippetPath === "string" ? obj.snippetPath : "snippet",
    };
  }
  return null;
}

/** String fields from a raw object (ignores the `preset` marker itself). */
function cleanOverrides(obj: Record<string, unknown>): Partial<Omit<CustomSearchConfig, "apiKey">> {
  const out: Record<string, string> = {};
  for (const key of ["url", "authKind", "authParam", "resultsPath", "titlePath", "urlPath", "snippetPath"]) {
    const value = obj[key];
    if (typeof value === "string" && value.trim()) out[key] = value.trim();
  }
  return out as Partial<Omit<CustomSearchConfig, "apiKey">>;
}

function getPath(root: unknown, path: string): unknown {
  if (!path) return undefined;
  let current: unknown = root;
  for (const segment of path.split(".")) {
    if (current == null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

/**
 * A generic, configurable search provider. The operator supplies only a URL, a
 * key and JSON field paths; the adapter makes no assumption about the vendor.
 * Credentials come from the existing settings vault — never hard-coded.
 */
export class CustomJsonSearchProvider implements SearchProvider {
  readonly id = "custom-search";
  readonly tier = "secondary" as const;

  constructor(private readonly config: CustomSearchConfig) {}

  configured(): boolean {
    return Boolean(this.config.url && this.config.url.trim());
  }

  async search(query: string, limit: number): Promise<SearchAttempt> {
    const base = { capability: "web_search" as const, provider: this.id, tier: this.tier };
    const q = query.trim();
    if (!q || !this.configured()) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(
          base,
          this.configured() ? "invalid_request" : "not_configured",
          this.configured() ? "query is required" : "no search API URL is configured"
        ),
      };
    }

    const expanded = this.withQueryAuth(
      this.config.url
        .replace(/\{query\}/g, encodeURIComponent(q))
        .replace(/\{limit\}/g, String(limit))
    );
    const check = validateOutboundUrl(expanded);
    if (!check.safe) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "blocked", `search URL rejected: ${check.reason ?? "unsafe"}`, {
          retryable: false,
        }),
      };
    }

    const started = Date.now();
    let res;
    try {
      res = await safeGet({
        url: expanded,
        timeoutMs: CUSTOM_SEARCH_TIMEOUT_MS,
        maxBytes: 2 * 1024 * 1024,
        headers: { "user-agent": UA, ...this.authHeaders() },
      });
    } catch (err) {
      const code = err instanceof OutboundError ? err.code : "";
      const timedOut = code === "timeout";
      const category = timedOut
        ? "timeout"
        : code === "blocked_host" || code === "blocked_protocol"
          ? "blocked"
          : "transport_error";
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(
          base,
          category,
          timedOut ? `search request timed out after ${CUSTOM_SEARCH_TIMEOUT_MS} ms` : "search request failed",
          { latencyMs: Date.now() - started, timedOut }
        ),
      };
    }

    const latencyMs = Date.now() - started;
    const bytes = res.bytes;
    if (res.status < 200 || res.status >= 300) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "http_error", `search API returned HTTP ${res.status}`, {
          latencyMs,
          httpStatus: res.status,
          bytes,
        }),
      };
    }

    let payload: unknown;
    try {
      payload = JSON.parse(res.text);
    } catch {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "parse_failure", "search API response was not valid JSON", {
          latencyMs,
          httpStatus: res.status,
          bytes,
          parseOutcome: "failed",
        }),
      };
    }

    const rows = getPath(payload, this.config.resultsPath);
    if (!Array.isArray(rows)) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(
          base,
          "parse_failure",
          `no results array found at "${this.config.resultsPath}"`,
          { latencyMs, httpStatus: res.status, bytes, parseOutcome: "failed" }
        ),
      };
    }

    const results: WebSearchResult[] = [];
    for (const row of rows) {
      if (results.length >= limit) break;
      const url = String(getPath(row, this.config.urlPath) ?? "").trim();
      const title = String(getPath(row, this.config.titlePath) ?? "").trim();
      if (!url || !title) continue;
      const snippet = String(getPath(row, this.config.snippetPath) ?? "").trim();
      results.push({ title, url, snippet, publishedAt: null });
    }

    if (results.length === 0) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: zeroResultDiagnostic(base, "the search API answered but returned no usable results", {
          latencyMs,
          httpStatus: res.status,
          bytes,
        }),
      };
    }

    return {
      provider: this.id,
      tier: this.tier,
      results,
      diagnostic: okDiagnostic(base, {
        latencyMs,
        httpStatus: res.status,
        bytes,
        resultCount: results.length,
      }),
    };
  }

  private authHeaders(): Record<string, string> {
    const { apiKey, authKind, authParam } = this.config;
    if (!apiKey) return {};
    if (authKind === "bearer") return { authorization: `Bearer ${apiKey}` };
    if (authKind === "header") return { [authParam || "x-api-key"]: apiKey };
    return {}; // query auth is appended to the URL by the caller
  }

  /** The URL with a query-auth key appended, when configured that way. */
  withQueryAuth(url: string): string {
    if (this.config.authKind !== "query" || !this.config.apiKey) return url;
    const u = new URL(url);
    u.searchParams.set(this.config.authParam || "key", this.config.apiKey);
    return u.toString();
  }
}

export { OutboundError };

// ── Provider registry ───────────────────────────────────────────────────────

/**
 * The ordered, independent search providers to try. The operator-configured
 * provider is tried first when configured so a working paid/keyed API is
 * preferred over the scrape-prone defaults. The keyless default is a CHAIN of
 * independent HTML endpoints — one keyless engine being blocked no longer blanks
 * the search.
 */
export interface SearchProviderSet {
  providers: SearchProvider[];
}

/** The keyless fallback chain, in preference order (best-parsed first). */
export function keylessSearchProviders(): SearchProvider[] {
  return [
    new DuckDuckGoHtmlProvider(),
    new DuckDuckGoLiteProvider(),
    new MojeekProvider(),
    new BingHtmlProvider(),
  ];
}

export async function resolveSearchProviders(
  custom: SearchProvider | null
): Promise<SearchProvider[]> {
  const { getSourcePreferenceMap } = await import("@/lib/data-source-preferences");
  const prefs = await getSourcePreferenceMap();
  const allowed = (id: string): boolean => {
    switch (id) {
      case "duckduckgo-html":
      case "duckduckgo-lite":
      case "mojeek":
      case "bing-html":
        return prefs.duckduckgo !== false;
      case "tavily":
      case "brave":
      case "exa":
      case "serper":
        return prefs[id] !== false;
      default:
        return true;
    }
  };

  const list: SearchProvider[] = [];
  if (custom && (await Promise.resolve(custom.configured())) && allowed(custom.id)) {
    list.push(custom);
  }
  list.push(...keylessSearchProviders().filter((p) => allowed(p.id)));
  return list;
}
