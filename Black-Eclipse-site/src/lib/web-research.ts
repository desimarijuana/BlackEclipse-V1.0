// ── Shared web research ──────────────────────────────────────────────────────
// The ONE web search + page retrieval implementation for the whole application.
// It exists so the Phase-2 retrieval layer (`/api/harness/data`) and the legacy
// agent tool (`src/lib/agent/tools.ts`) do not each grow their own copy — a
// second web-search system is explicitly forbidden.
//
// Search: DuckDuckGo HTML (no key). Page fetch: the SSRF-hardened `safeGet`
// transport in `connectors/security.ts`. Extraction: cheerio (already a dep).
// Nothing is fabricated: an unparseable page yields null.

import * as cheerio from "cheerio";
import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";

export interface WebSearchResult {
  title: string;
  url: string;
  snippet: string;
  publishedAt?: string | null;
}

export interface WebPage {
  url: string;
  title: string | null;
  text: string;
  bytes: number;
}

const SEARCH_TIMEOUT_MS = 10_000;
const FETCH_TIMEOUT_MS = 8_000;
const MAX_HTML_BYTES = 512 * 1024;
const MAX_TEXT_CHARS = 20_000;

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

/**
 * Search the web via DuckDuckGo's HTML endpoint. Returns ranked results with
 * title, url and snippet. Never throws — an empty array means "nothing found".
 */
export async function webSearch(query: string, limit = 8): Promise<WebSearchResult[]> {
  const q = query.trim();
  if (!q) return [];
  try {
    const res = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(q)}`, {
      headers: { "User-Agent": UA },
      signal: AbortSignal.timeout(SEARCH_TIMEOUT_MS),
    });
    if (!res.ok) return [];
    const html = await res.text();
    const $ = cheerio.load(html);
    const out: WebSearchResult[] = [];
    $("a.result__a").each((_i, el) => {
      if (out.length >= limit) return;
      const href = $(el).attr("href") || "";
      const title = $(el).text().replace(/\s+/g, " ").trim();
      const snippet = $(el)
        .closest(".result")
        .find(".result__snippet")
        .text()
        .replace(/\s+/g, " ")
        .trim();
      const url = unwrapDuckDuckGo(href);
      if (!url || !title) return;
      out.push({ title, url, snippet, publishedAt: null });
    });
    return out;
  } catch {
    return [];
  }
}

/** DuckDuckGo wraps outbound links in a redirect; recover the real URL. */
function unwrapDuckDuckGo(href: string): string {
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

/**
 * Retrieve a page through the SSRF-hardened transport and extract readable text.
 * Returns null for blocked hosts, non-HTML responses, errors and timeouts.
 */
export async function fetchWebPage(url: string): Promise<WebPage | null> {
  if (!validateOutboundUrl(url).safe) return null;
  try {
    const res = await safeGet({
      url,
      timeoutMs: FETCH_TIMEOUT_MS,
      maxBytes: MAX_HTML_BYTES,
      headers: { "user-agent": UA, accept: "text/html,application/xhtml+xml" },
    });
    if (res.status < 200 || res.status >= 300) return null;
    const type = (res.contentType ?? "").toLowerCase();
    if (type && !type.includes("html") && !type.includes("xml") && !type.includes("text")) return null;

    const $ = cheerio.load(res.text);
    $("script, style, noscript, nav, header, footer, aside, form, svg").remove();
    const title =
      ($('meta[property="og:title"]').attr("content") || $("title").first().text() || "").trim() || null;
    const text = $("body")
      .text()
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, MAX_TEXT_CHARS);
    if (!text) return null;
    return { url, title, text, bytes: res.bytes };
  } catch (err) {
    if (!(err instanceof OutboundError)) {
      console.warn("[web-research] fetch failed:", url.slice(0, 80), err instanceof Error ? err.message : err);
    }
    return null;
  }
}

export { validateOutboundUrl };
