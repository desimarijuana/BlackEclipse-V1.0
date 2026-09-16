// ── Investor Eye tools for the agent (Phase 2.11 — the AI Analyst) ───────────
// Read-only tools that let the research agent answer world-state questions from
// the STRUCTURED Investor Eye data instead of hallucinating. Follows the
// `ToolDefinition` contract in `tools.ts` (same shape as `dataset-tools.ts` and
// `journal-tools.ts`) and is spread into `TOOLS`.
//
// Retrieval pipeline (spec §42):
//   user → intent → object/event/market/relationship retrieval → LLM synthesis
//
// Every result states provenance and separates OBSERVED facts from INFERRED
// links, so the model can cite its evidence and never presents an inference as
// a fact.

import type { ToolDefinition } from './tools';
import { queryEvents, rowToEvent } from '@/lib/investor-eye/state';
import { countryByIso2, resolveCountry } from '@/lib/investor-eye/countries';
import { queryEdges, iso2ForCountryId } from '@/lib/investor-eye/graph-data';
import { buildGraph, neighboursOf } from '@/lib/investor-eye/graph';
import { severityWeight } from '@/lib/investor-eye/classify';
import { prisma } from '@/lib/db';

/** Clamp a tool-provided hour window to a sane range. */
function clampHours(raw: unknown, fallback = 168): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.max(1, Math.min(Math.round(n), 24 * 30));
}

function line(...parts: Array<string | undefined | null>): string {
  return parts.filter((p) => p !== undefined && p !== null && p !== '').join('');
}

/** Query the stored world-state events for a time window / country / type. */
async function getWorldEvents(
  hours: number,
  country: string | undefined,
  eventType: string | undefined,
  severity: string | undefined,
  limit: number,
): Promise<string> {
  const iso2 = country ? (countryByIso2(country)?.iso2 ?? resolveCountry(country)?.iso2) : undefined;
  const events = await queryEvents({ hours, iso2, eventType, severity, limit: Math.min(limit, 60) });

  if (events.length === 0) {
    const filters = [
      iso2 ? `country=${iso2}` : null,
      eventType ? `type=${eventType}` : null,
      severity ? `severity=${severity}` : null,
    ].filter(Boolean).join(', ');
    // A healthy source with zero matches is a real observation, not an error.
    return `No Investor Eye events in the last ${hours}h${filters ? ` matching ${filters}` : ''}. ` +
      `This is an observed empty result from stored events, not a data outage.`;
  }

  const lines = events.map((e) => {
    const channels = e.channels.length ? ` | channels: ${e.channels.join(', ')}` : '';
    const commodities = e.commodities.length ? ` | commodities: ${e.commodities.join(', ')}` : '';
    const sectors = e.sectors.length ? ` | sectors: ${e.sectors.join(', ')}` : '';
    return line(
      `- [${e.publishedAt}] (${e.eventType}/${e.severity}) ${e.title}`,
      e.countries.length ? ` | countries: ${e.countries.join(', ')}` : '',
      channels, commodities, sectors,
      ` | confidence: ${e.confidence.toFixed(2)} | sources: ${e.sourceCount} | primary: ${e.primarySource}`,
    );
  });

  return [
    `Investor Eye events — last ${hours}h${iso2 ? ` in ${iso2}` : ''}${eventType ? `, type ${eventType}` : ''}: ${events.length} event(s).`,
    `Provenance: LIVE (normalized + deduplicated from GDELT/USGS; confidence is data quality, NOT certainty).`,
    '',
    ...lines,
  ].join('\n');
}

/** Country intelligence: stored events + real economic metrics. */
async function getCountryIntelligence(country: string, hours: number): Promise<string> {
  const def = countryByIso2(country) ?? resolveCountry(country);
  if (!def) {
    return `Unknown country "${country}". Use an ISO2 code (e.g. US, PK, TW) or a country name.`;
  }
  const events = await queryEvents({ hours, iso2: def.iso2, limit: 40 });
  const { buildCountryDetail } = await import('@/lib/investor-eye/phase2');
  const detail = await buildCountryDetail(def.iso2);

  const byType = new Map<string, number>();
  for (const e of events) byType.set(e.eventType, (byType.get(e.eventType) ?? 0) + 1);
  const topTypes = [...byType.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);

  const metricLines = detail.metrics.length
    ? detail.metrics.map((m) => `  - ${m.label}: ${m.value}${m.unit}`)
    : ['  (no free public economic series available for this country)'];

  return [
    `${def.name} (${def.iso2})${def.region ? ` — ${def.region}` : ''}`,
    line('Market link: ', def.marketId ?? 'none', def.currency ? ` (${def.currency})` : ''),
    '',
    `Events in the last ${hours}h: ${events.length}`,
    topTypes.length ? `  By type: ${topTypes.map(([t, n]) => `${t} ${n}`).join(', ')}` : '  No events in window.',
    '',
    `Economic metrics (provenance: ${detail.provenance}):`,
    ...metricLines,
    '',
    events.slice(0, 6).map((e) => `- [${e.publishedAt}] (${e.eventType}/${e.severity}) ${e.title}`).join('\n'),
  ].filter((l) => l !== '').join('\n');
}

