// ── English dictionary — navigation domain ──────────────────────────────────
// A DOMAIN slice of the canonical English dictionary, spread into `en` so
// `t('nav.…')` stays autocompleted and type-checked exactly as before. Moving
// a domain here is the documented way the oversized `en.ts` SHRINKS (see the
// ratchet note in `src/lib/size-budget.test.ts`): the keys move, the canonical
// set stays one object. This slice owns the primary navigation labels (the
// sidebar menu, tab launchers and search destinations).

export const navigation = {
  // Navigation (sidebar primary menu)
  'nav.chat': 'ChatBot',
  'nav.home': 'Dashboard',
  'nav.dashboard': 'Command Center',
  'nav.investorEye': 'Investor Eye',
  'nav.marketWorkspace': 'Chart Workspace',
  'nav.discovery': 'Market Discover',
  'nav.portfolio': 'Portfolio',
  'nav.journal': 'Journal',
  'nav.news': 'Market News',
  'nav.earnings': 'Earnings',
  'nav.heatmap': 'Market Bubbles',
  'nav.economics': 'Economics',
  'nav.alerts': 'Price Alerts',
  'nav.skills': 'Skills',
  'nav.sdk': 'Eclipse SDK',
  'nav.memory': 'Eclipse Memory',
  'nav.artifacts': 'Artifacts',
  'nav.tasks': 'Tasks',
  'nav.pages': 'Pages',
  'nav.uiBuilder': 'Capability Studio',
  'nav.backtest': 'Quant Research',
  'nav.strategyStudio': 'Strategy Studio',
  'nav.researchData': 'Research Data',
  'nav.graphStudio': 'Graph Studio',
  'nav.tables': 'Tables',
  'nav.overview': 'Overview',
  'nav.bots': 'Bots',
} as const;
