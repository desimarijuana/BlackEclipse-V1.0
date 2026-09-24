// ── Research provenance presentation model ──────────────────────────────────
// Pure helpers that turn a gated run's `research` blob into the render model for
// the chat "Sources" area. Kept out of the React component so the ordering,
// numbering and merging rules are unit-testable without a DOM — the same
// pattern as `lib/chat/markdown.ts`.
//
// Nothing here invents a field: an absent value stays null/omitted and renders
// as "unknown". Presentation only; the evidence/retrieval logic is untouched.

import type {
  ResearchCitation,
  ResearchCoverageLeg,
  ResearchMetadata,
  ResearchRunInfo,
} from '@/lib/harness/types';

/** Narrow the loosely-typed `Message.research` to a run-info object, or null. */
export function coerceResearchRun(info: unknown): ResearchRunInfo | null {
  if (!info || typeof info !== 'object') return null;
  const candidate = info as ResearchRunInfo;
  if (!candidate.status) return null;
  return candidate;
}

/** A short `YYYY-MM-DD` from an ISO string; null when not a parseable date. */
export function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const day = iso.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null;
}

/** Map each evidence id to its 1-based source number for `[n]` references. */
export function sourceIndexById(citations: ResearchCitation[]): Map<string, number> {
  const map = new Map<string, number>();
  citations.forEach((c, i) => {
    if (c.evidenceId && !map.has(c.evidenceId)) map.set(c.evidenceId, i + 1);
  });
  return map;
}

/** The `[1,2]` markers for a set of evidence ids (unknown ids dropped). */
export function sourceMarkers(ids: string[], index: Map<string, number>): number[] {
  return ids.map((id) => index.get(id)).filter((n): n is number => typeof n === 'number');
}

/**
 * Limitations shown to the user: coverage/validation limitations plus declared
 * missing evidence, de-duplicated. Always visible (never inside the Sources
 * list), so uncertainty survives even when nothing was cited.
 */
export function mergeLimitations(metadata: ResearchMetadata | null | undefined): string[] {
  if (!metadata) return [];
  return Array.from(new Set([...(metadata.limitations ?? []), ...(metadata.missingEvidence ?? [])]));
}

export interface CoverageCounts {
  covered: number;
  unmet: number;
  total: number;
}

/** Covered / unmet leg counts. `not_applicable` legs are excluded from unmet. */
export function coverageCounts(legs: ResearchCoverageLeg[]): CoverageCounts {
  const covered = legs.filter((l) => l.status === 'covered').length;
  const unmet = legs.filter((l) => l.status !== 'covered' && l.status !== 'not_applicable').length;
  return { covered, unmet, total: legs.length };
}

/** True when at least one cited source is a secondary (lower-confidence) source. */
export function hasSecondarySource(citations: ResearchCitation[]): boolean {
  return citations.some((c) => c.sourceType === 'secondary');
}

/** The single line shown on the collapsed panel header (always visible). */
export function summarizeRun(info: ResearchRunInfo): string {
  const legs = info.coverage?.legs ?? [];
  const citations = info.metadata?.citations ?? [];
  const conflicts = info.metadata?.conflicts ?? [];
  const { covered, unmet } = coverageCounts(legs);
  const parts: string[] = [];
  if (legs.length > 0) parts.push(`${covered}/${legs.length} legs covered`);
  if (unmet > 0) parts.push(`${unmet} unmet`);
  if (citations.length > 0) parts.push(`${citations.length} source(s)`);
  if (conflicts.length > 0) parts.push(`${conflicts.length} conflict(s)`);
  return parts.join(' · ');
}