/** Market observations for the world-state (reuses the existing market path). */
async function getWorldMarkets(): Promise<string> {
  const { assembleState } = await import('@/lib/investor-eye/state');
  const state = await assembleState({ hours: 24 });
  if (state.markets.length === 0) {
    return `No market observations available (provenance: ${state.status.provenance}). ` +
      `The market layer reuses the JDDS index path; an empty result means no cached or live quotes.`;
  }
  const lines = state.markets.map(
    (m) => `- ${m.name} (${m.symbol}): ${m.price.toFixed(2)} ${m.currency ?? ''} ${m.changePct >= 0 ? '+' : ''}${m.changePct.toFixed(2)}% [${m.provenance}]`,
  );
  return [
    `Market observations (provenance: ${state.status.provenance}, updated ${state.status.updatedAt ?? 'n/a'}):`,
    ...lines,
  ].join('\n');
}

/** Relationship graph around an entity, labelled by relation class. */
async function getRelationships(entity: string, kind: string | undefined): Promise<string> {
  const edges = await queryEdges({ limit: 1000 });
  if (edges.length === 0) {
    return `No relationships have been derived yet. The graph is built from ingested events ` +
      `(co-mentions) and stored entity attributes; it is empty until ingestion has run.`;
  }
  const graph = buildGraph(edges, { maxNodes: 400, maxPerKind: { company: 60, security: 30 }, iso2ForCountryId });

  // Resolve which node the caller means: exact id, then case-insensitive name/symbol.
  const needle = entity.trim().toLowerCase();
  const candidates = graph.nodes.filter((n) => {
    if (kind && n.kind !== kind) return false;
    const idPart = n.id.split(':')[1]?.toLowerCase() ?? '';
    return idPart === needle || n.name.toLowerCase() === needle || n.name.toLowerCase().includes(needle);
  });
  if (candidates.length === 0) {
    const kinds = [...new Set(graph.nodes.map((n) => n.kind))].join(', ');
    return `No graph node matches "${entity}"${kind ? ` of kind ${kind}` : ''}. Known node kinds: ${kinds}. ` +
      `Try a country code (US), a company symbol (AAPL), or a commodity (Crude Oil).`;
  }

  const target = candidates.sort((a, b) => b.degree - a.degree)[0];
  const { links } = neighboursOf(graph, target.id);
  if (links.length === 0) {
    return `${target.name} (${target.kind}) has no relationships in the current graph.`;
  }

  const lines = links.slice(0, 25).map((l) => {
    const dir = l.source === target.id ? '→' : '←';
    return `- ${dir} ${l.other?.name ?? '?'} (${l.other?.kind ?? '?'}) — ${l.relations.join('/')} ` +
      `[${l.relationClass.toLowerCase()}] weight ${l.weight.toFixed(2)}`;
  });

  return [
    `Relationships for ${target.name} (${target.kind}), strongest first: ${links.length} edge(s).`,
    `Relation classes: OBSERVED = both endpoints appear in a real source record (or stored attribute); ` +
      `INFERRED = derived by a documented rule. Treat INFERRED links as potential exposure, not fact.`,
    '',
    ...lines,
  ].join('\n');
}

