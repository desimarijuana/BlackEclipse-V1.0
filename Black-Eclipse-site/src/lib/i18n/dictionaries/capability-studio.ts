// ── English dictionary — Capability Studio domain (Phase D) ─────────────────
// A DOMAIN slice of the canonical English dictionary, spread into `en` so
// `t('studio.…')` stays autocompleted and type-checked exactly as before.
// Moving a domain here is the documented way the oversized `en.ts` SHRINKS
// (see the ratchet note in `src/lib/size-budget.test.ts`). This slice owns the
// Capability Studio chrome: the section switcher, the skills and integrations
// summaries, and the "open the manager" actions.

export const capabilityStudio = {
  'studio.title': 'Capability Studio',
  'studio.subtitle': 'One place for everything Eclipse can be extended with — pages and widgets, tools and plugins, skills, and your connected data.',
  'studio.section.pages': 'Pages & widgets',
  'studio.section.plugins': 'Tools & plugins',
  'studio.section.skills': 'Skills',
  'studio.section.integrations': 'Integrations',
  'studio.loading': 'Loading…',
  'studio.loadFailed': "Couldn't load {what} — {reason}",
  'studio.retry': 'Retry',
  'studio.open': 'Open {what}',
  'studio.plugins.hint': 'Enable, inspect and configure the tools your plugins contribute. Installing a new plugin goes through the operator acquisition route (Settings → Data Sources / the recovery console), never from here.',
  'studio.skills.total': 'Skills',
  'studio.skills.enabled': 'Enabled',
  'studio.skills.pending': 'Awaiting evaluation',
  'studio.skills.issues': 'Needs attention',
  'studio.skills.empty': 'No skills loaded yet.',
  'studio.integrations.sources': 'Connected data sources',
  'studio.integrations.ready': 'Enabled',
  'studio.integrations.attention': 'Needs attention',
  'studio.integrations.mcp': 'MCP servers',
  'studio.integrations.mcpConnected': 'Connected',
  'studio.integrations.mcpTools': 'Registered tools',
  'studio.integrations.openData': 'Open Data Sources',
  'studio.integrations.openMcp': 'Open MCP Servers',
  'studio.integrations.empty': 'Nothing connected yet.',
} as const;
