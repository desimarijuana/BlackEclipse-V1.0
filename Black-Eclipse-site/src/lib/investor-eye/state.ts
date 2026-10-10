// ── Investor Eye — state assembly & ingestion ────────────────────────────────
// The server-side brain. It:
//   1. runs every configured source (partial failure is normal — see below),
//   2. normalizes + clusters + dedupes the results into one event feed,
//   3. joins country entities and the EXISTING market data (/api/indices data
//      shape) onto the state,
//   4. computes honest provenance,
//   5. caches the assembled state and records a SourceRun per source.
//
// Failure policy (spec §14/§50): a source that fails does NOT take down the
// feed. If every event source fails, the feed is UNAVAILABLE — never an
// invented "0 events". If at least one source succeeds, the feed is LIVE (or
// CACHED/HISTORICAL) and the failed sources are reported in `status.sources`.

import { prisma, yieldToEventLoop } from '@/lib/db';
import { fetchYahooBatchQuote } from '@/lib/scraper/fetchers/yfinance';
import { toMarketId, marketDisplayName, currencyFor } from '@/lib/markets';
import { registerBuiltinSources, configuredSources, listSources } from './sources/registry';
import { clusterEvents } from './cluster';
import { collapseDuplicateKeys } from './dedup';
import { breakerCanAttempt, breakerRecordFailure, breakerRecordSuccess, breakerSnapshot } from './circuit-breaker';
import { reResolveEventLocation } from './geo-resolve';
import { aggregatePoints, zoomForCount } from './geo';
import { countryByIso2, COUNTRIES, resolveCountry } from './countries';
import { SEVERITY_RANK } from './classify';
import {
  clearCache, clearInflight, getCachedState, getInflight, isAssembling, isCacheFresh,
  loadPersistedState, persistState, setCachedState, setInflight,
} from './cache';
import type {
  CountrySummary, DataStatus, EventSeverity, InvestorEyeState, MarketObservation,
  NormalizedEvent, Provenance, SourceRunSummary, SourceStatus,
} from './types';

/** Index universes — MUST match `/api/indices` so the market layer is the same
 *  data, not a second market system. Kept to capital-market countries. */
const MARKET_INDEX: Record<string, { symbol: string; name: string }> = {
  US: { symbol: '^GSPC', name: 'S&P 500' },
  CA: { symbol: '^GSPTSE', name: 'S&P/TSX' },
  MX: { symbol: '^MXX', name: 'IPC Mexico' },
  BR: { symbol: '^BVSP', name: 'Ibovespa' },
  UK: { symbol: '^FTSE', name: 'FTSE 100' },
  DE: { symbol: '^GDAXI', name: 'DAX' },
  FR: { symbol: '^FCHI', name: 'CAC 40' },
  NL: { symbol: '^AEX', name: 'AEX' },
  JP: { symbol: '^N225', name: 'Nikkei 225' },
  KR: { symbol: '^KS11', name: 'KOSPI' },
  CN: { symbol: '000001.SS', name: 'Shanghai Composite' },
  HK: { symbol: '^HSI', name: 'Hang Seng' },
  TW: { symbol: '^TWII', name: 'TAIEX' },
  SG: { symbol: '^STI', name: 'Straits Times' },
  MY: { symbol: '^KLSE', name: 'FTSE Bursa KLCI' },
  AU: { symbol: '^AXJO', name: 'S&P/ASX 200' },
  IN: { symbol: '^NSEI', name: 'Nifty 50' },
  PK: { symbol: '^KSE100', name: 'KSE-100' },
  ID: { symbol: '^JKSE', name: 'Jakarta Composite' },
  TH: { symbol: '^SET.BK', name: 'SET Index' },
  VN: { symbol: '^VNINDEX', name: 'VN Index' },
  SA: { symbol: '^TASI.SR', name: 'Tadawul' },
  AE: { symbol: '^DFMGI', name: 'DFM General' },
  ZA: { symbol: '^JALSH', name: 'JSE All Share' },
  EG: { symbol: '^EGX30', name: 'EGX 30' },
  NG: { symbol: '^NGXALLSH', name: 'NGX All Share' },
  RU: { symbol: '^IMOEX.ME', name: 'MOEX Russia' },
  TR: { symbol: '^XU100', name: 'BIST 100' },
};