/** Portfolio exposure + intersecting events, from caller-supplied holdings. */
async function getPortfolioExposure(holdingsJson: string): Promise<string> {
  let holdings: Array<{ symbol: string; weight: number; country?: string; sector?: string }> = [];
  try {
    const parsed = JSON.parse(holdingsJson || '[]');
    if (Array.isArray(parsed)) {
      holdings = parsed.map((h) => ({
        symbol: String((h as Record<string, unknown>).symbol ?? ''),
        weight: Number((h as Record<string, unknown>).weight ?? 0),
        country: (h as Record<string, unknown>).country ? String((h as Record<string, unknown>).country).toUpperCase() : undefined,
        sector: (h as Record<string, unknown>).sector ? String((h as Record<string, unknown>).sector) : undefined,
      })).filter((h) => h.symbol && Number.isFinite(h.weight));
    }
  } catch {
    return `Invalid holdings JSON. Pass an array like [{"symbol":"AAPL","weight":0.4,"country":"US","sector":"Technology"}].`;
  }
  if (holdings.length === 0) {
    return `No holdings supplied. Pass an array like [{"symbol":"AAPL","weight":0.4,"country":"US","sector":"Technology"}]. ` +
      `The client portfolio engine owns valuation; this tool only computes exposure from what it is given.`;
  }

  const { computeExposure, portfolioIntersections } = await import('@/lib/investor-eye/analytics');
  const { assembleState } = await import('@/lib/investor-eye/state');
  const exposure = computeExposure(holdings);
  const state = await assembleState({ hours: 168 });
  const intersections = portfolioIntersections(state.events, exposure);

  const countryLines = exposure.countries.slice(0, 10).map((c) => `  - ${c.key}: ${(c.weight * 100).toFixed(1)}%`);
  const sectorLines = exposure.sectors.slice(0, 10).map((s) => `  - ${s.label}: ${(s.weight * 100).toFixed(1)}%`);
  const hitLines = intersections.slice(0, 10).map(
    (x) => `- [${x.event.severity}] ${x.event.title} (exposed ${(x.exposedWeight * 100).toFixed(1)}%; ` +
      `${x.matchedCountries.length ? `countries ${x.matchedCountries.join(',')}` : ''}` +
      `${x.matchedSectors.length ? ` sectors ${x.matchedSectors.join(',')}` : ''})`,
  );

  return [
    `Portfolio exposure (EXPOSURE ONLY — not investment advice or a recommendation):`,
    `Countries:\n${countryLines.join('\n') || '  (none mapped)'}`,
    `Sectors:\n${sectorLines.join('\n') || '  (none mapped)'}`,
    `Unmapped weight: ${(exposure.unmappedWeight * 100).toFixed(1)}%`,
    '',
    `Current events intersecting the portfolio (${intersections.length}), provenance ${state.status.provenance}:`,
    hitLines.join('\n') || '- none',
    '',
    `Intersections are OBSERVED (a held country/sector appears in the event). They are not a prediction.`,
  ].join('\n');
}

/** Risk decomposition with drivers. */
async function getRiskState(hours: number): Promise<string> {
  const { buildRiskState, buildRegionState } = await import('@/lib/investor-eye/analytics');
  const { assembleState } = await import('@/lib/investor-eye/state');
  const state = await assembleState({ hours });
  const components = buildRiskState(state.events);
  const regions = buildRegionState(state.events, state.countries);

  const lines = components.map(
    (c) => `- ${c.label}: ${(c.score * 100).toFixed(0)}/100 (n=${c.sampleSize})` +
      (c.drivers.length ? ` — ${c.drivers.join('; ')}` : ''),
  );
  const regionLines = regions.slice(0, 8).map(
    (r) => `- ${r.region}: ${r.eventCount} event(s), avg severity ${r.avgSeverity.toFixed(2)}${r.topType ? `, top type ${r.topType}` : ''}`,
  );

  return [
    `Investor Eye risk decomposition — last ${hours}h (provenance ${state.status.provenance}).`,
    `These are decomposable event-density measures with their drivers, NOT a market forecast or single score:`,
    ...lines,
    '',
    `By region:`,
    ...regionLines,
  ].join('\n');
}

/** Read one event in full by id or dedupKey. */
async function getEventDetail(id: string): Promise<string> {
  if (!id) return `An event id is required. Use get_world_events first to discover ids.`;
  const row = await prisma.geopoliticalEvent.findFirst({ where: { OR: [{ id }, { dedupKey: id }] } });
  if (!row) return `No event found with id/dedupKey "${id}". Use get_world_events to list current events.`;
  const e = rowToEvent(row);
  return [
    `Event: ${e.title}`,
    `Type: ${e.eventType} | Severity: ${e.severity} | Published: ${e.publishedAt}`,
    `Countries: ${e.countries.join(', ') || 'none'} | Location: ${e.lon ?? '?'},${e.lat ?? '?'}`,
    `Channels: ${e.channels.join(', ') || 'none'}`,
    `Commodities: ${e.commodities.join(', ') || 'none'} | Sectors: ${e.sectors.join(', ') || 'none'}`,
    `Confidence: ${e.confidence.toFixed(2)} (internal data quality, not certainty) | Sources: ${e.sourceCount} | Primary: ${e.primarySource}`,
    e.summary ? `Summary: ${e.summary}` : '',
    e.sources.length ? `Evidence:\n${e.sources.slice(0, 8).map((s) => `  - ${s.name}${s.url ? ` ${s.url}` : ''}`).join('\n')}` : '',
  ].filter(Boolean).join('\n');
}

