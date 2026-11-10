// ── Economy web fallback (screener-style) ───────────────────────────────────
// When a structured provider has no value for a metric, the app may look for it
// on an OFFICIAL source the same way the stock verification panel does:
//   web_search → keep only official hosts → fetch the page → extract a
//   labelled number + date deterministically.
//
// Guardrails:
//   • Never replaces a structured (LIVE) value — only fills a gap.
//   • Only official-domain pages are eligible.
//   • A value requires a label match AND a plausible numeric range; otherwise
//     the metric stays unavailable. Nothing is guessed from a headline alone.
//   • Callers mark the result as WEB provenance, with the source URL attached.

import { fetchWebPageDetailed, searchWeb } from "@/lib/web-research";

/** Official statistical / central-bank hosts eligible for the economy fallback. */
export const ECON_OFFICIAL_DOMAINS = [
  "fred.stlouisfed.org",
  "bls.gov",
  "bea.gov",
  "federalreserve.gov",
  "treasury.gov",
  "ecb.europa.eu",
  "bankofengland.co.uk",
  "boj.or.jp",
  "rba.gov.au",
  "rbnz.govt.nz",
  "bankofcanada.ca",
  "snb.ch",
  "rbi.org.in",
  "sbp.org.pk",
  "pbc.gov.cn",
  "worldbank.org",
  "imf.org",
  "oecd.org",
  "ons.gov.uk",
  "stats.gov.cn",
  "statcan.gc.ca",
  "mospi.gov.in",
  "pbs.gov.pk",
  "stat.go.jp",
  "ec.europa.eu",
  "census.gov",
];

export function isOfficialEconHost(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./i, "").toLowerCase();
    return ECON_OFFICIAL_DOMAINS.some((d) => host === d || host.endsWith(`.${d}`));
  } catch {
    return false;
  }
}

export interface WebMetricSpec {
  /** Search query used to find the official page. */
  query: string;
  /**
   * A labelled number: capture group 1 must be the numeric value. Keep these
   * narrow — a broad regex is how a wrong number gets attached to a label.
   */
  pattern: RegExp;
  /** Reject parsed values outside the plausible range. */
  min: number;
  max: number;
}

export interface WebMetricResult {
  value: number;
  asOf: string | null;
  url: string;
  provider: string;
  retrievedAt: string;
}

export interface EnrichmentDeps {
  search?: typeof searchWeb;
  fetchPage?: typeof fetchWebPageDetailed;
  now?: () => number;
}

function parseAsOf(text: string, index: number): string | null {
  const window = text.slice(Math.max(0, index - 260), index + 260);
  const iso = window.match(/\b(20\d{2})-(\d{2})-(\d{2})\b/);
  if (iso) return iso[0];
  const monthYear = window.match(
    /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b/i,
  );
  if (monthYear) {
    const month = new Date(`${monthYear[1]} 1, ${monthYear[2]}`).getMonth() + 1;
    return `${monthYear[2]}-${String(month).padStart(2, "0")}`;
  }
  return null;
}

/** Extract a labelled value from fetched page text. Exported for tests. */
export function extractMetricFromText(
  text: string,
  spec: Pick<WebMetricSpec, "pattern" | "min" | "max">,
): { value: number; asOf: string | null } | null {
  const match = spec.pattern.exec(text);
  if (!match) return null;
  const raw = Number(match[1].replace(/,/g, ""));
  if (!Number.isFinite(raw) || raw < spec.min || raw > spec.max) return null;
  return { value: raw, asOf: parseAsOf(text, match.index) };
}

const MAX_ENRICHMENTS = 8;

/**
 * Try to fill a single missing metric from official web sources. Returns null
 * when no official page yielded a confident, in-range labelled value.
 */
export async function enrichMetricFromWeb(
  spec: WebMetricSpec,
  deps: EnrichmentDeps = {},
): Promise<WebMetricResult | null> {
  const search = deps.search ?? searchWeb;
  const fetchPage = deps.fetchPage ?? fetchWebPageDetailed;
  const now = deps.now ?? Date.now;

  const found = await search(spec.query, 6);
  const official = found.results.filter((r) => r.url && isOfficialEconHost(r.url));
  if (official.length === 0) return null;

  for (const result of official.slice(0, 2)) {
    try {
      const page = await fetchPage(result.url);
      if (!page.page) continue;
      const parsed = extractMetricFromText(page.page.text, spec);
      if (!parsed) continue;
      return {
        value: parsed.value,
        asOf: parsed.asOf,
        url: result.url,
        provider: new URL(result.url).hostname.replace(/^www\./i, ""),
        retrievedAt: new Date(now()).toISOString(),
      };
    } catch {
      // Try the next official result — one failed page is not fatal.
    }
  }
  return null;
}

/**
 * Enrich a set of labelled metrics concurrently. `specs` is keyed by metric id;
 * ids without a spec are skipped. Hard-capped so a total provider outage cannot
 * turn one snapshot request into dozens of outbound calls.
 */
export async function enrichMetrics(
  missing: Array<{ id: string }>,
  specs: Record<string, WebMetricSpec>,
  deps: EnrichmentDeps = {},
): Promise<Record<string, WebMetricResult>> {
  const candidates = missing.filter((m) => specs[m.id]).slice(0, MAX_ENRICHMENTS);
  const settled = await Promise.all(
    candidates.map(async (m) => {
      try {
        return [m.id, await enrichMetricFromWeb(specs[m.id], deps)] as const;
      } catch {
        return [m.id, null] as const;
      }
    }),
  );
  const out: Record<string, WebMetricResult> = {};
  for (const [id, result] of settled) {
    if (result) out[id] = result;
  }
  return out;
}
