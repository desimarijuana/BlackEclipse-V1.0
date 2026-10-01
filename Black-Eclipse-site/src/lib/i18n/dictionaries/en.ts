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
  'nav.skills': 'Skills',
  'nav.memory': 'Eclipse Memory',

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
  'sidebar.agentic': 'Agentic',
  'sidebar.modeSwitcher': 'Menu mode',
  'sidebar.openSettings': 'Open Settings',
  'sidebar.modeTerminalShortcut': 'Switch menu to Terminal',
  'sidebar.modeAgenticShortcut': 'Switch menu to Agentic',

  // Settings — General
  'settings.general.title': 'Appearance & Preferences',
  'settings.general.description':
    'Tailor the interface theme, default market, currency, timezone and how frequently live data refreshes.',
  'settings.general.languageHint':
    'Translates the interface. Financial data and news stay in their original language.',

  // Settings — Customization (language + accessibility)
  'settings.customization.title': 'Customization',
  'settings.customization.description':
    'Make the interface yours — choose your language and tune motion, contrast and text size for how you see and navigate.',
  'settings.customization.language': 'Language',
  'settings.customization.languageHint':
    'Financial data and news stay in their original language.',
  'settings.accessibility.title': 'Accessibility',
  'settings.accessibility.description':
    'Adjust the interface so it works for how you see and navigate.',
  'settings.accessibility.reduceMotion': 'Reduce motion',
  'settings.accessibility.reduceMotionHint': 'Minimize animations and transitions across the app.',
  'settings.accessibility.highContrast': 'High contrast',
  'settings.accessibility.highContrastHint': 'Increase contrast for text and borders to improve legibility.',
  'settings.accessibility.largeText': 'Larger text',
  'settings.accessibility.largeTextHint': 'Increase the base font size throughout the interface.',
  'settings.accessibility.reset': 'Reset accessibility',

  // Accessibility (screen-reader labels)
  'a11y.skipToContent': 'Skip to main content',
  'a11y.mainNavigation': 'Main navigation',
  'a11y.mainContent': 'Main content',
  'a11y.closeMenu': 'Close menu',
  'a11y.openMenu': 'Open menu',

  // Repository navigator (read-only task surface) — names the finance JOB,
  // never the mechanism. The refusal sentences are keyed by the machine code.
  'task.navigator.title': 'Look through the project',
  'task.navigator.description':
    'Find a file, read a passage, or search the project’s notes and documents. Read-only — nothing is changed.',
  'task.navigator.emptyQuery': 'Ask something about the project to get started.',
  'task.navigator.found': 'Found {count} passage(s).',
  'task.navigator.noMatches': 'No matches were found for that.',
  'task.navigator.reading': 'Reading {name}…',
  'task.navigator.citation': 'From {path}:{line}',

  // Authoring a change (Phase 2) — progress and result lines name the TASK,
  // never the mechanism (no "patch", "diff", "worktree", "sandbox").
  'task.authoring.working': 'Writing the change…',
  'task.authoring.checking': 'Checking it works…',
  'task.authoring.done': 'Done. I made the change in your project and saved a copy of what changed.',
  'task.authoring.doneCount': 'Done. I changed {count} file(s) in your project.',
  'task.authoring.seeChanges': 'See what changed',
  'task.authoring.undo': 'Undo this change',
  'task.authoring.undone': 'Undone — your project is back to how it was.',

  // Refusals — one plain sentence per machine code, plus a shared details label.
  // The code itself is never shown as the primary message; it belongs behind
  // the details affordance.
  'refusal.details': 'Show details',
  'refusal.PROTECTED_PATH':
    'I couldn’t read that because it holds Eclipse’s own private data, so I left it alone.',
  'refusal.PATH_TRAVERSAL':
    'I couldn’t look there because it points outside the project, so I left it alone.',
  'refusal.PATH_OUTSIDE_WORKSPACE':
    'I couldn’t look there because it is outside the project, so I left it alone.',
  'refusal.SYMLINK_ESCAPE':
    'I couldn’t look there because it leads outside the project, so I left it alone.',
  'refusal.IGNORED_PATH':
    'I skipped that because it is generated automatically and not meant to be read by hand.',
  'refusal.NOT_FOUND': 'I couldn’t find that, so there was nothing to read.',
  'refusal.BINARY_FILE':
    'I couldn’t read that because it isn’t readable text, so I left it alone.',
  'refusal.TOO_LARGE': 'That is too large for me to read in one go.',
  'refusal.WORKSPACE_UNAVAILABLE':
    'I don’t have a project folder to look through right now, so I can’t answer that.',
  'refusal.INVALID_PATTERN':
    'I couldn’t run that search because the wording wasn’t something I could look for.',

  // Refusals for authoring a change (Phase 2) — one plain sentence each, no
  // mechanism word. Keyed by the machine code for the details affordance.
  'refusal.PATCH_PATH_ABSOLUTE':
    'I didn’t make that change because it points outside your project, so I left everything alone.',
  'refusal.PATCH_PATH_TRAVERSAL':
    'I didn’t make that change because it points above your project folder, so I left everything alone.',
  'refusal.PATCH_PATH_SYMLINK':
    'I didn’t make that change because it leads outside your project, so I left everything alone.',
  'refusal.PATCH_PROTECTED_PATH':
    'I didn’t change that file because it holds private account data, so I left it alone.',
  'refusal.PATCH_OUTSIDE_SCOPE':
    'I didn’t make that change because it reaches beyond the part you asked me to work on.',
  'refusal.PATCH_BASE_MISMATCH':
    'I didn’t make that change because the file changed since I read it — ask me to look again.',
  'refusal.PATCH_TOO_LARGE': 'I didn’t make that change because it is too big to do safely at once.',
  'refusal.PATCH_SPAN_NOT_FOUND':
    'I didn’t make that change because the text I meant to replace is no longer there.',
  'refusal.PATCH_SPAN_AMBIGUOUS':
    'I didn’t make that change because the text I meant to replace appears in more than one place, so I couldn’t tell which you meant.',
  'refusal.PATCH_FILE_EXISTS':
    'I didn’t make that change because a file with that name is already there.',
  'refusal.PATCH_FILE_MISSING':
    'I didn’t make that change because the file I meant to change is no longer there.',
  'refusal.PATCH_MALFORMED':
    'I didn’t make that change because I couldn’t understand the request.',
  'refusal.PATCH_UNKNOWN_OP':
    'I didn’t make that change because it asked for something I can’t do.',
  'refusal.PATCH_TOO_MANY_OPERATIONS':
    'I didn’t make that change because it asked for too many separate edits at once.',
  'refusal.PROFILE_DENIED':
    'I’m not set up to change files in this session, so I left everything alone.',
  'refusal.WORKSPACE_UNBOUND':
    'I don’t have a project folder to change right now, so I couldn’t do that.',
  'refusal.UNKNOWN_WORKSPACE':
    'I couldn’t find a work area to make or undo that change, so I left everything alone.',

  // Keyboard shortcuts dialog
  'keyboard.title': 'Keyboard shortcuts',
  'keyboard.searchPlaceholder': 'Search actions, keys, or pages',
  'keyboard.noMatches': 'No matching shortcuts.',
  'keyboard.globalGroup': 'Global and chart shortcuts',
  'keyboard.navGroup': 'Sidebar navigation',
} as const;
