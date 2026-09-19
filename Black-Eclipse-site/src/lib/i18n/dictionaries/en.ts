// ── English dictionary (canonical source) ────────────────────────────────────
// Every translatable UI string is declared here first. Keys are flat dot-paths
// so `t('nav.chat')` is autocompleted and type-checked. Other locales provide a
// `Partial` of this shape; any key they omit falls back to the English value.
//
// Scope: interface chrome only (navigation, buttons, settings labels, empty
// states). Never financial data, news, or AI output — those come from the API
// and are not translated here.

export const en = {
  // Navigation (sidebar primary menu)
  'nav.chat': 'ChatBot',
  'nav.dashboard': 'Command Center',
  'nav.investorEye': 'Investor Eye',
  'nav.marketWorkspace': 'Chart Workspace',
  'nav.discovery': 'Market Screener',
  'nav.portfolio': 'Portfolio',
  'nav.journal': 'Journal',
  'nav.news': 'Market News',
  'nav.earnings': 'Earnings',
  'nav.heatmap': 'Market Bubbles',
  'nav.economics': 'Economics',
  'nav.alerts': 'Price Alerts',

  // Common actions & nouns
  'common.settings': 'Settings',
  'common.search': 'Search',
  'common.close': 'Close',
  'common.open': 'Open',
  'common.save': 'Save',
  'common.saved': 'Saved',
  'common.cancel': 'Cancel',
  'common.reset': 'Reset',
  'common.resetDefaults': 'Reset to defaults',
  'common.loading': 'Loading',
  'common.expand': 'Expand',
  'common.collapse': 'Collapse',
  'common.language': 'Language',
  'common.appearance': 'Appearance',
  'common.theme': 'Theme',
  'common.dark': 'Dark',
  'common.light': 'Light',
  'common.timezone': 'Timezone',
  'common.currency': 'Currency',
  'common.market': 'Market',
  'common.enabled': 'Enabled',
  'common.disabled': 'Disabled',
  'common.none': 'None',
  'common.unavailable': 'Unavailable',
  'common.current': 'Current',

  // Top bar
  'topbar.searchPlaceholder': 'Search instruments, indicators, commands…',

  // Sidebar
  'sidebar.chatHistory': 'Chat History',
  'sidebar.newChat': 'New Chat',
  'sidebar.noSessions': 'No active sessions',
  'sidebar.untitledSession': 'Untitled Session',
  'sidebar.terminal': 'Terminal',
  'sidebar.openSettings': 'Open Settings',

  // Settings — General
  'settings.general.title': 'Appearance & Preferences',
  'settings.general.description':
    'Tailor the interface theme, language, default market, currency, timezone and how frequently live data refreshes.',
  'settings.general.languageHint':
    'Translates the interface. Financial data and news stay in their original language.',

  // Settings — Accessibility
  'settings.accessibility.title': 'Accessibility',
  'settings.accessibility.description':
    'Adjust the interface so it works for how you see and navigate.',
  'settings.accessibility.reduceMotion': 'Reduce motion',
  'settings.accessibility.reduceMotionHint': 'Minimize animations and transitions.',
  'settings.accessibility.highContrast': 'High contrast',
  'settings.accessibility.highContrastHint': 'Increase contrast for text and borders.',
  'settings.accessibility.largeText': 'Larger text',
  'settings.accessibility.largeTextHint': 'Increase the base font size across the app.',

  // Accessibility (screen-reader labels)
  'a11y.skipToContent': 'Skip to main content',
  'a11y.mainNavigation': 'Main navigation',
  'a11y.mainContent': 'Main content',
  'a11y.closeMenu': 'Close menu',
  'a11y.openMenu': 'Open menu',

  // Keyboard shortcuts dialog
  'keyboard.title': 'Keyboard shortcuts',
  'keyboard.searchPlaceholder': 'Search actions, keys, or pages',
  'keyboard.noMatches': 'No matching shortcuts.',
  'keyboard.globalGroup': 'Global and chart shortcuts',
  'keyboard.navGroup': 'Sidebar navigation',
} as const;
