// ── Investor Eye — relationship graph data (Phase 2.10) ──────────────────────
// Turns normalized events + country/market/company entities into persisted
// `Relationship` edges (and `EventEntity` links), then reads them back for the
// graph endpoint.
//
// Everything derived here is labelled honestly:
//   OBSERVED   both endpoints appear together in one real source record, or the
//              link is stored data (a company's sector / HQ country)
//   INFERRED   produced by an explicit rule rather than co-occurrence
//
// This module is the only writer of `Relationship` / `EventEntity`.

import { prisma, yieldToEventLoop } from '@/lib/db';
import { countryByIso2, COUNTRIES, resolveCountry } from './countries';
import { severityWeight } from './classify';
import type {
  CountrySummary, MarketObservation, NormalizedEvent, Provenance, RelationshipEdge,
} from './types';

// Bounds so a single event with many entities cannot explode the edge count.
const MAX_COUNTRIES_PER_EVENT = 5;
const MAX_COMMODITIES_PER_EVENT = 4;
const MAX_SECTORS_PER_EVENT = 4;

function edgeKey(
  fromKind: string, fromId: string, relation: string, toKind: string, toId: string,
): string {
  // Deterministic + direction-preserving so re-ingestion upserts.
  return `${fromKind}:${fromId}|${relation}|${toKind}:${toId}`;
}

interface EdgeAccumulator {
  key: string;
  fromKind: string; fromId: string; fromName: string;
  toKind: string; toId: string; toName: string;
  relation: string; relationClass: RelationshipEdge['relationClass'];
  weight: number;
  evidence: RelationshipEdge['evidence'];
}

/**
 * Derive relationship edges from a window of events. Pure — no DB.
 *
 * Co-occurrence edges are OBSERVED because both endpoints genuinely appear in
 * the same source text; the *meaning* of the pairing is not claimed.
 */
export function deriveEventEdges(events: NormalizedEvent[]): RelationshipEdge[] {
  const acc = new Map<string, EdgeAccumulator>();

  const add = (
    fromKind: string, fromId: string, fromName: string,
    relation: string, relationClass: RelationshipEdge['relationClass'],
    toKind: string, toId: string, toName: string,
    weight: number, eventId?: string,
  ) => {
    const key = edgeKey(fromKind, fromId, relation, toKind, toId);
    const existing = acc.get(key);
    if (existing) {
      existing.weight += weight;
      if (existing.evidence.length < 5 && eventId && !existing.evidence.some((e) => e.eventId === eventId)) {
        existing.evidence.push({ eventId, note: 'co-mentioned in event' });
      }
      return;
    }
    acc.set(key, {
      key,
      fromKind, fromId, fromName,
      toKind, toId, toName,
      relation, relationClass,
      weight,
      evidence: eventId ? [{ eventId, note: 'co-mentioned in event' }] : [],
    });
  };

  for (const e of events) {
    const weight = severityWeight(e.severity);
    const countries = e.countries
      .map((iso) => countryByIso2(iso))
      .filter((c): c is NonNullable<typeof c> => Boolean(c))
      .slice(0, MAX_COUNTRIES_PER_EVENT);

    // Country ↔ Country: both named in the same event.
    for (let i = 0; i < countries.length; i++) {
      for (let j = i + 1; j < countries.length; j++) {
        add('country', countries[i].iso2, countries[i].name, 'co_mentioned', 'OBSERVED',
          'country', countries[j].iso2, countries[j].name, weight, e.id ?? e.dedupKey);
      }
    }

    // Country → Commodity / Sector: the event ties the country to the channel.
    for (const c of countries) {
      for (const commodity of e.commodities.slice(0, MAX_COMMODITIES_PER_EVENT)) {
        add('country', c.iso2, c.name, 'exposed_to', 'OBSERVED',
          'commodity', commodity, commodity, weight, e.id ?? e.dedupKey);
      }
      for (const sector of e.sectors.slice(0, MAX_SECTORS_PER_EVENT)) {
        add('country', c.iso2, c.name, 'exposed_to', 'OBSERVED',
          'sector', sector, sector, weight, e.id ?? e.dedupKey);
      }
    }

    // Country → Market: the country where the event occurred has an index.
    // Stored linkage (MARKET_INDEX) → OBSERVED.
    for (const c of countries) {
      if (!c.marketId) continue;
      add('country', c.iso2, c.name, 'has_market', 'OBSERVED',
        'market', c.marketId, c.marketId, weight * 0.5, e.id ?? e.dedupKey);
    }
  }

  return [...acc.values()].map((a) => ({
    edgeKey: a.key,
    fromKind: a.fromKind, fromId: a.fromId, fromName: a.fromName,
    toKind: a.toKind, toId: a.toId, toName: a.toName,
    relation: a.relation,
    relationClass: a.relationClass,
    weight: Number(a.weight.toFixed(3)),
    evidence: a.evidence,
    provenance: 'LIVE' as Provenance,
  }));
}

