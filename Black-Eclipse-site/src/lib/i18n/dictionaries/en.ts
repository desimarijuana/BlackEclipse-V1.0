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

  // Running checks (Phase 3) — names the job, never the command.
  'task.check.working': 'Checking the numbers…',
  'task.check.running': 'Running the checks…',
  'task.check.passed': 'The checks passed.',
  'task.check.failed': 'The checks found something to fix.',
  'task.check.timedOut': 'That check took too long, so I stopped it.',
  'task.check.truncated': 'That check produced a lot of output; I kept the beginning.',

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

  // Running-checks refusals (Phase 3) — one plain sentence + a next step.
  'refusal.COMMAND_NOT_ALLOWLISTED':
    'That isn’t a check I’m allowed to run. I can run a check for you instead — tests, types, lint, a build, or a quick look at the project’s history.',
  'refusal.COMMAND_NOT_ENABLED':
    'I’m not allowed to add software to the project in this session, so I left it alone.',
  'refusal.COMMAND_EXECUTABLE_MISSING':
    'The tool I’d need for that check isn’t installed on this computer, so I couldn’t run it.',
  'refusal.COMMAND_ARG_INVALID':
    'I couldn’t run that check because one of the details I was given wasn’t something I could use.',
  'refusal.SANDBOX_UNAVAILABLE':
    'I can’t run checks safely on this computer right now, so I won’t run them.',
  'refusal.COMMAND_REFUSED':
    'I didn’t run that check because it isn’t one I’m allowed to run.',

  // Proof it works (Phase 4) — the verification panel. Names the job, never the
  // mechanism (no "exit code", "digest", "verification ledger"); the technical
  // reason sits behind the "details" affordance.
  'code.proof.title': 'Proof it works',
  'code.proof.checks': '{count} check(s)',
  'code.proof.checkPassed': 'Passed — {seconds}s',
  'code.proof.checkFailed': 'Did not pass',
  'code.proof.noChecks': 'No checks were run.',
  'code.proof.verified': 'confirmed',
  'code.proof.notChecked': 'not checked yet',
  'code.proof.repairPassed': 'Fixed after {attempts} attempt(s).',
  'code.proof.repairFailed': 'Could not fix it ({attempts} of {max} attempts).',
  'code.proof.truncated': 'More checks were run than are shown here.',
  'code.proof.details': 'details',

  // Code tasks (Phase 5) — the task screen names the JOB, never the mechanism.
  // The three autonomy choices are plain sentences, not config keys.
  'code.task.title': 'Tasks',
  'code.task.new': 'Start a task',
  'code.task.empty': 'No tasks yet. Ask Eclipse to build or change something.',
  'code.task.working': 'Writing the change…',
  'code.task.resultDone': 'Done. I changed the project and saved what changed.',
  'code.task.seeChanges': 'See what changed',
  'code.task.undoChange': 'Undo this change',
  'code.task.cancel': 'Stop this task',
  'code.task.discard': 'Remove the task’s work area',
  'code.task.resultFailed': 'That task did not finish. Nothing was sent anywhere.',
  'code.task.changeNewFile': 'New file: {name}',
  'code.task.changeEditedFile': 'Changed: {name}',
  'code.task.changeRemovedFile': 'Removed: {name}',
  'code.task.autonomy.planOnly': 'Just tell me what you’d do',
  'code.task.autonomy.editVerify': 'Make the change and show me',
  'code.task.autonomy.approveExternal': 'Do it and ask me before anything outside the app',
  'code.task.badge.planOnly': 'Just planning',
  'code.task.badge.editVerify': 'Changes and shows',
  'code.task.badge.approveExternal': 'Asks before going outside',
  'code.task.status.created': 'Starting',
  'code.task.status.planReview': 'Waiting for you to choose',
  'code.task.status.completed': 'Done',
  'code.task.status.failed': 'Could not finish',
  'code.task.status.cancelled': 'Stopped',
  'code.task.status.discarded': 'Removed',
  'code.task.plan.title': 'What I’d do',
  'code.task.plan.accept': 'Go ahead and make the change',
  'code.task.plan.reject': 'Not now',
  'code.task.plan.willTouch': 'I’d work on: {files}',
  'code.task.plan.willCheck': 'I’d check it with: {checks}',
  'code.approvals.title': 'Actions waiting for you',
  'code.approvals.none': 'Nothing is waiting for your OK.',
  'code.approvals.action.commit': 'Save the change',
  'code.approvals.action.push': 'Send the change to the project’s remote',
  'code.approvals.action.openPr': 'Open a review request for the change',
  'code.approvals.action.deploy': 'Publish the change',
  'code.approvals.approve': 'Approve',
  'code.approvals.deny': 'Deny',
  'code.approvals.approved': 'Approved',
  'code.approvals.denied': 'Denied',
  'code.approvals.used': 'Already used once',
  'code.approvals.needsOk': 'I did not run that — it needs the app owner’s OK. Ask them and I’ll continue.',

  // ── Scheduled jobs (Phase 6) ─────────────────────────────────────────────
  // The user names the JOB, never the mechanism. A cron expression, skill id,
  // job kind or machine reason is never on this surface — only behind "details".
  'jobs.title': 'Scheduled jobs',
  'jobs.description': 'Work Eclipse does for you on a schedule, or when something happens.',
  'jobs.empty': 'No jobs yet. Start with one from the library.',
  'jobs.create': 'New job',
  'jobs.library.title': 'Start with a ready-made job',
  'jobs.library.use': 'Use this',
  'jobs.library.answer': 'Tell me: {label}',
  'jobs.library.placeholder': 'e.g. {example}',
  'jobs.editor.name': 'What should we call this job?',
  'jobs.editor.namePlaceholder': 'e.g. Overnight news on my holdings',
  'jobs.editor.cadence': 'When should it run?',
  'jobs.editor.cadence.weekdayMorning': 'Every weekday at 7:30am',
  'jobs.editor.cadence.daily': 'Every day at 8:00am',
  'jobs.editor.cadence.every6h': 'Every 6 hours',
  'jobs.editor.cadence.every12h': 'Every 12 hours',
  'jobs.editor.cadence.fileChange': 'When a file in a folder changes',
  'jobs.editor.cadence.webAddress': 'When something calls this job’s web address',
  'jobs.editor.cadence.manual': 'Only when I start it',
  'jobs.editor.whichFolder': 'Which folder?',
  'jobs.editor.delivery': 'How should it tell me?',
  'jobs.editor.delivery.inApp': 'In the app',
  'jobs.editor.delivery.artifact': 'Save a report',
  'jobs.editor.details': 'Details',
  'jobs.editor.schedule': 'Schedule',
  'jobs.editor.enable': 'Turn this job on',
  'jobs.editor.save': 'Save job',
  'jobs.editor.saved': 'Job saved. It is off until you turn it on.',
  'jobs.list.enabledOn': 'On',
  'jobs.list.enabledOff': 'Off',
  'jobs.list.runNow': 'Run now',
  'jobs.list.enable': 'Turn on',
  'jobs.list.disable': 'Turn off',
  'jobs.list.history': 'What happened',
  'jobs.list.delete': 'Remove this job',
  'jobs.list.never': 'Hasn’t run yet',
  'jobs.breaker.paused': 'This job has failed a few times, so I paused it.',
  'jobs.breaker.reset': 'Restart this job',
  'jobs.breaker.pausedBy': 'Paused after repeated trouble. Restart when you’re ready.',
  'jobs.breaker.closed': 'Working normally',
  'jobs.breaker.open': 'Paused — failed several times in a row',
  'jobs.breaker.half_open': 'Trying once more',
  'jobs.run.status.running': 'Running now',
  'jobs.run.status.ok': 'Finished',
  'jobs.run.status.failed': 'Couldn’t finish',
  'jobs.run.status.skipped': 'Skipped',
  'jobs.run.status.timed_out': 'Stopped — took too long',
  'jobs.run.status.refused': 'Not allowed',
  'jobs.run.delivered': 'Delivered',
  'jobs.run.webhook.token': 'Copy this now — you won’t see it again.',
  'jobs.run.details': 'Details',

  // ── Analysis / computed results (Phase 8) ────────────────────────────────
  // A computed number says so, in words. It names the finance job, never the
  // mechanism (no interpreter/module/exit-code vocabulary).
  'analysis.computed': 'Worked out by Eclipse',
  'analysis.retrieved': 'From a source',
  'analysis.unavailable': 'This number has no record of where it came from, so Eclipse won’t show it.',
  'analysis.noOutputs': 'Nothing came back from that.',
  'analysis.saved': 'Saved',
  'analysis.notASource': 'This was worked out by Eclipse from the data above — it isn’t a figure from a data source.',
  'analysis.details': 'How Eclipse worked this out',
  'analysis.needsInput': 'I need a bit more to work that out: {what}',
  'analysis.notEnabled': 'Eclipse isn’t set up to work numbers out in this session.',

  // ── Ready-made finance tools (Phase 9) ───────────────────────────────────
  // The user asks in words and answers in words. A "kit"/"scaffold"/"template"
  // never appears on the surface.
  'kit.market_data_adapter.title': 'A new market-data source',
  'kit.market_data_adapter.summary': 'Connect a new place to get market data from.',
  'kit.market_data_adapter.q.source_name': 'What should we call this source?',
  'kit.market_data_adapter.q.data_type': 'What kind of data does it provide — a live price, history, statements, or news?',
  'kit.mcp_server.title': 'A new tool server',
  'kit.mcp_server.summary': 'Add a small server that offers extra tools to Eclipse.',
  'kit.mcp_server.q.source_name': 'What should we call this tool server?',
  'kit.mcp_server.q.description': 'In one line, what does it do?',
  'kit.ratio_calculator.title': 'A new financial ratio',
  'kit.ratio_calculator.summary': 'Work out a ratio that isn’t built in yet.',
  'kit.ratio_calculator.q.ratio_name': 'What is the ratio called?',
  'kit.ratio_calculator.q.description': 'In words, how is it worked out?',
  'kit.backtest_strategy.title': 'A backtest strategy',
  'kit.backtest_strategy.summary': 'Try a strategy over past prices and see how it would have done.',
  'kit.backtest_strategy.q.strategy_name': 'What should we call this strategy?',
  'kit.backtest_strategy.q.period': 'Which period should it look at — 1 year, 5 years, or another range?',
  'kit.chart_indicator.title': 'A chart indicator',
  'kit.chart_indicator.summary': 'Add a line or signal to a price chart.',
  'kit.chart_indicator.q.indicator_name': 'What is the indicator called?',
  'kit.portfolio_module.title': 'A portfolio analysis',
  'kit.portfolio_module.summary': 'Look at your holdings together — weights, contributions, and more.',
  'kit.portfolio_module.q.module_name': 'What should we call this analysis?',
  'kit.data_ingestion_pipeline.title': 'A data-import job',
  'kit.data_ingestion_pipeline.summary': 'Keep a dataset up to date from a source, without creating duplicates.',
  'kit.data_ingestion_pipeline.q.source_name': 'What should we call this import?',
  'kit.research_workflow.title': 'A repeatable research routine',
  'kit.research_workflow.summary': 'Save a routine you can run again and again.',
  'kit.research_workflow.q.workflow_name': 'What should we call this routine?',
  'kit.research_workflow.q.description': 'In one line, what does it do?',
  'kit.result.done': 'Done — I built it and checked it. It works.',
  'kit.result.unavailable': 'I couldn’t get that far — some data was missing.',
  'kit.result.inert': 'I’ve prepared it — review it and switch it on when you’re happy.',
  'kit.result.checkFailed': 'I built it, but one check didn’t pass. Want me to fix it?',

  // Keyboard shortcuts dialog
  'keyboard.title': 'Keyboard shortcuts',
  'keyboard.searchPlaceholder': 'Search actions, keys, or pages',
  'keyboard.noMatches': 'No matching shortcuts.',
  'keyboard.globalGroup': 'Global and chart shortcuts',
  'keyboard.navGroup': 'Sidebar navigation',
} as const;
