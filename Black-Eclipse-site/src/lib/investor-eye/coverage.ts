// ── Investor Eye — conflict coverage / gap report ────────────────────────────
// "I can't see the conflicts" has three genuinely different causes and the user
// deserves to know which one they are looking at:
//
//   observed    conflicts WERE fetched and plotted.
//   quiet       every source is healthy but none observed a conflict in the
//               window — an honest zero, not a failure.
//   degraded    one or more sources failed/throttled, so the absence is partly
//               a COVERAGE gap, not evidence that nothing happened.
//   unavailable no event feed at all (we cannot say anything about conflicts).
//
// Pure and deterministic: it only reads the assembled state, so it is unit-
// testable and cannot invent a reason. This is the deterministic half of
// "make conflicts appear" — the AI backfill (Phase 2) builds on this signal.

import type { InvestorEyeState, SourceStatus } from './types';

/** Event types counted as conflict/coercion for coverage purposes. */
const CONFLICT_TYPES = new Set(['conflict', 'military']);

export type CoverageStatus = 'observed' | 'quiet' | 'degraded' | 'unavailable';

export interface CoverageReport {
  status: CoverageStatus;
  /** Conflict/military events present in the window. */
  conflictCount: number;
  totalEvents: number;
  /** Events retained from an earlier cycle (real, within-window). */
  replayedCount: number;
  healthySources: number;
  degradedSourceIds: string[];
  /** One-line, human explanation safe to show in the UI. */
  explanation: string;
}

function isDegraded(s: SourceStatus): boolean {
  return s.state === 'error' || s.state === 'rate_limited' || s.state === 'unavailable';
}

/**
 * Summarize whether the conflict layer is populated and, if not, why.
 *
 * Reads only `events`, `status.sources` and `eventsUnavailable`, so it can run
 * on the client from the same payload the map renders — no second data path.
 */
export function conflictCoverage(
  state: Pick<InvestorEyeState, 'events' | 'status' | 'eventsUnavailable'> | null | undefined,
): CoverageReport {
  const events = state?.events ?? [];
  const sources = state?.status.sources ?? [];
  const healthySources = sources.filter((s) => !isDegraded(s)).length;
  const degradedSourceIds = sources.filter(isDegraded).map((s) => s.id);
  const conflictCount = events.filter((e) => CONFLICT_TYPES.has(e.eventType)).length;
  const replayedCount = events.filter((e) => e.replayed).length;

  if (!state || state.eventsUnavailable) {
    return {
      status: 'unavailable',
      conflictCount,
      totalEvents: events.length,
      replayedCount,
      healthySources,
      degradedSourceIds,
      explanation: 'Event feed unavailable — conflict coverage cannot be assessed.',
    };
  }

  if (conflictCount > 0) {
    return {
      status: 'observed',
      conflictCount,
      totalEvents: events.length,
      replayedCount,
      healthySources,
      degradedSourceIds,
      explanation: `${conflictCount} conflict event${conflictCount === 1 ? '' : 's'} in this window.`,
    };
  }

  if (degradedSourceIds.length > 0) {
    return {
      status: 'degraded',
      conflictCount,
      totalEvents: events.length,
      replayedCount,
      healthySources,
      degradedSourceIds,
      explanation: `No conflicts shown, but ${degradedSourceIds.join(', ')} ${degradedSourceIds.length === 1 ? 'is' : 'are'} degraded — this is a coverage gap, not proof of calm.`,
    };
  }

  return {
    status: 'quiet',
    conflictCount,
    totalEvents: events.length,
    replayedCount,
    healthySources,
    degradedSourceIds,
    explanation: `No conflicts observed in this window across ${healthySources} healthy source${healthySources === 1 ? '' : 's'}.`,
  };
}
