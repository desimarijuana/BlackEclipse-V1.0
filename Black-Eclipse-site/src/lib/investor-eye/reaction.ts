// ── Investor Eye — observed price reaction ───────────────────────────────────
// "What did the market actually do after this event?" — the one question that
// turns an exposure *claim* into an observation.
//
// This is deliberately NOT a model and NOT a prediction. It measures the real
// stored close series around an event's timestamp and reports the window
// returns, plus the sample it was computed from. If there are no stored candles
// covering the window the result is UNAVAILABLE, never a zero or a guess.
//
// Pure: the caller supplies the series (see `phase2.loadPriceHistory`), so this
// is unit-testable with no DB or network.

import type { Provenance } from './types';

/** A normalised daily close. `date` is YYYY-MM-DD (UTC). */
export interface PricePoint {
  date: string;
  value: number;
}

/**
 * Return horizons, in trading days after the event. `1d` = the first close at
 * or after the event, which is the conventional "next session" reaction.
 */
export const REACTION_WINDOWS = [1, 5, 20] as const;
export type ReactionWindow = (typeof REACTION_WINDOWS)[number];

export interface ReactionMeasure {
  window: ReactionWindow;
  /** Percent change from the pre-event baseline close to the horizon close. */
  changePct: number;
  /** The dates actually compared (so the UI never implies more precision). */
  from: string;
  to: string;
}

export interface PriceReaction {
  symbol: string;
  /** Close immediately before the event (the baseline), if one exists. */
  baseline: { date: string; value: number } | null;
  measures: ReactionMeasure[];
  /**
   * Largest absolute move across the measured windows, so a caller can rank
   * events by market impact without re-deriving it.
   */
  maxAbsChangePct: number | null;
  /** Trading days of series available AFTER the event (drives honesty text). */
  daysAfter: number;
  availability: Provenance;
  note: string;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Parse an event timestamp to a UTC day key, tolerant of ISO or date-only. */
export function eventDay(publishedAt: string): string | null {
  const t = Date.parse(publishedAt);
  if (Number.isNaN(t)) return null;
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * Measure the price reaction around `eventDate` from a daily close series.
 *
 * `series` must be ascending by date. Points are matched by UTC day, and the
 * baseline is the last close STRICTLY BEFORE the event day (an event that
 * prints after the close should be compared against that same close, which is
 * what "last close before the event" means in practice).
 */
export function computePriceReaction(
  symbol: string,
  eventDate: string,
  series: PricePoint[],
): PriceReaction {
  const empty = (note: string, availability: Provenance = 'UNAVAILABLE'): PriceReaction => ({
    symbol,
    baseline: null,
    measures: [],
    maxAbsChangePct: null,
    daysAfter: 0,
    availability,
    note,
  });

  if (!series || series.length === 0) return empty('No stored price history for this instrument.');
  const day = eventDay(eventDate);
  if (!day) return empty('Event timestamp could not be parsed.');

  // Ascending, de-duplicated by day (the last write for a day wins).
  const byDay = new Map<string, number>();
  for (const p of series) {
    if (!p?.date || !Number.isFinite(p.value)) continue;
    byDay.set(p.date.slice(0, 10), p.value);
  }
  const days = [...byDay.keys()].sort();
  if (days.length === 0) return empty('No stored price history for this instrument.');

  const after = days.filter((d) => d > day);
  const baselineDay = [...days].reverse().find((d) => d <= day) ?? null;
  if (!baselineDay) {
    return empty('No close on or before the event — history starts later.', 'UNAVAILABLE');
  }
  const baselineValue = byDay.get(baselineDay)!;

  const measures: ReactionMeasure[] = [];
  for (const w of REACTION_WINDOWS) {
    // Index into the post-event days; the last available close satisfies a
    // window longer than the data (flagged via `daysAfter`).
    const idx = Math.min(w, after.length) - 1;
    if (idx < 0) continue;
    const toDay = after[idx];
    const toValue = byDay.get(toDay)!;
    if (!Number.isFinite(toValue) || baselineValue === 0) continue;
    // Round to 3dp: enough to see a real move, short enough not to imply precision.
    measures.push({
      window: w,
      changePct: Math.round(((toValue - baselineValue) / baselineValue) * 100000) / 1000,
      from: baselineDay,
      to: toDay,
    });
  }

  const maxAbsChangePct = measures.length
    ? Math.max(...measures.map((m) => Math.abs(m.changePct)))
    : null;

  const note = after.length === 0
    ? 'The event is more recent than the latest stored close — reaction not yet measurable.'
    : measures.length < REACTION_WINDOWS.length
      ? 'Only part of the reaction window is covered by stored history.'
      : 'Observed close-to-close moves. Descriptive, not predictive, and not adjusted for other news.';

  return {
    symbol,
    baseline: { date: baselineDay, value: baselineValue },
    measures,
    maxAbsChangePct,
    daysAfter: after.length,
    availability: measures.length > 0 ? 'HISTORICAL' : 'UNAVAILABLE',
    note,
  };
}

/** Human label for a horizon, used in the UI and tests. */
export function reactionWindowLabel(w: ReactionWindow): string {
  return w === 1 ? '+1 session' : `+${w} sessions`;
}

/** Days between two day keys (UTC), for sanity checks in tests. */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY_MS);
}