const WINDOW_HOURS_DEFAULT = 24;

export interface AssembleOptions {
  hours?: number;
  /** Skip the cache and rebuild (used by the refresh endpoint / cron). */
  force?: boolean;
  maxRecordsPerSource?: number;
}

// The in-flight guard lives in the shared cache module (anchored on
// `globalThis`) so every route bundle sees the same one — see cache.ts.
export { isAssembling };

// ── Source runs ──────────────────────────────────────────────────────────────

async function recordRun(summary: SourceRunSummary): Promise<void> {
  try {
    await prisma.sourceRun.create({
      data: {
        source: summary.source,
        startedAt: new Date(summary.startedAt),
        finishedAt: new Date(summary.finishedAt),
        status: summary.status ?? (summary.error ? 'error' : summary.recordsAccepted > 0 ? 'ok' : 'empty'),
        recordsReceived: summary.recordsReceived,
        recordsAccepted: summary.recordsAccepted,
        recordsRejected: summary.recordsRejected,
        error: summary.error?.slice(0, 400),
        latencyMs: summary.durationMs,
      },
    });
  } catch {
    /* observability is best-effort */
  }
}

/** Run one source and return { events, summary }. Never throws. */
async function runSource(
  source: ReturnType<typeof configuredSources>[number],
  hours: number,
  maxRecords?: number,
): Promise<{ events: NormalizedEvent[]; summary: SourceRunSummary }> {
  const startedAt = new Date().toISOString();
  const started = Date.now();
  // Circuit breaker: a source with several consecutive failures is skipped for a
  // cooldown so a deterministically-down provider cannot cost its full timeout
  // on every cycle. The skip is reported with the real reason — never as a
  // healthy-but-quiet source.
  if (!breakerCanAttempt(source.id)) {
    const snap = breakerSnapshot(source.id);
    return {
      events: [],
      summary: {
        source: source.id, startedAt, finishedAt: new Date().toISOString(),
        durationMs: 0, recordsReceived: 0, recordsAccepted: 0, recordsRejected: 0,
        error: `circuit open — ${snap.failures} consecutive failures; retry in ${Math.ceil(snap.retryAfterMs / 1000)}s`,
        status: 'error',
        provenance: 'UNAVAILABLE',
      },
    };
  }
  try {
    const raw = await source.fetch({ hours, maxRecords });
    const received = raw.length;
    let events: NormalizedEvent[] = [];
    try {
      events = source.normalize(raw);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      breakerRecordFailure(source.id);
      return {
        events: [],
        summary: {
          source: source.id, startedAt, finishedAt: new Date().toISOString(),
          durationMs: Date.now() - started, recordsReceived: received,
          recordsAccepted: 0, recordsRejected: received, error: `normalize: ${message}`,
          status: 'error',
          provenance: 'UNAVAILABLE',
        },
      };
    }
    // Fetch + normalize succeeded (an honest empty result counts).
    breakerRecordSuccess(source.id);
    const accepted = events.length;
    // A source may AGGREGATE: FIRMS ships one CSV batch that `normalize`
    // expands into hundreds of clusters, so accepted can exceed received. A
    // negative "rejected" is nonsense, so it is clamped rather than reported.
    const rejected = Math.max(0, received - accepted);
    return {
      events,
      summary: {
        source: source.id, startedAt, finishedAt: new Date().toISOString(),
        durationMs: Date.now() - started, recordsReceived: received,
        recordsAccepted: accepted, recordsRejected: rejected,
        status: accepted > 0 ? 'ok' : 'empty',
        provenance: accepted > 0 ? 'LIVE' : 'UNAVAILABLE',
      },
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // A source may classify its own failures; currently only a genuine upstream
    // throttle is treated as distinct from an error (so it is not reported as a
    // broken integration).
    const rateLimited = err instanceof Error && err.name === 'RateLimited';
    // A throttle is upstream pressure, not proof the integration is broken, but
    // it still warrants backing off — the breaker counts both so a provider that
    // is hammering us does not get retried at full rate every cycle.
    breakerRecordFailure(source.id);
    return {
      events: [],
      summary: {
        source: source.id, startedAt, finishedAt: new Date().toISOString(),
        durationMs: Date.now() - started, recordsReceived: 0,
        recordsAccepted: 0, recordsRejected: 0, error: message,
        status: rateLimited ? 'rate_limited' : 'error',
        provenance: 'UNAVAILABLE',
      },
    };
  }
}

// ── Market observations (reuse the existing scraper bridge) ──────────────────

/**
 * Pull index quotes for capital-market countries. Reuses the same yfinance
 * bridge and cached `IndexQuote` rows as `/api/indices` — this is NOT a second
 * market-data system. Yahoo failures degrade to JDDS cache, then UNAVAILABLE.
 */
export async function buildMarketObservations(): Promise<{ markets: MarketObservation[]; provenance: Provenance }> {
  const entries = Object.entries(MARKET_INDEX).map(([iso2, idx]) => ({ iso2, ...idx }));
  const symbols = entries.map((e) => e.symbol);

  let liveBySymbol = new Map<string, { price: number; changePct: number }>();
  let provenance: Provenance = 'UNAVAILABLE';
  try {
    const results = await fetchYahooBatchQuote(symbols, 'US');
    for (const r of results) {
      if (r.status === 'ok' && r.quote && r.quote.price > 0) {
        liveBySymbol.set(r.quote.symbol, { price: r.quote.price, changePct: r.quote.changePct });
      }
    }
    if (liveBySymbol.size > 0) provenance = 'LIVE';
  } catch {
    liveBySymbol = new Map();
  }

  // JDDS cache fallback: every market that has an IndexQuote row.
  const cached = await prisma.indexQuote.findMany();
  const cacheByKey = new Map(cached.map((c) => [`${c.marketId}:${c.symbol}`, c]));

  const markets: MarketObservation[] = [];
  for (const e of entries) {
    const marketId = toMarketId(e.iso2);
    const live = liveBySymbol.get(e.symbol);
    const c = cacheByKey.get(`${marketId}:${e.symbol}`) ?? cacheByKey.get(`US:${e.symbol}`);
    const price = live?.price ?? c?.price ?? 0;
    const changePct = live?.changePct ?? c?.changePct ?? 0;
    if (price <= 0) continue; // never emit a zero-price observation
    const obsProvenance: Provenance = live ? 'LIVE' : 'CACHED';
    if (provenance === 'UNAVAILABLE' && obsProvenance === 'CACHED') provenance = 'CACHED';
    markets.push({
      marketId,
      iso2: e.iso2,
      name: marketDisplayName(marketId),
      symbol: e.name,
      price,
      changePct,
      currency: currencyFor(marketId),
      provenance: obsProvenance,
      updatedAt: live ? new Date().toISOString() : c?.updatedAt?.toISOString(),
    });
  }
  return { markets, provenance };
}

// ── Country aggregation ──────────────────────────────────────────────────────

export function buildCountrySummaries(
  events: NormalizedEvent[],
  markets: MarketObservation[],
): CountrySummary[] {
  const marketsByIso = new Map<string, MarketObservation[]>();
  for (const m of markets) {
    if (!m.iso2) continue;
    const arr = marketsByIso.get(m.iso2) ?? [];
    arr.push(m);
    marketsByIso.set(m.iso2, arr);
  }

  const byIso = new Map<string, { count: number; last: string }>();
  for (const e of events) {
    for (const iso2 of e.countries) {
      const cur = byIso.get(iso2) ?? { count: 0, last: e.publishedAt };
      cur.count++;
      if (Date.parse(e.publishedAt) > Date.parse(cur.last)) cur.last = e.publishedAt;
      byIso.set(iso2, cur);
    }
  }

  // Include every country that has either events or a market, but never
  // fabricate an entry for a country with neither.
  const out: CountrySummary[] = [];
  for (const def of COUNTRIES) {
    const agg = byIso.get(def.iso2);
    const mkts = marketsByIso.get(def.iso2) ?? [];
    if (!agg && mkts.length === 0) continue;
    out.push({
      iso2: def.iso2,
      iso3: def.iso3,
      name: def.name,
      region: def.region,
      lon: def.lon,
      lat: def.lat,
      eventCount: agg?.count ?? 0,
      lastEventAt: agg?.last,
      markets: mkts,
    });
  }
  // Highest activity first.
  return out.sort((a, b) => b.eventCount - a.eventCount || a.name.localeCompare(b.name));
}

// ── Status ───────────────────────────────────────────────────────────────────

function buildStatus(
  runs: SourceRunSummary[],
  eventsProvenance: Provenance,
  lastKnownAt: string | null,
  updatedAt: string | null,
): DataStatus {
  const registered = listSources();
  const sources: SourceStatus[] = registered.map((s) => {
    const run = runs.find((r) => r.source === s.id);
    const state: SourceStatus['state'] = s.requiresCredentials
      ? 'optional'
      : !run
        ? 'configured'
        : run.status === 'rate_limited'
          ? 'rate_limited'
          : run.error
            ? 'error'
            : 'available';
    return {
      id: s.id,
      name: s.name,
      capabilities: [...s.capabilities],
      requiresCredentials: s.requiresCredentials,
      state,
      lastSuccess: run && !run.error ? run.finishedAt : undefined,
      lastError: run?.error,
      latencyMs: run?.durationMs,
      recordsLastRun: run?.recordsAccepted,
    };
  });

  return {
    provenance: eventsProvenance,
    updatedAt,
    label: freshnessLabel(eventsProvenance, updatedAt, lastKnownAt),
    sources,
  };
}

function freshnessLabel(provenance: Provenance, updatedAt: string | null, lastKnownAt: string | null): string {
  if (provenance === 'UNAVAILABLE') {
    return lastKnownAt ? `DATA UNAVAILABLE · LAST KNOWN ${formatUtc(lastKnownAt)}` : 'DATA UNAVAILABLE';
  }
  if (!updatedAt) return provenance;
  const ageSec = Math.max(0, Math.round((Date.now() - Date.parse(updatedAt)) / 1000));
  if (ageSec < 90) return `UPDATED ${ageSec}s AGO`;
  const mins = Math.round(ageSec / 60);
  if (mins < 60) return `UPDATED ${mins}m AGO`;
  return `${provenance} · ${formatUtc(updatedAt)}`;
}

export function formatUtc(iso: string): string {
  try {
    const d = new Date(iso);
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${hh}:${mm} UTC`;
  } catch {
    return iso;
  }
}

// ── Assembly ─────────────────────────────────────────────────────────────────

/**
 * Assemble the current world state. Cached per window; pass `force` to rebuild.
 * Always returns a usable state object — never throws.
 *
 * Concurrency (important): the cache and the in-flight promise live on
 * `globalThis` (see cache.ts). Next evaluates each route in its own module
 * instance, so without sharing, every endpoint would cold-run the full source
 * ingestion on its own. Here a second caller for the SAME window awaits the
 * first assembly's promise; a caller for a DIFFERENT window starts its own
 * (windows are genuinely different payloads).
 */
/**
 * Assemble (or serve) the world state for a window.
 *
 * TRUE stale-while-revalidate. A cold assembly measures ~15–18s (GDELT bulk +
 * news + USGS + markets), and the previous implementation AWAITED it even when a
 * perfectly good previous state existed — so the first paint of the map was
 * "DATA UNAVAILABLE" for the whole build, then flipped to LIVE. That is the
 * flapping this function exists to prevent.
 *
 * Order of preference:
 *   1. a fresh cache entry            → return it (milliseconds)
 *   2. a stale cache entry            → return it NOW, rebuild in the background
 *   3. the persisted last-known state → return it NOW, rebuild in the background
 *   4. nothing at all                 → await the build (genuine first run)
 *
 * Any state served by 2/3 is labelled CACHED and flagged `refreshing`, so the UI
 * can say "last known" honestly instead of pretending it is live. The rebuild
 * populates the cache, and the client's next poll picks it up.
 */
export async function assembleState(options: AssembleOptions = {}): Promise<InvestorEyeState> {
  const hours = options.hours ?? WINDOW_HOURS_DEFAULT;

  if (!options.force && isCacheFresh(hours)) {
    const cached = getCachedState(hours);
    if (cached) return cached;
  }

  const inflight = getInflight(hours);
  const stale = getCachedState(hours);

  const startBackground = () => {
    if (getInflight(hours)) return;
    const promise = runAssembly(hours, options);
    setInflight(hours, promise);
    promise
      .catch((err) => console.error('[investor-eye] background rebuild failed:', err))
      .finally(() => clearInflight(hours));
  };

  // An explicit `refresh=1` is the caller ASKING to wait for a rebuild — the
  // refresh button would otherwise appear to do nothing. `force` therefore
  // bypasses the stale-serve paths and genuinely awaits the assembly.
  if (options.force) {
    if (inflight) return inflight;
    const promise = runAssembly(hours, options);
    setInflight(hours, promise);
    try {
      return await promise;
    } finally {
      clearInflight(hours);
    }
  }

  if (stale) {
    startBackground();
    return { ...stale, refreshing: true, status: { ...stale.status, provenance: 'CACHED' } };
  }

  if (!inflight) {
    // No in-memory cache at all. Seed from the persisted snapshot so a cold
    // start / restart is instant rather than a 17s blank map.
    const persisted = await loadPersistedState();
    if (persisted) {
      startBackground();
      return {
        ...persisted,
        windowHours: hours,
        refreshing: true,
        status: { ...persisted.status, provenance: 'CACHED' },
      };
    }
  }

  if (inflight) return inflight;

  const promise = runAssembly(hours, options);
  setInflight(hours, promise);
  try {
    return await promise;
  } finally {
    clearInflight(hours);
  }
}

/** The actual assembly. Only ever entered once per window at a time. */
async function runAssembly(hours: number, options: AssembleOptions): Promise<InvestorEyeState> {
  try {
    registerBuiltinSources();
    const sources = configuredSources();

    const runs: SourceRunSummary[] = [];
    const allEvents: NormalizedEvent[] = [];
    for (const source of sources) {
      const { events, summary } = await runSource(source, hours, options.maxRecordsPerSource);
      runs.push(summary);
      allEvents.push(...events);
      await yieldToEventLoop();
    }
    await Promise.all(runs.map((r) => recordRun(r)));

    // A rate-limited source is NOT a healthy one: it produced nothing and told
    // us why. Only genuinely-successful runs count as "succeeded" here.
    const succeeded = runs.filter((r) => !r.error);
    const anyEventsReceived = runs.some((r) => r.recordsReceived > 0);
    const allThrottled = runs.length > 0 && runs.every((r) => r.status === 'rate_limited');

    // Dedupe + cluster the merged feed (stable ordering → stable dedup keys).
    allEvents.sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt));
    let clustered = clusterEvents(allEvents).filter((e) => {
      // Enforce the requested time window after clustering (a cluster's
      // earliest member can drift outside it).
      const ageHours = (Date.now() - Date.parse(e.publishedAt)) / 36e5;
      return ageHours <= hours + 1;
    });

    // Defensive: clustering can leave two records that share a `dedupKey` (the
    // key is also the DB unique constraint, so they would render as duplicate
    // React children and one row would overwrite the other on upsert). Collapse
    // them, keeping the higher-signal record.
    clustered = collapseDuplicateKeys(clustered);

    // Attach REAL headlines where the ingested news corpus already has the
    // article. GDELT has no headline of its own, so without this a GDELT event
    // can only show its actors. Best-effort: a miss leaves the field null.
    try {
      const { enrichEventsWithHeadlines, applyHeadlineEnrichment } = await import('./enrich');
      const matches = await enrichEventsWithHeadlines(clustered);
      clustered = applyHeadlineEnrichment(clustered, matches);
    } catch (err) {
      console.warn('[investor-eye] headline enrichment unavailable:', err instanceof Error ? err.message : err);
    }

    // Persist clustered events (idempotent upsert on dedupKey).
    await persistEvents(clustered);

    // Market observations come from the EXISTING data path.
    const { markets, provenance: marketProvenance } = await buildMarketObservations();
    const countries = buildCountrySummaries(clustered, markets);

    // Warm the candle cache for the index universe so historical analogues have
    // real series to read (Phase 4.3).
    //
    // DELIBERATELY FIRE-AND-FORGET: a full backfill measured ~170s (30 markets
    // × the Python bridge). Awaiting it here blocked the very first world-state
    // response, so the map rendered "0 events / DATA UNAVAILABLE" while the
    // request was still in flight. The map must never wait on optional history;
    // it appears on the next cycle (or via POST /api/investor-eye/history).
    void (async () => {
      try {
        const { historyStatus, backfillMarketHistory } = await import('./history');
        const status = await historyStatus();
        const thin = status.filter((s) => s.bars < 30);
        if (thin.length < Math.ceil(status.length / 2)) return;
        const result = await backfillMarketHistory({ symbols: thin.map((s) => s.symbol) });
        if (result.written > 0) console.log(`[investor-eye] history backfill wrote ${result.written} bars`);
      } catch (err) {
        console.warn('[investor-eye] history backfill skipped:', err instanceof Error ? err.message : err);
      }
    })();

    // Rebuild the relationship graph (spec §41). Best-effort — a graph failure
    // must never break the world state. Company nodes come from the JDDS Asset
    // universe via the Phase 2 builder.
    try {
      const { refreshGraph } = await import('./graph-data');
      const { buildCompanies } = await import('./phase2');
      const companies = await buildCompanies(120);
      await refreshGraph({ events: clustered, countries, markets, companies });
    } catch (err) {
      console.warn('[investor-eye] graph rebuild skipped:', err instanceof Error ? err.message : err);
    }

    // Provenance: events available if ANY source succeeded (even with zero
    // observed events — zero can be a real observation). A total throttle/failure
    // with no data → UNAVAILABLE, with last-known from the cache. Note a
    // throttled source must not be laundered into "healthy but quiet": if every
    // source was throttled we have no basis for claiming the feed is empty.
    let eventsProvenance: Provenance;
    if (anyEventsReceived || clustered.length > 0) eventsProvenance = 'LIVE';
    else if (succeeded.length > 0 && !allThrottled) eventsProvenance = 'LIVE'; // healthy but quiet
    else if (marketProvenance !== 'UNAVAILABLE') eventsProvenance = marketProvenance;
    else eventsProvenance = 'UNAVAILABLE';

    const updatedAt = new Date().toISOString();
    const previous = getCachedState(hours) ?? (await loadPersistedState());
    const lastKnownAt = previous?.generatedAt ?? null;

    let state: InvestorEyeState = {
      generatedAt: updatedAt,
      windowHours: hours,
      events: clustered,
      countries,
      markets,
      status: buildStatus(runs, eventsProvenance, lastKnownAt, updatedAt),
      eventsUnavailable: eventsProvenance === 'UNAVAILABLE',
      lastKnownAt: eventsProvenance === 'UNAVAILABLE' ? lastKnownAt : null,
    };

    // A total outage: keep the last known state but relabel it honestly.
    if (eventsProvenance === 'UNAVAILABLE' && previous) {
      state = {
        ...previous,
        generatedAt: updatedAt,
        windowHours: hours,
        status: { ...buildStatus(runs, 'UNAVAILABLE', previous.generatedAt, previous.generatedAt) },
        eventsUnavailable: true,
        lastKnownAt: previous.generatedAt,
      };
      setCachedState(state, hours);
      return state;
    }

    setCachedState(state, hours);
    if (eventsProvenance !== 'UNAVAILABLE') await persistState(state);
    return state;
  } catch (err) {
    console.error('[investor-eye] assembleState failed:', err);
    const previous = getCachedState(hours) ?? (await loadPersistedState());
    if (previous) {
      return {
        ...previous,
        eventsUnavailable: false,
        status: { ...previous.status, provenance: 'CACHED' },
      };
    }
    return emptyState(hours, 'UNAVAILABLE', null);
  }
}

function emptyState(hours: number, provenance: Provenance, lastKnownAt: string | null): InvestorEyeState {
  return {
    generatedAt: new Date().toISOString(),
    windowHours: hours,
    events: [],
    countries: [],
    markets: [],
    status: {
      provenance,
      updatedAt: null,
      label: lastKnownAt ? `DATA UNAVAILABLE · LAST KNOWN ${formatUtc(lastKnownAt)}` : 'DATA UNAVAILABLE',
      sources: listSources().map((s) => ({
        id: s.id, name: s.name, capabilities: [...s.capabilities],
        requiresCredentials: s.requiresCredentials, state: 'unavailable' as const,
      })),
    },
    eventsUnavailable: true,
    lastKnownAt,
  };
}

/** Upsert clustered events into JDDS. Idempotent on `dedupKey`. */
export async function persistEvents(events: NormalizedEvent[]): Promise<{ written: number }> {
  let written = 0;
  for (const e of events) {
    try {
      const data = {
        title: e.title,
        summary: e.summary,
        headline: e.headline ?? null,
        description: e.description ?? null,
        actors: JSON.stringify(e.actors ?? []),
        providerCodes: JSON.stringify(e.providerCodes ?? {}),
        placeName: e.placeName ?? null,
        geoMethod: e.geoMethod ?? null,
        eventType: e.eventType,
        category: e.category ?? null,
        severity: e.severity,
        channels: JSON.stringify(e.channels),
        commodities: JSON.stringify(e.commodities),
        sectors: JSON.stringify(e.sectors),
        securities: JSON.stringify(e.securities),
        countries: JSON.stringify(e.countries),
        lon: e.lon,
        lat: e.lat,
        confidence: e.confidence,
        relevance: e.relevance ?? 0,
        relevanceReasons: JSON.stringify(e.relevanceReasons ?? []),
        sourceCount: e.sourceCount,
        sources: JSON.stringify(e.sources),
        primarySource: e.primarySource,
        publishedAt: new Date(e.publishedAt),
        status: 'active',
      };
      const row = await prisma.geopoliticalEvent.upsert({
        where: { dedupKey: e.dedupKey },
        update: data,
        create: { dedupKey: e.dedupKey, ...data },
        select: { id: true },
      });
      // Backfill the row id onto the in-memory event. Without this the state
      // payload has no `id`, so anything keyed by it (the entity links endpoint,
      // the detail route) would fall back to the dedupKey and 404 whenever the
      // row was not persisted under that key.
      e.id = row.id;
      written++;
    } catch (err) {
      // One bad row must not abort the batch.
      console.warn('[investor-eye] persist event failed:', err instanceof Error ? err.message : err);
    }
    if (written % 25 === 0) await yieldToEventLoop();
  }
  return { written };
}

// ── Read helpers (DB-backed) ─────────────────────────────────────────────────

function parseJsonArray(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

/** Map a Prisma event row to the API/UI shape. Shared by the routes. */
export function rowToEvent(row: {
  id: string; dedupKey: string; title: string; summary: string | null;
  headline?: string | null; description?: string | null;
  actors?: string | null; providerCodes?: string | null;
  placeName?: string | null; geoMethod?: string | null;
  eventType: string; category?: string | null; severity: string; channels: string; commodities: string;
  sectors: string; securities: string; countries: string; lon: number | null;
  lat: number | null; confidence: number; relevance?: number; relevanceReasons?: string;
  sourceCount: number; sources: string;
  primarySource: string; publishedAt: Date; firstSeen: Date; lastUpdated: Date;
  status: string;
}): NormalizedEvent {
  let sources: NormalizedEvent['sources'] = [];
  try {
    const parsed = JSON.parse(row.sources);
    if (Array.isArray(parsed)) sources = parsed;
  } catch { /* leave empty */ }
  let actors: NormalizedEvent['actors'];
  try {
    const parsed = JSON.parse(row.actors ?? '[]');
    if (Array.isArray(parsed) && parsed.length > 0) actors = parsed;
  } catch { /* leave undefined */ }
  let providerCodes: NormalizedEvent['providerCodes'];
  try {
    const parsed = JSON.parse(row.providerCodes ?? '{}');
    if (parsed && typeof parsed === 'object' && Object.keys(parsed).length > 0) providerCodes = parsed;
  } catch { /* leave undefined */ }
  return {
    id: row.id,
    dedupKey: row.dedupKey,
    title: row.title,
    summary: row.summary ?? undefined,
    headline: row.headline ?? undefined,
    description: row.description ?? undefined,
    actors,
    providerCodes,
    placeName: row.placeName ?? undefined,
    geoMethod: (row.geoMethod as NormalizedEvent['geoMethod']) ?? undefined,
    eventType: row.eventType as NormalizedEvent['eventType'],
    category: row.category ?? undefined,
    severity: row.severity as EventSeverity,
    channels: parseJsonArray(row.channels),
    commodities: parseJsonArray(row.commodities),
    sectors: parseJsonArray(row.sectors),
    securities: parseJsonArray(row.securities),
    countries: parseJsonArray(row.countries),
    lon: row.lon ?? undefined,
    lat: row.lat ?? undefined,
    confidence: row.confidence,
    relevance: row.relevance ?? undefined,
    relevanceReasons: parseJsonArray(row.relevanceReasons),
    sourceCount: row.sourceCount,
    sources,
    primarySource: row.primarySource,
    publishedAt: row.publishedAt.toISOString(),
    firstSeen: row.firstSeen.toISOString(),
    lastUpdated: row.lastUpdated.toISOString(),
    status: row.status as 'active' | 'archived',
  };
}

/** Query persisted events with an optional time window / country filter. */
export async function queryEvents(options: {
  hours?: number;
  iso2?: string;
  eventType?: string;
  severity?: string;
  limit?: number;
} = {}): Promise<NormalizedEvent[]> {
  const hours = options.hours ?? WINDOW_HOURS_DEFAULT;
  const since = new Date(Date.now() - hours * 36e5);
  const rows = await prisma.geopoliticalEvent.findMany({
    where: {
      publishedAt: { gte: since },
      ...(options.eventType ? { eventType: options.eventType } : {}),
      ...(options.severity ? { severity: options.severity } : {}),
    },
    // Rank by investor relevance, then recency. Relevance is what makes the
    // feed useful (a well-corroborated local incident is still noise); recency
    // breaks ties so the newest of equally-relevant events leads.
    orderBy: [{ relevance: 'desc' }, { publishedAt: 'desc' }],
    take: options.limit ?? 800,
  });
  let events = rows.map(rowToEvent).map(upgradeEventLocation);
  if (options.iso2) {
    const iso = options.iso2.toUpperCase();
    events = events.filter((e) => e.countries.includes(iso));
  }
  return events;
}

/**
 * Re-derive an event's anchor with the CURRENT geo rules.
 *
 * Rows persisted before `capital` existed keep a stale centroid + `geoMethod`.
 * Resolution is deterministic and cheap, so it is recomputed on read rather than
 * migrated — this is what upgrades historical rows without touching the database.
 */
export function upgradeEventLocation(event: NormalizedEvent): NormalizedEvent {
  const resolved = reResolveEventLocation(event);
  if (
    resolved.lon === event.lon &&
    resolved.lat === event.lat &&
    resolved.geoMethod === event.geoMethod
  ) {
    return event;
  }
  return {
    ...event,
    lon: resolved.lon ?? event.lon,
    lat: resolved.lat ?? event.lat,
    placeName: resolved.placeName ?? event.placeName,
    geoMethod: resolved.geoMethod ?? event.geoMethod,
  };
}

/** Recent source runs for the Data Health panel. */
export async function recentSourceRuns(limit = 40): Promise<SourceRunSummary[]> {
  const rows = await prisma.sourceRun.findMany({ orderBy: { startedAt: 'desc' }, take: limit });
  return rows.map((r) => ({
    source: r.source,
    startedAt: r.startedAt.toISOString(),
    finishedAt: r.finishedAt?.toISOString() ?? r.startedAt.toISOString(),
    durationMs: r.latencyMs ?? 0,
    recordsReceived: r.recordsReceived,
    recordsAccepted: r.recordsAccepted,
    recordsRejected: r.recordsRejected,
    error: r.error ?? undefined,
    status: r.status as SourceRunSummary['status'],
    provenance: r.status === 'ok' ? 'LIVE' : r.status === 'empty' ? 'LIVE' : 'UNAVAILABLE',
  }));
}

/** Re-export so callers don't import two modules. */
export { getCachedState, loadPersistedState, setCachedState, clearCache };
export { aggregatePoints, zoomForCount, countryByIso2, resolveCountry, SEVERITY_RANK };
