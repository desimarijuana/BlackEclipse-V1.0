// ── English dictionary — acquisition / collected-data domain (Phase 16) ─────
// A DOMAIN slice of the canonical English dictionary, spread into `en` so
// `t('acquire.…')` stays autocompleted and type-checked exactly as before.
// Moving a domain here is the documented way the oversized `en.ts` SHRINKS
// (see the ratchet note in `src/lib/size-budget.test.ts`): the keys move, the
// canonical set stays one object. This slice owns the collection manifest's
// user-facing language: what was collected, from where, how complete, and the
// licence/attribution the source requires.

export const acquire = {
  'acquire.title': 'Collected data',
  'acquire.complete': 'Complete',
  'acquire.partial': 'Partial',
  'acquire.purpose': 'Purpose',
  'acquire.source': 'Source',
  'acquire.window': 'Window',
  'acquire.rows': 'Rows',
  'acquire.licence': 'Licence',
  'acquire.attribution': 'Attribution',
  'acquire.partialReason': 'Stopped early: {reason}',
  'acquire.rowsUnknown': 'count unavailable',
} as const;
