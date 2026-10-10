// ── Investor Eye — source registry ───────────────────────────────────────────
// Central registry of world-state sources. Mirrors the discipline of
// `lib/connectors/registry.ts` (anchored on `globalThis` so dev HMR cannot
// leave two registries behind) but is additive — it does not join the market
// capability resolver.
//
// A source is a small adapter: `fetch()` gets raw records through the shared
// `safeGet` transport, `normalize()` converts them into the Investor Eye
// vocabulary. Nothing here is provider-specific at the registry level.

import type { EventSource } from '../types';
import { gdeltSource } from './gdelt';
import { usgsSource } from './usgs';
import { newsSource } from './news';
import { firmsSource } from './firms';
import { eonetSource } from './eonet';

const globalForSources = globalThis as unknown as {
  investorEyeSources: Map<string, EventSource> | undefined;
};

const sources: Map<string, EventSource> =
  globalForSources.investorEyeSources ?? new Map<string, EventSource>();

globalForSources.investorEyeSources = sources;

export function registerSource(source: EventSource): void {
  sources.set(source.id, source);
}

export function getSource(id: string): EventSource | undefined {
  return sources.get(id);
}

export function listSources(): EventSource[] {
  return [...sources.values()];
}

/** Sources that can actually run in this environment right now. */
export function configuredSources(): EventSource[] {
  return listSources().filter((s) => s.isConfigured());
}

let registered = false;

/** Register every built-in source (idempotent). */
export function registerBuiltinSources(): void {
  if (registered && sources.size > 0) return;
  registerSource(gdeltSource);
  registerSource(usgsSource);
  // News-derived events: reuses the already-ingested `NewsItem` rows, so this
  // adds real macro/market coverage with no new feed or credentials.
  registerSource(newsSource);
  // Satellite fire detections: keyless global CSV, aggregated into clusters.
  registerSource(firmsSource);
  // Curated multi-hazard natural events: keyless global JSON (storms, floods,
  // volcanoes, droughts, ice, …) — the wide coverage the point-feed hazards miss.
  registerSource(eonetSource);
  registered = true;
}
