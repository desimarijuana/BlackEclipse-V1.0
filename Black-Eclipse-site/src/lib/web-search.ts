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

// ── DuckDuckGo HTML (keyless default) ───────────────────────────────────────

const DDG_SEARCH_TIMEOUT_MS = 10_000;

/**
 * The keyless fallback. DuckDuckGo's HTML endpoint now frequently answers with
 * HTTP 202 and an anti-bot page; previously that parsed to zero results and was
 * reported identically to "no results". It is now diagnosed explicitly so the
 * caller knows the transport was blocked, not that the web was empty.
 */
export class DuckDuckGoHtmlProvider implements SearchProvider {
  readonly id = "duckduckgo-html";
  readonly tier = "secondary" as const;

  configured(): boolean {
    return true;
  }

  async search(query: string, limit: number): Promise<SearchAttempt> {
    const base = { capability: "web_search" as const, provider: this.id, tier: this.tier };
    const q = query.trim();
    if (!q) {
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: failedDiagnostic(base, "invalid_request", "query is required"),
      };
    }
    const started = Date.now();
    let res;
    try {
      res = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}`, {
        headers: { "User-Agent": UA },
        signal: AbortSignal.timeout(DDG_SEARCH_TIMEOUT_MS),
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
          timedOut ? `search request timed out after ${DDG_SEARCH_TIMEOUT_MS} ms` : "search request failed",
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
      // HTTP 202 is DuckDuckGo's anti-bot/challenge response. It is a BLOCK, not
      // an empty result set — the caller must be able to tell these apart.
      const blocked = httpStatus === 202 || /anomaly|unusual traffic|are you a robot/i.test(html);
      return {
        provider: this.id,
        tier: this.tier,
        results: [],
        diagnostic: blocked
          ? failedDiagnostic(
              base,
              "blocked",
              `search provider challenged the request (HTTP ${httpStatus}); no results were served`,
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

  private parse(html: string, limit: number): WebSearchResult[] {
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
 * The ordered, independent search providers to try. DuckDuckGo is always
 * present; the operator-configured provider is tried first when configured so a
 * working paid/keyed API is preferred over the scrape-prone default.
 */
export interface SearchProviderSet {
  providers: SearchProvider[];
}

export async function resolveSearchProviders(
  custom: SearchProvider | null
): Promise<SearchProvider[]> {
  const list: SearchProvider[] = [];
  if (custom && (await Promise.resolve(custom.configured()))) list.push(custom);
  list.push(new DuckDuckGoHtmlProvider());
  return list;
}
