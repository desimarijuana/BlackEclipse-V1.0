// ── Market-wide SEC "latest filings" feed ───────────────────────────────────
// EDGAR publishes a current-events Atom feed
//   /cgi-bin/browse-edgar?action=getcurrent&type=<form>&count=<n>&output=atom
// This is official, keyless and newest-first. We parse only what the feed
// states: company, CIK, form, filed date/time, accession and the filing index
// URL. An entry we cannot parse is dropped, never guessed.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { SEC_USER_AGENT } from "@/lib/fundamentals/providers/sec-edgar";

const BASE_URL =
  "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&company=&dateb=&owner=include&output=atom";

export interface EdgarFiling {
  id: string;
  company: string;
  cik: string | null;
  ticker?: string | null;
  form: string;
  filed: string | null;
  /** Provider timestamp (ISO) — useful for ordering. */
  updated: string | null;
  accession: string | null;
  items: string[];
  url: string;
}

const FORM_RE = /^[A-Za-z0-9 /-]{1,16}$/;
const MAX_LIMIT = 100;

export function isPlausibleForm(form: string): boolean {
  return FORM_RE.test(form);
}

export function parseEdgarFeed(xml: string): EdgarFiling[] {
  const $ = cheerio.load(xml, { xmlMode: true });
  const filings: EdgarFiling[] = [];

  $("entry").each((_, entry) => {
    const $entry = $(entry);
    const title = $entry.find("title").first().text().replace(/\s+/g, " ").trim();
    const link = $entry.find('link[rel="alternate"]').first().attr("href") ?? "";
    if (!link) return;

    // "8-K - Ribbon Acquisition Corp. (0002035016) (Filer)"
    const match = title.match(/^(.+?)\s+-\s+(.+?)\s+\((\d{7,10})\)(?:\s+\(Filer\))?$/);
    const formFromCategory = $entry.find('category[label="form type"]').first().attr("term") ?? "";
    const form = (match?.[1] ?? formFromCategory).trim();
    const company = (match?.[2] ?? title).trim();
    const cik = match?.[3] ?? null;
    if (!form) return;

    const summary = $entry
      .find("summary")
      .first()
      .text()
      .replace(/<[^>]+>/g, " ")
      .replace(/\r/g, "");
    const filed = summary.match(/Filed:\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
    const accession = summary.match(/AccNo:\s*([0-9-]+)/)?.[1] ?? null;
    const items: string[] = [];
    for (const line of summary.split("\n")) {
      const item = line.match(/Item\s+[\d.]+\s*:\s*(.+)/);
      if (item) items.push(item[1].trim());
    }

    const updated = $entry.find("updated").first().text().trim() || null;
    const urnId = $entry.find("id").first().text().trim();

    filings.push({
      id: accession ?? urnId ?? link,
      company,
      cik,
      form,
      filed,
      updated,
      accession,
      items,
      url: link,
    });
  });

  return filings;
}

interface CacheEntry {
  at: number;
  filings: EdgarFiling[];
}

const CACHE_TTL_MS = 3 * 60 * 1000;
const cache = new Map<string, CacheEntry>();

function feedUrl(form: string, limit: number): string {
  const params = new URLSearchParams();
  if (form) params.set("type", form);
  params.set("count", String(limit));
  return `${BASE_URL}&${params.toString()}`;
}

export interface FilingsFeedResult {
  filings: EdgarFiling[];
  form: string;
  retrievedAt: string;
  cached: boolean;
}

export async function fetchLatestFilings(
  options: { form?: string; limit?: number; refresh?: boolean } = {},
  deps: { get?: typeof safeGet; now?: () => number } = {},
): Promise<FilingsFeedResult> {
  const form = (options.form ?? "").trim();
  if (form && !isPlausibleForm(form)) throw new Error("invalid form type");
  const limit = Math.max(1, Math.min(MAX_LIMIT, options.limit ?? 40));
  const key = `${form || "*"}|${limit}`;
  const now = deps.now ?? Date.now;

  const hit = cache.get(key);
  if (!options.refresh && hit && now() - hit.at < CACHE_TTL_MS) {
    return {
      filings: hit.filings,
      form,
      retrievedAt: new Date(hit.at).toISOString(),
      cached: true,
    };
  }

  const get = deps.get ?? safeGet;
  const res = await get({
    url: feedUrl(form, limit),
    headers: {
      "user-agent": SEC_USER_AGENT,
      accept: "application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    },
    timeoutMs: 10_000,
    maxBytes: 4 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`EDGAR latest-filings HTTP ${res.status}`);
  }
  const filings = parseEdgarFeed(res.text).slice(0, limit);
  cache.set(key, { at: now(), filings });
  return {
    filings,
    form,
    retrievedAt: new Date(now()).toISOString(),
    cached: false,
  };
}

export function __resetFilingsFeedCache(): void {
  cache.clear();
}
