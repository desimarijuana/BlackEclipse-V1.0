// ── Fired-alert event diffing ──────────────────────────────────────────────
// Pure helper for the global alert-notification provider. The live feed
// (GET /api/alerts/live) returns the most recent events newest-first, capped at
// 50 (`take: 50`), so an id-only "last seen" check can re-announce an event once
// it scrolls out of the window. This tracks a bounded set of already-seen ids
// instead, so a notification fires exactly once per event.
//
// Kept framework-free and pure so it can be unit-tested without a DOM.

export interface LiveAlertEvent {
  id: string;
  alertId?: string;
  detail?: string;
}

/** How many recent ids to remember. Comfortably larger than the feed's 50. */
export const SEEN_CAP = 200;

/**
 * Given the newest-first event list and the ids already seen, return the events
 * that are genuinely new — oldest-first, so notifications appear in the order
 * they fired — plus the updated bounded seen-set.
 */
export function selectNewEvents(
  events: LiveAlertEvent[],
  seen: Set<string>,
): { fresh: LiveAlertEvent[]; seen: Set<string> } {
  const next = new Set(seen);
  const fresh: LiveAlertEvent[] = [];
  for (const e of events) {
    if (!e?.id) continue;
    if (!next.has(e.id)) {
      next.add(e.id);
      fresh.push(e);
    }
  }
  // `events` is newest-first, so `fresh` is newest-first too; reverse for
  // chronological order.
  fresh.reverse();
  return { fresh, seen: prune(next) };
}

/** Seed the seen-set from a full feed (used on first poll — notify nothing). */
export function seedSeen(events: LiveAlertEvent[], seen: Set<string> = new Set()): Set<string> {
  const next = new Set(seen);
  for (const e of events) if (e?.id) next.add(e.id);
  return prune(next);
}

/** Keep the set bounded; Sets preserve insertion order, so drop the oldest. */
function prune(seen: Set<string>): Set<string> {
  if (seen.size <= SEEN_CAP) return seen;
  const overflow = seen.size - SEEN_CAP;
  let i = 0;
  for (const id of seen) {
    if (i++ >= overflow) break;
    seen.delete(id);
  }
  return seen;
}