/**
 * Derive structural edges from stored entities: a company's sector and HQ
 * country, and a country's market. These are stored data, so OBSERVED.
 */
export function deriveStructuralEdges(
  companies: Array<{ symbol: string; name: string; iso2: string; sector?: string }>,
  markets: MarketObservation[],
): RelationshipEdge[] {
  const acc = new Map<string, RelationshipEdge>();

  const add = (
    fromKind: string, fromId: string, fromName: string,
    relation: string, toKind: string, toId: string, toName: string, weight: number,
  ) => {
    const key = edgeKey(fromKind, fromId, relation, toKind, toId);
    if (acc.has(key)) return;
    acc.set(key, {
      edgeKey: key,
      fromKind, fromId, fromName,
      toKind, toId, toName,
      relation,
      relationClass: 'OBSERVED',
      weight,
      evidence: [{ note: 'stored entity attribute' }],
      provenance: 'LIVE',
    });
  };

  for (const co of companies) {
    if (co.sector) add('company', co.symbol, co.name, 'part_of', 'sector', co.sector, co.sector, 1);
    const country = countryByIso2(co.iso2);
    if (country) {
      add('company', co.symbol, co.name, 'headquartered_in', 'country', country.iso2, country.name, 1);
    }
  }

  for (const m of markets) {
    if (!m.iso2) continue;
    const country = countryByIso2(m.iso2);
    if (!country) continue;
    add('country', country.iso2, country.name, 'has_market', 'market', m.marketId, m.symbol, 0.5);
  }

  return [...acc.values()];
}

// ── Persistence ─────────────────────────────────────────────────────────────

/** Upsert edges into JDDS. Idempotent on `edgeKey`. */
export async function persistEdges(edges: RelationshipEdge[]): Promise<{ written: number }> {
  let written = 0;
  for (const e of edges) {
    try {
      const data = {
        fromKind: e.fromKind, fromId: e.fromId, fromName: e.fromName,
        toKind: e.toKind, toId: e.toId, toName: e.toName,
        relation: e.relation,
        relationClass: e.relationClass,
        weight: e.weight,
        evidence: JSON.stringify(e.evidence),
        provenance: e.provenance,
        lastSeen: new Date(),
      };
      await prisma.relationship.upsert({
        where: { edgeKey: e.edgeKey },
        update: data,
        create: { edgeKey: e.edgeKey, ...data },
      });
      written++;
    } catch (err) {
      console.warn('[investor-eye] persist edge failed:', err instanceof Error ? err.message : err);
    }
    if (written % 50 === 0) await yieldToEventLoop();
  }
  return { written };
}

/**
 * Write `EventEntity` links so events become queryable by entity. Best-effort.
 * Country entities also upsert into the `Country` table so the join target
 * exists.
 */
export async function persistEventEntities(events: NormalizedEvent[]): Promise<{ written: number }> {
  let written = 0;
  for (const e of events) {
    if (!e.id) continue; // must be a persisted row
    const refs: Array<{ kind: string; entityId: string; name: string; lon?: number; lat?: number }> = [];
    for (const iso of e.countries) {
      const c = countryByIso2(iso);
      if (!c) continue;
      refs.push({ kind: 'country', entityId: c.iso2, name: c.name, lon: c.lon, lat: c.lat });
    }
    for (const commodity of e.commodities) refs.push({ kind: 'commodity', entityId: commodity, name: commodity });
    for (const sector of e.sectors) refs.push({ kind: 'sector', entityId: sector, name: sector });
    for (const security of e.securities) refs.push({ kind: 'security', entityId: security, name: security });

    for (const ref of refs) {
      try {
        // Deterministic per (event, kind, entity) — delete-then-create keeps it
        // idempotent without a dedicated unique constraint.
        const existing = await prisma.eventEntity.findFirst({
          where: { eventId: e.id, kind: ref.kind, entityId: ref.entityId },
          select: { id: true },
        });
        if (existing) continue;
        await prisma.eventEntity.create({
          data: {
            eventId: e.id,
            kind: ref.kind,
            entityId: ref.entityId,
            name: ref.name,
            lon: ref.lon,
            lat: ref.lat,
          },
        });
        written++;
      } catch (err) {
        console.warn('[investor-eye] persist event entity failed:', err instanceof Error ? err.message : err);
      }
    }
    if (written % 50 === 0) await yieldToEventLoop();
  }
  return { written };
}

