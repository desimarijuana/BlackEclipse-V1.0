// ── Structured academic / news / media connectors ───────────────────────────
// Web search is not the only retrieval shape. Academic questions need
// OpenAlex/Crossref/arXiv/PubMed; news needs GDELT; images/video need a media
// index. These are first-class, KEYLESS connectors reached through the same
// SSRF-hardened transport as web search — not keyword hacks over DuckDuckGo.
//
// Every connector returns the SAME normalized shape (`WebSearchResult[]` + a
// `RetrievalDiagnostic`) so the Python research registry can treat them
// uniformly and fall back to web search when a connector is unavailable.
// Nothing is fabricated: an empty answer is `zero_results`, a failure is a
// named category, never a guessed result.

import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import {
  failedDiagnostic,
  okDiagnostic,
  zeroResultDiagnostic,
  type RetrievalDiagnostic,
} from "@/lib/retrieval-diagnostics";
import type { WebSearchResult } from "@/lib/web-search";

const UA = "BlackEclipse/1.0 (open-source financial research; contact@blackeclipse.local)";
const TIMEOUT_MS = 12_000;
const MAX_BYTES = 4 * 1024 * 1024;

export type ConnectorKind = "academic" | "news" | "image" | "video";

export interface ConnectorOutcome {
  results: WebSearchResult[];
  diagnostic: RetrievalDiagnostic;
}

function base(kind: ConnectorKind, provider: string): Pick<RetrievalDiagnostic, "capability" | "provider" | "tier"> {
  return { capability: "web_search", provider, tier: "secondary" };
}

async function getJson(
  url: string,
  provider: string,
  kind: ConnectorKind
): Promise<{ ok: true; payload: unknown; latencyMs: number } | { ok: false; diagnostic: RetrievalDiagnostic; latencyMs: number }> {
  const check = validateOutboundUrl(url);
  if (!check.safe) {
    return {
      ok: false,
      latencyMs: 0,
      diagnostic: failedDiagnostic(base(kind, provider), "blocked", `URL rejected: ${check.reason ?? "unsafe"}`, {
        retryable: false,
      }),
    };
  }
  const started = Date.now();
  try {
    const res = await safeGet({
      url,
      timeoutMs: TIMEOUT_MS,
      maxBytes: MAX_BYTES,
      headers: { "user-agent": UA, accept: "application/json" },
    });
    const latencyMs = Date.now() - started;
    if (res.status < 200 || res.status >= 300) {
      return {
        ok: false,
        latencyMs,
        diagnostic: failedDiagnostic(base(kind, provider), "http_error", `${provider} returned HTTP ${res.status}`, {
          latencyMs,
          httpStatus: res.status,
          bytes: res.bytes,
        }),
      };
    }
    return { ok: true, payload: JSON.parse(res.text), latencyMs };
  } catch (err) {
    const code = err instanceof OutboundError ? err.code : "";
    const timedOut = code === "timeout";
    const latencyMs = Date.now() - started;
    return {
      ok: false,
      latencyMs,
      diagnostic: failedDiagnostic(
        base(kind, provider),
        timedOut ? "timeout" : code === "blocked_host" || code === "blocked_protocol" ? "blocked" : "transport_error",
        timedOut ? `${provider} timed out after ${TIMEOUT_MS} ms` : `${provider} request failed`,
        { latencyMs, timedOut }
      ),
    };
  }
}

function ok(provider: string, kind: ConnectorKind, results: WebSearchResult[], latencyMs: number, bytes: number): ConnectorOutcome {
  return {
    results,
    diagnostic: okDiagnostic(base(kind, provider), { latencyMs, bytes, resultCount: results.length }),
  };
}

function empty(provider: string, kind: ConnectorKind, latencyMs: number): ConnectorOutcome {
  return {
    results: [],
    diagnostic: zeroResultDiagnostic(base(kind, provider), `${provider} answered but returned no matches`, { latencyMs }),
  };
}

// ── Academic: OpenAlex (primary keyless scholarly index) ────────────────────

function reconstructAbstract(inv: unknown): string {
  if (!inv || typeof inv !== "object") return "";
  const pairs: Array<[number, string]> = [];
  for (const [word, positions] of Object.entries(inv as Record<string, unknown>)) {
    if (Array.isArray(positions)) for (const p of positions) if (typeof p === "number") pairs.push([p, word]);
  }
  pairs.sort((a, b) => a[0] - b[0]);
  return pairs.map(([, w]) => w).join(" ");
}

