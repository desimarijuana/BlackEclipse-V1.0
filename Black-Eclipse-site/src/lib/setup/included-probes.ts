// ── Included-source reachability probes (client-safe data) ─────────────────
// One small, fixed endpoint per included open source. Keeping this separate
// from `check.ts` (which imports Prisma-backed settings) means a unit test can
// assert every included source has a probe without loading the server stack.
//
// These are reachability probes, not data pulls. They use documented endpoints,
// one bounded request each, and no page a provider forbids scraping.

import type { SourceId } from "./types";

export interface Probe {
  url: string;
  headers?: Record<string, string>;
}

// SEC (and some other agencies) reject a generic User-Agent. A contact-shaped
// value is required by their fair-access policy.
const UA = "BlackEclipse setup-check admin@blackeclipse.local";

export const INCLUDED_PROBES: Partial<Record<SourceId, Probe>> = {
  sec: {
    url: "https://data.sec.gov/submissions/CIK0000320193.json",
    headers: { "user-agent": UA, accept: "application/json" },
  },
  fred: {
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP",
    headers: { "user-agent": UA },
  },
  bea: {
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDPC1",
    headers: { "user-agent": UA },
  },
  bls: {
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",
    headers: { "user-agent": UA },
  },
  worldbank: {
    url: "https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&per_page=1",
    headers: { "user-agent": UA, accept: "application/json" },
  },
  eurostat: {
    url: "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_cphi_m?lang=EN&time=2024&geo=EU27_2020",
    headers: { "user-agent": UA, accept: "application/json" },
  },
  gdelt: {
    // The DOC API is frequently rate-limited/slow; the v2 last-update file is
    // the cheapest reliable reachability signal for the same service.
    url: "https://data.gdeltproject.org/gdeltv2/lastupdate.txt",
    headers: { "user-agent": UA, accept: "text/plain" },
  },
  usgs: {
    url: "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson",
    headers: { "user-agent": UA, accept: "application/json" },
  },
  firms: {
    url: "https://firms.modaps.eosdis.nasa.gov/active_fire/",
    headers: { "user-agent": UA },
  },
  "news-rss": {
    url: "https://www.sec.gov/news/pressreleases.rss",
    headers: { "user-agent": UA, accept: "application/rss+xml, application/xml, text/xml" },
  },
};

export function hasIncludedProbe(id: SourceId): boolean {
  return Boolean(INCLUDED_PROBES[id]);
}
