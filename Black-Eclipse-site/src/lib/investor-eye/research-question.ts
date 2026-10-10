// ── Investor Eye — event research question ───────────────────────────────────
// Turns a normalized event into a research mandate for the shared Evidence &
// Research Engine. Pure, so the exact text the model receives is a reviewable,
// testable artefact rather than a string built inline in a component — a silent
// change to it would change what the engine searches for.
//
// The mandate asks for EVIDENCE and CORROBORATION, not speculation, and always
// requests dates and contradictions so the engine's answer is checkable.

import type { NormalizedEvent } from './types';

export function eventResearchQuestion(event: NormalizedEvent): string {
  const where = event.placeName ?? (event.countries.length > 0 ? event.countries.join(', ') : 'the reported location');
  const type = event.eventType.replace(/_/g, ' ');
  const actors = (event.actors ?? [])
    .map((a) => a.name)
    .filter(Boolean)
    .slice(0, 4)
    .join(', ');

  const date = (() => {
    const t = Date.parse(event.publishedAt);
    return Number.isNaN(t) ? event.publishedAt : new Date(t).toISOString().slice(0, 10);
  })();

  const parts = [
    `Research mandate: corroborate the ${type} event reported as "${event.title}"`,
    `near ${where} on/around ${date}.`,
    actors ? `Reported actors: ${actors}.` : '',
    `Establish with independent sources what is actually confirmed to have happened, by whom and when,`,
    `and flag any contradictory or unconfirmed reporting.`,
    `Identify the countries, commodities, sectors and publicly traded companies most plausibly exposed,`,
    `and the economic transmission channels (energy, shipping, trade, sanctions, rates) that could carry the impact.`,
    `Cite each finding with its source and date, separate observed facts from inference, and state what remains unknown.`,
  ];
  return parts.filter(Boolean).join(' ').trim();
}