export async function openAlexSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "openalex";
  const kind: ConnectorKind = "academic";
  const perPage = Math.min(Math.max(limit, 1), 25);
  const url = `https://api.openalex.org/works?search=${encodeURIComponent(query)}&per-page=${perPage}&sort=relevance_score:desc`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const rows = (got.payload as { results?: unknown[] })?.results;
  if (!Array.isArray(rows) || rows.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const row of rows) {
    if (results.length >= limit) break;
    const r = row as Record<string, unknown>;
    const doi = typeof r.doi === "string" ? r.doi : "";
    const loc = r.primary_location as Record<string, unknown> | undefined;
    const landing = loc && typeof loc.landing_page_url === "string" ? (loc.landing_page_url as string) : "";
    const url2 = doi || landing;
    if (!url2) continue;
    const oa = (r.open_access ?? {}) as Record<string, unknown>;
    const best = (r.best_oa_location ?? {}) as Record<string, unknown>;
    const pdfUrl = typeof best.pdf_url === "string" ? best.pdf_url : null;
    results.push({
      title: String(r.display_name ?? r.title ?? "").trim() || "Untitled work",
      url: url2,
      snippet: reconstructAbstract(r.abstract_inverted_index).slice(0, 500),
      publishedAt: r.publication_date ? String(r.publication_date) : r.publication_year ? String(r.publication_year) : null,
      pdfUrl,
      isOpenAccess: Boolean(oa.is_oa) || Boolean(pdfUrl),
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

// ── Academic: Semantic Scholar (citation-aware scholarly index) ─────────────

export async function semanticScholarSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "semantic-scholar";
  const kind: ConnectorKind = "academic";
  const max = Math.min(Math.max(limit, 1), 25);
  const fields = "title,abstract,url,year,venue,authors,externalIds,openAccessPdf,references.title,references.externalIds";
  const url =
    `https://api.semanticscholar.org/graph/v1/paper/search?query=${encodeURIComponent(query)}` +
    `&limit=${max}&fields=${fields}`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const rows = (got.payload as { data?: unknown[] })?.data;
  if (!Array.isArray(rows) || rows.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const row of rows) {
    if (results.length >= limit) break;
    const r = row as Record<string, unknown>;
    const ids = (r.externalIds ?? {}) as Record<string, unknown>;
    const doi = typeof ids.DOI === "string" ? ids.DOI : "";
    const url2 = doi ? `https://doi.org/${doi}` : String(r.url ?? "").trim();
    if (!url2) continue;
    const oaPdf = (r.openAccessPdf ?? {}) as Record<string, unknown>;
    const pdfUrl = typeof oaPdf.url === "string" ? oaPdf.url : null;
    const refs = Array.isArray(r.references)
      ? (r.references as Array<Record<string, unknown>>)
          .filter((ref) => typeof ref.title === "string")
          .slice(0, 50)
          .map((ref) => ({
            title: String(ref.title),
            doi: typeof (ref.externalIds as Record<string, unknown> | undefined)?.DOI === "string"
              ? String((ref.externalIds as Record<string, unknown>).DOI)
              : null,
          }))
      : [];
    results.push({
      title: String(r.title ?? "").trim() || "Untitled work",
      url: url2,
      snippet: String(r.abstract ?? "").slice(0, 500),
      publishedAt: r.year ? String(r.year) : null,
      pdfUrl,
      isOpenAccess: Boolean(oaPdf.isOpenAccess) || Boolean(pdfUrl),
      references: refs,
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

// ── Academic: Crossref (fallback registry, DOIs) ────────────────────────────

export async function crossrefSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "crossref";
  const kind: ConnectorKind = "academic";
  const rows = Math.min(Math.max(limit, 1), 25);
  const url = `https://api.crossref.org/works?query=${encodeURIComponent(query)}&rows=${rows}&select=DOI,title,URL,abstract,published`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const items = ((got.payload as { message?: { items?: unknown[] } })?.message?.items) ?? [];
  if (!Array.isArray(items) || items.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const item of items) {
    if (results.length >= limit) break;
    const r = item as Record<string, unknown>;
    const url2 = typeof r.URL === "string" ? r.URL : r.DOI ? `https://doi.org/${r.DOI}` : "";
    if (!url2) continue;
    const title = Array.isArray(r.title) ? String(r.title[0] ?? "") : String(r.title ?? "");
    results.push({
      title: title.trim() || "Untitled work",
      url: url2,
      snippet: String(r.abstract ?? "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 500),
      publishedAt: null,
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

// ── News: GDELT (keyless global news event index) ───────────────────────────

export async function gdeltSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "gdelt";
  const kind: ConnectorKind = "news";
  const max = Math.min(Math.max(limit, 1), 25);
  const url = `https://api.gdeltproject.org/api/v2/doc/doc?query=${encodeURIComponent(query)}&mode=artlist&format=json&maxrecords=${max}&sort=datedesc`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const articles = (got.payload as { articles?: unknown[] })?.articles;
  if (!Array.isArray(articles) || articles.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const a of articles) {
    if (results.length >= limit) break;
    const r = a as Record<string, unknown>;
    const url2 = String(r.url ?? "").trim();
    if (!url2) continue;
    const seendate = String(r.seendate ?? "");
    results.push({
      title: String(r.title ?? "").trim() || String(r.domain ?? "Untitled"),
      url: url2,
      snippet: String(r.domain ?? ""),
      publishedAt: seendate ? _gdeltDate(seendate) : null,
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

function _gdeltDate(s: string): string | null {
  // GDELT seendate: YYYYMMDDTHHMMSSZ
  const m = s.match(/^(\d{4})(\d{2})(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
}

// ── Media: Openverse (images) and Wikimedia Commons (image/video) ───────────

export async function openverseSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "openverse";
  const kind: ConnectorKind = "image";
  const pageSize = Math.min(Math.max(limit, 1), 25);
  const url = `https://api.openverse.org/v1/images/?q=${encodeURIComponent(query)}&page_size=${pageSize}`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const rows = (got.payload as { results?: unknown[] })?.results;
  if (!Array.isArray(rows) || rows.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const row of rows) {
    if (results.length >= limit) break;
    const r = row as Record<string, unknown>;
    const url2 = String(r.foreign_landing_url ?? r.url ?? "").trim();
    if (!url2) continue;
    results.push({
      title: String(r.title ?? "").trim() || "Untitled image",
      url: url2,
      snippet: `Image by ${String(r.creator ?? "unknown")} (${String(r.license ?? "see source")})`,
      publishedAt: null,
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

export async function commonsSearch(query: string, limit: number, kind: "image" | "video"): Promise<ConnectorOutcome> {
  const provider = "wikimedia-commons";
  const filetype = kind === "video" ? "video" : "bitmap";
  const max = Math.min(Math.max(limit, 1), 25);
  const url =
    `https://commons.wikimedia.org/w/api.php?action=query&list=search&format=json&srnamespace=6` +
    `&srlimit=${max}&srsearch=${encodeURIComponent(`filetype:${filetype} ${query}`)}`;
  const got = await getJson(url, provider, kind);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const rows = ((got.payload as { query?: { search?: unknown[] } })?.query?.search) ?? [];
  if (!Array.isArray(rows) || rows.length === 0) return empty(provider, kind, got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const row of rows) {
    if (results.length >= limit) break;
    const title = String((row as Record<string, unknown>).title ?? "").replace(/^File:/, "").trim();
    if (!title) continue;
    results.push({
      title,
      url: `https://commons.wikimedia.org/wiki/${encodeURIComponent("File:" + title)}`,
      snippet: `${kind} on Wikimedia Commons`,
      publishedAt: null,
    });
  }
  return results.length ? ok(provider, kind, results, got.latencyMs, 0) : empty(provider, kind, got.latencyMs);
}

// ── Dispatch ────────────────────────────────────────────────────────────────

/**
 * Run the keyless connector chain for a kind. The first connector that returns
 * results wins; a connector failure falls through to the next; every attempt is
 * recorded. Returns at least one diagnostic (never an empty list).
 */
function academicKey(result: WebSearchResult): string {
  const doi = result.url.match(/10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+/i);
  if (doi) return `doi:${doi[0].toLowerCase().replace(/\.$/, "")}`;
  return `title:${result.title.toLowerCase().replace(/[^a-z0-9]+/g, "")}`;
}

/** Academic results are merged across providers, not first-wins. */
async function runAcademicConnectors(
  query: string,
  limit: number
): Promise<{ results: WebSearchResult[]; diagnostics: RetrievalDiagnostic[]; provider: string | null }> {
  const connectors = [openAlexSearch, semanticScholarSearch, crossrefSearch];
  const settled = await Promise.allSettled(connectors.map((fn) => fn(query, limit)));
  const diagnostics: RetrievalDiagnostic[] = [];
  const byKey = new Map<string, WebSearchResult>();
  const providers = new Set<string>();
  for (const outcome of settled) {
    if (outcome.status !== "fulfilled") continue;
    diagnostics.push(outcome.value.diagnostic);
    if (outcome.value.results.length > 0) providers.add(outcome.value.diagnostic.provider);
    for (const result of outcome.value.results) {
      const key = academicKey(result);
      if (!byKey.has(key)) byKey.set(key, result);
    }
  }
  const results = [...byKey.values()].slice(0, Math.max(limit, 1) * 2);
  return {
    results,
    diagnostics: diagnostics.length ? diagnostics : [],
    provider: providers.size ? [...providers].join("+") : null,
  };
}

export async function runConnectors(
  kind: ConnectorKind,
  query: string,
  limit: number
): Promise<{ results: WebSearchResult[]; diagnostics: RetrievalDiagnostic[]; provider: string | null }> {
  if (kind === "academic") return runAcademicConnectors(query, limit);
  const chain: Array<(q: string, l: number) => Promise<ConnectorOutcome>> =
    kind === "news"
      ? [gdeltSearch]
      : kind === "image"
        ? [openverseSearch, (q, l) => commonsSearch(q, l, "image")]
        : [(q, l) => commonsSearch(q, l, "video"), (q, l) => commonsSearch(q, l, "image")];

  const diagnostics: RetrievalDiagnostic[] = [];
  for (const connector of chain) {
    const outcome = await connector(query, limit);
    diagnostics.push(outcome.diagnostic);
    if (outcome.results.length > 0) {
      return { results: outcome.results, diagnostics, provider: outcome.diagnostic.provider };
    }
    if (outcome.diagnostic.category === "zero_results") {
      return { results: [], diagnostics, provider: outcome.diagnostic.provider };
    }
  }
  return { results: [], diagnostics, provider: null };
}
