// ── Investor Eye — source catalog & data governance ─────────────────────────
// The spec's data-governance requirement (§6 / §36): every external source must
// carry its license, whether commercial use is allowed, whether it needs a key,
// its rate limit, its expected freshness, and the attribution the UI must show.
//
// WHY THIS IS A SEPARATE MODULE FROM THE SOURCE ADAPTERS:
// An adapter answers "how do I fetch and normalize this?" — a question about
// code. The catalog answers "am I ALLOWED to use this, and what must I say about
// it?" — a question about law and honesty. Fusing them would mean a license
// question could only be answered by constructing a fetcher, and a new adapter
// could ship without anyone noticing it has no license entry.
//
// The catalog is keyed by source id and a test asserts every REGISTERED source
// has an entry, so adding a provider without declaring its license fails CI.
//
// "Public API" does NOT imply "free for commercial use". Nothing here is
// inferred from a URL being reachable — each entry records what the provider
// actually states, with a link an operator can check.

/**
 * How the data may be used. Deliberately coarse: the exact terms live at
 * `licenseUrl` / `termsUrl`, and this is the machine-checkable summary.
 */
export type CommercialUse = 'yes' | 'no' | 'unknown';

/** Expected update cadence — so the UI never implies more freshness than exists. */
export type DataFreshness = 'seconds' | 'minutes' | 'hourly' | 'daily' | 'static';

export interface SourceCatalogEntry {
  /** Matches the `EventSource.id` in `sources/registry.ts`. */
  id: string;
  name: string;
  /** The providing organisation (not the BlackEclipse id). */
  provider: string;
  category: 'news' | 'geopolitical' | 'hazard' | 'geography' | 'market' | 'maritime' | 'aviation' | 'space' | 'infrastructure';
  website: string;
  /** Human label for the license, e.g. 'Public domain'. */
  license: string;
  licenseUrl?: string;
  termsUrl?: string;
  commercialUse: CommercialUse;
  /** True when the source cannot run without an operator-supplied credential. */
  requiresApiKey: boolean;
  attributionRequired: boolean;
  /** The exact attribution line the UI should render when required. */
  attribution?: string;
  /** Documented limit, or `undefined` when unlimited/undocumented. */
  rateLimit?: string;
  dataFreshness: DataFreshness;
  /**
   * True when the data is produced by BlackEclipse itself rather than fetched
   * from a third party (currently only the stored RSS corpus). A license link is
   * not required for local data — the upstream feed terms are declared per feed
   * in `DEFAULT_NEWS_FEEDS` — so the catalog invariant exempts these entries.
   */
  local?: boolean;
  /** One-line description of what the source contributes. */
  note: string;
}

/**
 * The registry of upstream data sources Investor Eye consumes.
 *
 * Entries only exist for sources the code ACTUALLY consumes — a catalog entry
 * for something nothing calls would be documentation of a fiction. Planned but
 * unwired providers (AIS, ADS-B, OSM, CelesTrak) are intentionally absent; when
 * one lands, its adapter and its entry land together.
 */
export const SOURCE_CATALOG: SourceCatalogEntry[] = [
  {
    id: 'gdelt',
    name: 'GDELT 2.0',
    provider: 'The GDELT Project',
    category: 'geopolitical',
    website: 'https://www.gdeltproject.org/',
    license: 'Open — unrestricted use, citation required',
    licenseUrl: 'https://www.gdeltproject.org/about.html',
    termsUrl: 'https://www.gdeltproject.org/about.html',
    commercialUse: 'yes',
    requiresApiKey: false,
    attributionRequired: true,
    attribution: 'GDELT Project — gdeltproject.org',
    rateLimit: 'Bulk 15-minute export: unlimited; DOC API: throttled (429)',
    dataFreshness: 'minutes',
    note: 'Machine-coded global news events (CAMEO), actors, Goldstein scores, exact action coordinates.',
  },
  {
    id: 'usgs',
    name: 'USGS Earthquakes',
    provider: 'U.S. Geological Survey',
    category: 'hazard',
    website: 'https://earthquake.usgs.gov/',
    license: 'Public domain (U.S. Government work)',
    licenseUrl: 'https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits',
    commercialUse: 'yes',
    requiresApiKey: false,
    attributionRequired: false,
    attribution: 'USGS Earthquake Hazards Program',
    dataFreshness: 'minutes',
    note: 'Geolocated seismic events with magnitude, depth and a per-quake feature id.',
  },
  {
    id: 'news',
    name: 'Market News (JDDS)',
    provider: 'BlackEclipse RSS ingestion',
    category: 'news',
    website: 'https://github.com/anomalyco/opencode',
    // The rows are already stored in JDDS by the app's own news ingester; this
    // entry documents that Investor Eye reads its own database, not a third
    // party. The underlying feeds' terms are recorded where they are declared
    // (`DEFAULT_NEWS_FEEDS` in `lib/settings.ts`).
    license: 'Local data — see each feed in Settings → News Feeds',
    local: true,
    commercialUse: 'unknown',
    requiresApiKey: false,
    attributionRequired: false,
    dataFreshness: 'minutes',
    note: 'Turns the already-ingested RSS corpus into normalized macro/market events. No network call.',
  },
  {
    id: 'firms',
    name: 'NASA FIRMS Active Fire',
    provider: 'NASA LANCE / FIRMS',
    category: 'hazard',
    website: 'https://firms.modaps.eosdis.nasa.gov/',
    license: 'Open — NASA EOSDIS/LANCE, free and unrestricted',
    licenseUrl: 'https://www.earthdata.nasa.gov/data/projects/lance',
    termsUrl: 'https://firms.modaps.eosdis.nasa.gov/',
    commercialUse: 'yes',
    requiresApiKey: false,
    attributionRequired: true,
    attribution: 'NASA FIRMS — fire information for resource management system',
    rateLimit: 'Archive CSVs are unmetered; the Area API needs a free MAP_KEY (not used here)',
    dataFreshness: 'hourly',
    note: 'Near-real-time satellite fire/thermal hotspots (MODIS + VIIRS), aggregated into bounded clusters.',
  },
];

const BY_ID = new Map(SOURCE_CATALOG.map((e) => [e.id, e]));

/** Catalog entry for a source id, or undefined when none was declared. */
export function catalogFor(id: string): SourceCatalogEntry | undefined {
  return BY_ID.get(id);
}

/** True when a source has declared its governance metadata. */
export function hasCatalogEntry(id: string): boolean {
  return BY_ID.has(id);
}

/**
 * Every distinct attribution line the current sources require, deduplicated and
 * in catalog order. The UI renders these so required credit is never lost.
 */
export function requiredAttributions(ids?: string[]): string[] {
  const list = ids && ids.length > 0
    ? ids.map((id) => BY_ID.get(id)).filter((e): e is SourceCatalogEntry => Boolean(e))
    : SOURCE_CATALOG;
  const seen = new Set<string>();
  const out: string[] = [];
  for (const e of list) {
    if (!e.attributionRequired || !e.attribution) continue;
    if (seen.has(e.attribution)) continue;
    seen.add(e.attribution);
    out.push(e.attribution);
  }
  return out;
}

/** Short human label for commercial use, for the Data Sources table. */
export const COMMERCIAL_USE_LABEL: Record<CommercialUse, string> = {
  yes: 'Allowed',
  no: 'Not permitted',
  unknown: 'Verify terms',
};