/** Upsert the canonical `Country` rows referenced by the current state. */
export async function persistCountries(isos: string[]): Promise<number> {
  let written = 0;
  for (const iso of isos) {
    const c = countryByIso2(iso);
    if (!c) continue;
    try {
      await prisma.country.upsert({
        where: { iso2: c.iso2 },
        update: {
          iso3: c.iso3, name: c.name, mapName: c.mapName ?? c.name,
          region: c.region, lon: c.lon, lat: c.lat,
          marketId: c.marketId, currency: c.currency,
          aliases: JSON.stringify(c.aliases ?? []),
        },
        create: {
          iso2: c.iso2, iso3: c.iso3, name: c.name, mapName: c.mapName ?? c.name,
          region: c.region, lon: c.lon, lat: c.lat,
          marketId: c.marketId, currency: c.currency,
          aliases: JSON.stringify(c.aliases ?? []),
        },
      });
      written++;
    } catch {
      /* best-effort */
    }
  }
  return written;
}

// ── Read helpers ────────────────────────────────────────────────────────────

function parseEvidence(raw: string | null): RelationshipEdge['evidence'] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Read stored edges, optionally filtered. */
export async function queryEdges(
  options: { kinds?: string[]; minWeight?: number; limit?: number } = {},
): Promise<RelationshipEdge[]> {
  const rows = await prisma.relationship.findMany({
    where: options.minWeight !== undefined ? { weight: { gte: options.minWeight } } : {},
    orderBy: { weight: 'desc' },
    take: options.limit ?? 1500,
  });
  return rows.map((r) => ({
    edgeKey: r.edgeKey,
    fromKind: r.fromKind, fromId: r.fromId, fromName: r.fromName,
    toKind: r.toKind, toId: r.toId, toName: r.toName,
    relation: r.relation,
    relationClass: r.relationClass as RelationshipEdge['relationClass'],
    weight: r.weight,
    evidence: parseEvidence(r.evidence),
    provenance: r.provenance as Provenance,
    lastSeen: r.lastSeen.toISOString(),
  }));
}

/**
 * Rebuild the persisted graph from a finished ingestion cycle. Bounded and
 * best-effort: a failure here must never break the world state.
 */
export async function refreshGraph(inputs: {
  events: NormalizedEvent[];
  countries: CountrySummary[];
  markets: MarketObservation[];
  companies?: Array<{ symbol: string; name: string; iso2: string; sector?: string }>;
}): Promise<{ edges: number; entities: number; countries: number }> {
  try {
    const eventEdges = deriveEventEdges(inputs.events);
    const structuralEdges = deriveStructuralEdges(inputs.companies ?? [], inputs.markets);
    const countries = await persistCountries(inputs.countries.map((c) => c.iso2));
    // Re-read event ids (persistEvents ran before this) so EventEntity rows can
    // reference real rows.
    const persisted = await prisma.geopoliticalEvent.findMany({
      where: { dedupKey: { in: inputs.events.map((e) => e.dedupKey) } },
      select: { id: true, dedupKey: true },
    });
    const idByKey = new Map(persisted.map((p) => [p.dedupKey, p.id]));
    const withIds = inputs.events.map((e) => ({ ...e, id: idByKey.get(e.dedupKey) ?? e.id }));
    const entities = await persistEventEntities(withIds);
    const edgeResult = await persistEdges([...eventEdges, ...structuralEdges]);
    return { edges: edgeResult.written, entities: entities.written, countries };
  } catch (err) {
    console.warn('[investor-eye] graph refresh failed:', err instanceof Error ? err.message : err);
    return { edges: 0, entities: 0, countries: 0 };
  }
}

/** ISO2 resolver for `buildGraph` (accepts a code or a name). */
export function iso2ForCountryId(id: string): string | undefined {
  return countryByIso2(id)?.iso2 ?? resolveCountry(id)?.iso2 ?? (COUNTRIES.some((c) => c.iso2 === id) ? id : undefined);
}
