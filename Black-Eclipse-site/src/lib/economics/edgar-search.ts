// ── EDGAR full-text search ──────────────────────────────────────────────────
// The SEC's official full-text index (`efts.sec.gov/LATEST/search-index`)
// searches the text of every filing and returns JSON. This is distinct from the
// current-events feed (newest filings) and the submissions index (one issuer's
// filings): here a keyword can be traced across the whole market.
//
// Only fields the SEC returns are used. A hit without a resolvable document is
// dropped, and a document URL is constructed only from the SEC's own accession
// + filename pair.

import { safeGet } from "@/lib/connectors/security";
import { SEC_USER_AGENT } from "@/lib/fundamentals/providers/sec-edgar";
import { isPlausibleForm, type EdgarFiling } from "./sec-filings-feed";

const SEARCH_URL = "https://efts.sec.gov/LATEST/search-index";
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_LIMIT = 100;

export interface EdgarSearchResult {
  filings: EdgarFiling[];
  total: number;
  query: string;
  retrievedAt: string;
  cached: boolean;
}

interface RawHit {
  _id?: unknown;
  _score?: unknown;
  _source?: Record<string, unknown>;
}

function strArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function firstString(value: unknown): string | null {
  const arr = strArray(value);
  return arr.length > 0 ? arr[0] : null;
}

/** Split "Apple Inc.  (AAPL)  (CIK 0000320193)" into name, ticker, CIK. */
export function parseDisplayName(display: string | null): {
  company: string;
  ticker: string | null;
  cik: string | null;
} {
  if (!display) return { company: "", ticker: null, cik: null };
  const match = display.match(/^(.*?)\s+\(([^()]+)\)\s+\(CIK\s+(\d+)\)\s*$/);
  if (!match) return { company: display.trim(), ticker: null, cik: null };
  return { company: match[1].trim(), ticker: match[2].trim() || null, cik: match[3] };
}

export function parseEdgarSearch(payload: unknown): { filings: EdgarFiling[]; total: number } {
  const root = payload as { hits?: { total?: { value?: unknown }; hits?: unknown } } | null;
  const rawHits = root?.hits?.hits;
  const hits: RawHit[] = Array.isArray(rawHits) ? (rawHits as RawHit[]) : [];
  const totalRaw = root?.hits?.total?.value;
  const total = typeof totalRaw === "number" ? totalRaw : hits.length;

  const filings: EdgarFiling[] = [];
  const seen = new Set<string>();
  for (const hit of hits) {
    const source = hit._source;
    const id = typeof hit._id === "string" ? hit._id : null;
    if (!source || !id) continue;
    const [accession, filename] = id.split(":");
    if (!accession || !filename) continue;
    if (seen.has(id)) continue;

    const display = firstString(source.display_names);
    const parsed = parseDisplayName(display);
    const cik = firstString(source.ciks) ?? parsed.cik;
    if (!cik) continue;

    const form = String(source.form ?? firstString(source.root_forms) ?? "").trim();
    if (!form) continue;

    const url = `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${accession.replace(/-/g, "")}/${filename}`;
    seen.add(id);
    filings.push({
      id,
      company: parsed.company || display || "Unknown issuer",
      cik,
      ticker: parsed.ticker,
      form,
      filed: typeof source.file_date === "string" ? source.file_date : null,
      updated: null,
      accession,
      items: strArray(source.items),
      url,
    });
  }

  return { filings, total };
}

interface CacheEntry {
  at: number;
  filings: EdgarFiling[];
  total: number;
}

const CACHE_TTL_MS = 3 * 60 * 1000;
const cache = new Map<string, CacheEntry>();

export async function searchEdgarFilings(
  options: {
    query: string;
    forms?: string;
    start?: string;
    end?: string;
    limit?: number;
    refresh?: boolean;
  },
  deps: { get?: typeof safeGet; now?: () => number } = {},
): Promise<EdgarSearchResult> {
  const query = options.query.trim();
  if (query.length < 2) throw new Error("query must be at least 2 characters");
  if (query.length > 200) throw new Error("query is too long");

  const forms = (options.forms ?? "").trim();
  if (forms) {
    for (const form of forms.split(",").map((f) => f.trim())) {
      if (!isPlausibleForm(form)) throw new Error(`invalid form type: ${form}`);
    }
  }
  const start = (options.start ?? "").trim();
  const end = (options.end ?? "").trim();
  for (const [label, value] of [["start", start], ["end", end]] as const) {
    if (value && !DATE_RE.test(value)) throw new Error(`${label} must be YYYY-MM-DD`);
  }
  const limit = Math.max(1, Math.min(MAX_LIMIT, options.limit ?? 40));
  const key = `${query}|${forms}|${start}|${end}|${limit}`;
  const now = deps.now ?? Date.now;

  const hit = cache.get(key);
  if (!options.refresh && hit && now() - hit.at < CACHE_TTL_MS) {
    return {
      filings: hit.filings,
      total: hit.total,
      query,
      retrievedAt: new Date(hit.at).toISOString(),
      cached: true,
    };
  }

  const params = new URLSearchParams({ q: query, from: "0" });
  if (forms) params.set("forms", forms);
  if (start && end) {
    params.set("dateRange", "custom");
    params.set("startdt", start);
    params.set("enddt", end);
  }

  const get = deps.get ?? safeGet;
  const res = await get({
    url: `${SEARCH_URL}?${params.toString()}`,
    headers: {
      "user-agent": SEC_USER_AGENT,
      accept: "application/json",
    },
    timeoutMs: 12_000,
    maxBytes: 8 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`EDGAR full-text search HTTP ${res.status}`);
  }
  let payload: unknown;
  try {
    payload = JSON.parse(res.text);
  } catch {
    throw new Error("EDGAR full-text search returned non-JSON");
  }
  const parsed = parseEdgarSearch(payload);
  const filings = parsed.filings.slice(0, limit);
  cache.set(key, { at: now(), filings, total: parsed.total });
  return {
    filings,
    total: parsed.total,
    query,
    retrievedAt: new Date(now()).toISOString(),
    cached: false,
  };
}

export function __resetEdgarSearchCache(): void {
  cache.clear();
}