export const INVESTOR_EYE_TOOLS: ToolDefinition[] = [
  {
    name: 'get_world_events',
    description:
      'Query the normalized global event feed (geopolitical/economic/natural events) for a time window, optionally filtered by country, event type, or severity. Use this FIRST for questions about what is happening in the world. Returns observed events with provenance.',
    parameters: {
      type: 'object',
      properties: {
        hours: { type: 'number', description: 'Look-back window in hours (default 168 = 7 days).' },
        country: { type: 'string', description: 'Optional ISO2 code or country name, e.g. PK, Taiwan.' },
        event_type: {
          type: 'string',
          description: 'Optional type: conflict, military, protest, election, diplomatic, sanction, trade, tariff, cyber, energy, shipping, natural_disaster, monetary, fiscal, regulatory, other.',
        },
        severity: { type: 'string', description: 'Optional severity: low, medium, high, critical.' },
        limit: { type: 'number', description: 'Max events (default 25, max 60).' },
      },
    },
    execute: (a) =>
      getWorldEvents(
        clampHours(a.hours),
        a.country ? String(a.country) : undefined,
        a.event_type ? String(a.event_type) : undefined,
        a.severity ? String(a.severity) : undefined,
        Number.isFinite(Number(a.limit)) ? Number(a.limit) : 25,
      ),
  },
  {
    name: 'get_country_intelligence',
    description:
      'Country intelligence: stored events in a time window plus real free-public economic metrics (inflation, unemployment, GDP, rates). Use for "what is happening in <country>" and macro questions.',
    parameters: {
      type: 'object',
      properties: {
        country: { type: 'string', description: 'ISO2 code or country name, e.g. US, Pakistan, TW.' },
        hours: { type: 'number', description: 'Event look-back window in hours (default 168).' },
      },
      required: ['country'],
    },
    execute: (a) => getCountryIntelligence(String(a.country || ''), clampHours(a.hours)),
  },
  {
    name: 'get_world_markets',
    description:
      'Current market observations for the world-state map (major country indices), with change % and provenance (LIVE vs CACHED). Reuses the existing JDDS index path.',
    parameters: { type: 'object', properties: {} },
    execute: () => getWorldMarkets(),
  },
  {
    name: 'get_event_detail',
    description: 'Fetch one Investor Eye event in full (entities, channels, confidence, source evidence) by its id or dedupKey.',
    parameters: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'Event id or dedupKey from get_world_events.' },
      },
      required: ['id'],
    },
    execute: (a) => getEventDetail(String(a.id || '')),
  },
  {
    name: 'get_relationships',
    description:
      'Explore the relationship graph around an entity (country, company, commodity, sector, market). Each edge is labelled OBSERVED or INFERRED. Use for "how is X connected to Y" and exposure questions.',
    parameters: {
      type: 'object',
      properties: {
        entity: { type: 'string', description: 'Entity to centre on, e.g. US, AAPL, Crude Oil, Technology.' },
        kind: { type: 'string', description: 'Optional node kind filter: country, company, commodity, sector, market.' },
      },
      required: ['entity'],
    },
    execute: (a) => getRelationships(String(a.entity || ''), a.kind ? String(a.kind) : undefined),
  },
  {
    name: 'get_portfolio_exposure',
    description:
      'Compute portfolio exposure (country/sector weights) and the current events intersecting it. Pass the holdings you already know. Returns EXPOSURE only — never advice.',
    parameters: {
      type: 'object',
      properties: {
        holdings: {
          type: 'string',
          description: 'JSON array of holdings: [{"symbol":"AAPL","weight":0.4,"country":"US","sector":"Technology"}].',
        },
      },
      required: ['holdings'],
    },
    execute: (a) => getPortfolioExposure(String(a.holdings || '[]')),
  },
  {
    name: 'get_risk_state',
    description:
      'Decomposable world risk dimensions (conflict, trade, energy, political, shipping, financial, natural) with their drivers and sample sizes, plus a regional breakdown. Not a single score or forecast.',
    parameters: {
      type: 'object',
      properties: {
        hours: { type: 'number', description: 'Look-back window in hours (default 24).' },
      },
    },
    execute: (a) => getRiskState(clampHours(a.hours, 24)),
  },
];

export function getInvestorEyeTool(name: string): ToolDefinition | undefined {
  return INVESTOR_EYE_TOOLS.find((t) => t.name === name);
}

export { severityWeight };
