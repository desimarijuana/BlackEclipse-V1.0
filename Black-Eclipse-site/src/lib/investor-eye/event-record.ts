// ── Investor Eye — event record → analyst prompt ─────────────────────────────
// Renders ONE event as a compact, factual briefing for the AI analyst.
//
// Why this is its own module: the route handler should stay thin, and the SHAPE
// of what the model receives is a correctness concern — if actors, provenance or
// the location-precision line silently disappear, the analyst starts guessing.
// Pure and unit-tested for that reason.
//
// Rules mirrored here:
//   - absent fields are OMITTED, never printed as a placeholder that could read
//     as data ("Location: —" invites the model to fill the gap);
//   - the location precision is always stated, so the model cannot imply more
//     accuracy than we have;
//   - "derived" is marked on text-inferred channels/commodities/sectors, so the
//     model separates observation from inference.

import { GEO_METHOD_LABEL } from './geo-resolve';
import { actorTypeLabel } from './cameo';
import type { NormalizedEvent } from './types';

/** Render an event as a plain-text briefing for the analyst. */
export function formatEventRecord(event: NormalizedEvent): string {
  const lines: string[] = [
    `Title: ${event.headline ?? event.title}`,
    `Type: ${event.eventType} | Severity: ${event.severity}`,
    `First detected: ${event.publishedAt}`,
  ];

  if (event.placeName) lines.push(`Location: ${event.placeName}`);
  if (event.geoMethod) lines.push(`Location precision: ${GEO_METHOD_LABEL[event.geoMethod]}`);
  if (typeof event.lat === 'number' && typeof event.lon === 'number') {
    lines.push(`Coordinates: ${event.lat.toFixed(3)}, ${event.lon.toFixed(3)}`);
  }
  if (event.countries.length) lines.push(`Countries (ISO2): ${event.countries.join(', ')}`);

  if (event.actors?.length) {
    lines.push(
      `Actors: ${event.actors
        .map((a) => {
          const type = actorTypeLabel(a.typeCode);
          return `${a.name}${type ? ` [${type}]` : ''}${a.countryCode ? ` (${a.countryCode})` : ''}`;
        })
        .join('; ')}`,
    );
  }

  if (event.providerCodes?.cameoRoot) lines.push(`CAMEO root: ${event.providerCodes.cameoRoot}`);
  if (event.providerCodes?.goldstein !== undefined) lines.push(`Goldstein: ${event.providerCodes.goldstein}`);

  if (event.channels.length) lines.push(`Economic channels (derived from text): ${event.channels.join(', ')}`);
  if (event.commodities.length) lines.push(`Commodities (derived): ${event.commodities.join(', ')}`);
  if (event.sectors.length) lines.push(`Sectors (derived): ${event.sectors.join(', ')}`);

  if (event.relevance !== undefined) lines.push(`Investor relevance: ${Math.round(event.relevance * 100)}%`);
  if (event.relevanceReasons?.length) lines.push(`Relevance reasons: ${event.relevanceReasons.join(', ')}`);

  lines.push(`Confidence (data quality, NOT certainty): ${event.confidence}`);
  lines.push(`Sources: ${event.sources.map((s) => s.name).join(', ') || 'none captured'}`);
  if (event.description) lines.push(`Description: ${event.description}`);

  return lines.join('\n');
}

/**
 * The analyst's system prompt. Encodes the same honesty rules the world research
 * agent uses: label inference, quote provenance, and never invent.
 */
export const EXPLAIN_SYSTEM_PROMPT = `You are the Investor Eye analyst. You explain ONE specific world event and
how it could transmit to markets, using the structured record supplied plus the tools available.

Rules, without exception:
- Use the tools to gather context (get_world_events for related/nearby events,
  get_country_intelligence for the affected country, get_world_markets for index observations,
  get_risk_state for decomposable risk, get_event_detail for entity links). Prefer calling a
  tool over asserting something.
- Separate OBSERVED facts from INFERRED exposure. Any link you infer must be labelled "potential"
  or "could affect" - never stated as causal.
- Quote the provenance the tools return (LIVE / CACHED / HISTORICAL / UNAVAILABLE).
- If the record or a tool has no data, say it is unavailable. NEVER invent an event, a number,
  a headline, or a source.
- Confidence is internal data quality, not the probability an event is true. Say so if you cite it.

Answer in this shape, concisely:
1. What happened - one or two sentences, only what the record supports.
2. Who is involved - from the actors, if present.
3. Why it could matter - the economic channels, each marked potential.
4. Market context - only observations the tools actually return, with provenance.
5. What is uncertain - explicitly name the gaps.`;

/** The per-event user prompt. */
export function explainPromptFor(event: NormalizedEvent): string {
  return `Explain this event and its potential market relevance.\n\nEVENT RECORD\n${formatEventRecord(event)}`;
}
