// ── English dictionary — analysis / computed-result domain (Phase 8/18) ──────
// A DOMAIN slice of the canonical English dictionary, spread into `en` so
// `t('analysis.…')` stays autocompleted and type-checked exactly as before.
// Moving a domain here is the documented way the oversized `en.ts` SHRINKS
// (see the ratchet note in `src/lib/size-budget.test.ts`): the keys move, the
// canonical set stays one object. This slice owns the "worked out by Eclipse"
// language: the computed-vs-retrieved status words, the figure payload lines and
// the honest unavailable/needs-input sentences.

export const analysis = {
  'analysis.computed': 'Worked out by Eclipse',
  'analysis.retrieved': 'From a source',
  'analysis.unavailable': 'This number has no record of where it came from, so Eclipse won’t show it.',
  'analysis.noOutputs': 'Nothing came back from that.',
  'analysis.saved': 'Saved',
  'analysis.notASource': 'This was worked out by Eclipse from the data above — it isn’t a figure from a data source.',
  'analysis.details': 'How Eclipse worked this out',
  'analysis.needsInput': 'I need a bit more to work that out: {what}',
  'analysis.notEnabled': 'Eclipse isn’t set up to work numbers out in this session.',
  'analysis.figureDrawnFrom': 'Drawn from {what}',
  'analysis.figureSeed': 'Seed {seed} — the same seed reproduces this figure.',
} as const;
