// ── Navigation / Action / Instrument registries ─────────────────────────────
// Centralized, single source of truth. Screens/features register destinations
// and actions here once; the command bar consumes this registry — search logic
// is never scattered through the app.

import type {
  AppTab,
  Destination,
  SearchAction,
  SearchEntity,
} from './types';
import { INDEX_DEFS } from '@/lib/indices';
import { MEMORY_TABS, SKILLS_TABS } from '@/lib/app-screens';
import { JOURNAL_TABS } from '@/lib/journal-tabs';

// ── Page (destination) registry ─────────────────────────────────────────────
interface PageEntry {
  id: string;
  kind: SearchEntity['kind'];
  title: string;
  aliases: string[];
  keywords: string[];
  icon?: string;
  tab: AppTab;
  subroute?: string;
  params?: Record<string, string>;
  deepLink?: string;
  rankBoost?: number;
  /**
   * Navigation grouping for the palette's "Go to" list. Top-level tabs use
   * 'app'; a tab's sub-pages use the tab id (e.g. 'journal') so they nest under
   * their parent instead of mixing into the top-level list. Defaults to 'app'.
   */
  group?: string;
  /** True for a sub-page of another page (rendered indented in the palette). */
  child?: boolean;
}

const pages = new Map<string, PageEntry>();

function registerPage(entry: PageEntry) {
  pages.set(entry.id, entry);
}

/** Look up a registered page entity by its canonical id. */
export function getPage(id: string): SearchEntity | undefined {
  const p = pages.get(id);
  if (!p) return undefined;
  return pageToEntity(p);
}

/** All registered pages, as search entities. */
export function getAllPages(): SearchEntity[] {
  return [...pages.values()].map(pageToEntity);
}

/** Registered pages plus their nav metadata (group / child), for the palette. */
export function getPageEntries(): Array<SearchEntity & { group: string; child: boolean }> {
  return [...pages.values()].map((p) => ({
    ...pageToEntity(p),
    group: p.group ?? 'app',
    child: !!p.child,
  }));
}

function pageToEntity(p: PageEntry): SearchEntity {
  const destination: Destination = {
    tab: p.tab,
    ...(p.subroute ? { subroute: p.subroute } : {}),
    ...(p.params ? { params: p.params } : {}),
    ...(p.deepLink ? { deepLink: p.deepLink } : {}),
  };
  return {
    id: p.id,
    kind: p.kind,
    title: p.title,
    keywords: p.keywords,
    icon: p.icon,
    rankBoost: p.rankBoost,
    destination,
  };
}

/**
 * The palette's empty-query "Pages" launcher, in sidebar order (ChatBot → … →
 * Tables) plus Bots (its own mode, kept for discoverability). ONE list, guarded
 * by `registry-sync.test.ts`: every sidebar section must appear here and every
 * entry must be a registered top-level page — no sub-pages, no `settings`
 * (a modal), no `chart` (retired). Labs stay searchable, just not launcher rows.
 */
export const LAUNCHER_ORDER = [
  'page-chat',
  'page-home',
  'page-dashboard',
  'page-investor-eye',
  'page-market-workspace',
  'page-screener',
  'page-portfolio',
  'page-journal',
  'page-news',
  'page-heatmap',
  'page-economics',
  'page-alerts',
  'page-strategy-studio',
  'page-overview',
  'page-skills',
  'page-sdk',
  'page-memory',
  'page-artifacts',
  'page-tables',
  'page-code',
  'page-bots',
] as const;

/** Launcher rows for the palette, in LAUNCHER_ORDER. */
export function getLauncherPages(): SearchEntity[] {
  const out: SearchEntity[] = [];
  for (const id of LAUNCHER_ORDER) {
    const page = getPage(id);
    if (page) out.push(page);
  }
  return out;
}

// ── Instrument (securities/indicators) registry ────────────────────────────
// Phase 1 seeds the highest-value instruments + indicators. The full universe
// arrives in Phase 2 from the JDDS index build.
interface InstrumentEntry {
  id: string;
  kind: SearchEntity['kind'];
  title: string;
  symbol: string;
  assetClass: SearchEntity['assetClass'];
  market?: string;
  aliases: string[];
  keywords: string[];
  icon?: string;
  tab: AppTab;
  subroute?: string;
  params?: Record<string, string>;
  deepLink?: string;
  rankBoost?: number;
}

const instruments = new Map<string, InstrumentEntry>();

function registerInstrument(entry: InstrumentEntry) {
  instruments.set(entry.id, entry);
}

/** Resolve an exact symbol/alias → canonical instrument entity. */
export function getInstrumentByAlias(raw: string): SearchEntity | undefined {
  const key = raw.trim().toLowerCase();
  for (const inst of instruments.values()) {
    if (
      inst.symbol.toLowerCase() === key ||
      inst.title.toLowerCase() === key ||
      inst.aliases.some((a) => a.toLowerCase() === key)
    ) {
      return instrumentToEntity(inst);
    }
  }
  return undefined;
}

/** All registered instruments as search entities. */
export function getAllInstruments(): SearchEntity[] {
  return [...instruments.values()].map(instrumentToEntity);
}

function instrumentToEntity(i: InstrumentEntry): SearchEntity {
  const destination: Destination = {
    tab: i.tab,
    ...(i.subroute ? { subroute: i.subroute } : {}),
    ...(i.params ? { params: i.params } : {}),
    ...(i.deepLink ? { deepLink: i.deepLink } : {}),
  };
  return {
    id: i.id,
    kind: i.kind,
    title: i.title,
    symbol: i.symbol,
    assetClass: i.assetClass,
    market: i.market,
    keywords: i.keywords,
    icon: i.icon,
    rankBoost: i.rankBoost,
    destination,
  };
}

// ── Action (command palette) registry ───────────────────────────────────────
const actions = new Map<string, SearchAction>();

function registerAction(action: SearchAction) {
  actions.set(action.id, action);
}

/** All registered actions (static + dynamic). */
export function getAllActions(): SearchAction[] {
  return [...actions.values()];
}

/** Look up a registered action by its canonical id. */
export function getAction(id: string): SearchAction | undefined {
  return actions.get(id);
}

// ── Default registrations ────────────────────────────────────────────────────
// Pages.
registerPage({ id: 'page-home', kind: 'page', title: 'Dashboard', aliases: ['dashboard', 'daily brief', 'market dashboard', 'portfolio dashboard', 'overview'], keywords: ['dashboard', 'daily', 'brief', 'overview', 'market', 'portfolio', 'health', 'regime', 'breadth', 'watchlist'], icon: 'dashboard', tab: 'home', rankBoost: 1.28 });
registerPage({ id: 'page-dashboard', kind: 'page', title: 'Command Center', aliases: ['command center', 'widgets', 'workspace'], keywords: ['command center', 'widgets', 'workspace'], icon: 'dashboard', tab: 'dashboard', rankBoost: 1.15 });
registerPage({ id: 'page-market-workspace', kind: 'page', title: 'Chart Workspace', aliases: ['chart workspace', 'market workspace', 'multi chart', 'charts', 'terminal', 'workspace', 'trading terminal', 'grid'], keywords: ['chart workspace', 'market workspace', 'multi chart', 'charts', 'terminal', 'grid', 'layout', 'linked charts'], icon: 'candlestick', tab: 'market-workspace', rankBoost: 1.2 });
registerPage({ id: 'page-investor-eye', kind: 'page', title: 'Investor Eye', aliases: ['investor eye', 'gods eye', 'god\'s eye', 'world map', 'geopolitical', 'geopolitics', 'global state', 'world state', 'events map'], keywords: ['investor eye', 'gods eye', 'world', 'map', 'geopolitical', 'events', 'global', 'geopolitics', 'intelligence'], icon: 'eye', tab: 'investor-eye', rankBoost: 1.25 });
registerPage({ id: 'page-chat', kind: 'page', title: 'ChatBot', aliases: ['chat', 'ai', 'assistant', 'ask ai'], keywords: ['chatbot', 'chat', 'conversation', 'ai'], icon: 'bot', tab: 'chat' });
registerPage({ id: 'page-screener', kind: 'page', title: 'Market Discover', aliases: ['screener', 'discovery', 'stocks', 'discover', 'screen'], keywords: ['screener', 'market', 'stocks', 'discovery'], icon: 'screen', tab: 'discovery' });
registerPage({ id: 'page-portfolio', kind: 'page', title: 'Portfolio', aliases: ['my portfolio', 'holdings', 'watchlist', 'positions'], keywords: ['portfolio', 'holdings', 'watchlist', 'positions'], icon: 'pie', tab: 'portfolio', rankBoost: 1.1 });
registerPage({ id: 'page-journal', kind: 'page', title: 'Trading Journal', aliases: ['journal', 'trading journal', 'my trades', 'trade log'], keywords: ['journal', 'trading', 'trades', 'log'], icon: 'book', tab: 'journal', rankBoost: 1.1 });
registerPage({ id: 'page-news', kind: 'page', title: 'Market News', aliases: ['news', 'bulletin', 'headlines'], keywords: ['news', 'market news', 'headlines'], icon: 'news', tab: 'news' });
registerPage({ id: 'page-heatmap', kind: 'page', title: 'Market Bubbles', aliases: ['heatmap', 'bubbles', 'market map', 'treemap'], keywords: ['heatmap', 'bubbles', 'treemap'], icon: 'orbit', tab: 'heatmap' });
registerPage({ id: 'page-economics', kind: 'page', title: 'Economics', aliases: ['economics', 'economic calendar', 'macro', 'calendar', 'events'], keywords: ['economics', 'macro', 'calendar', 'indicators'], icon: 'globe', tab: 'economics' });
registerPage({ id: 'page-alerts', kind: 'page', title: 'Price Alerts', aliases: ['alerts', 'price alerts', 'notifications'], keywords: ['alerts', 'price', 'notifications'], icon: 'bell', tab: 'alerts' });
registerPage({ id: 'page-skills', kind: 'page', title: 'Skills', aliases: ['skills', 'agent skills', 'skill library', 'capabilities'], keywords: ['skills', 'agent', 'library', 'capabilities', 'tools'], icon: 'skills', tab: 'skills', rankBoost: 1.1 });
registerPage({ id: 'page-memory', kind: 'page', title: 'Eclipse Memory', aliases: ['memory', 'eclipse memory', 'agent memory', 'memory control room'], keywords: ['memory', 'eclipse memory', 'agent', 'persistence', 'audit'], icon: 'memory', tab: 'memory', rankBoost: 1.1 });
registerPage({ id: 'page-bots', kind: 'page', title: 'Bots', aliases: ['bots', 'autonomous bots', 'scheduled agents', 'automations', 'agents', 'schedules'], keywords: ['bots', 'agents', 'automation', 'schedule', 'cron', 'recurring', 'background', 'tasks'], icon: 'ghost', tab: 'bots', rankBoost: 1.15 });
registerPage({ id: 'page-settings', kind: 'page', title: 'Settings', aliases: ['settings', 'preferences', 'config', 'options'], keywords: ['settings', 'preferences', 'config'], icon: 'settings', tab: 'settings' });
registerPage({ id: 'page-backtest', kind: 'page', title: 'Quant Research', aliases: ['quant research', 'backtest', 'backtesting', 'strategy', 'strategies', 'quant', 'research workspace', 'equity curve', 'optimization'], keywords: ['quant', 'research', 'backtest', 'strategy', 'optimize', 'walk forward', 'monte carlo', 'dataset', 'equity curve', 'drawdown'], icon: 'candlestick', tab: 'backtest', rankBoost: 1.2 });
registerPage({ id: 'page-strategy-studio', kind: 'page', title: 'Strategy Studio', aliases: ['strategy studio', 'ai strategy', 'prompt strategy', 'vibe trading', 'strategy builder', 'ai backtest', 'paper trading'], keywords: ['strategy', 'studio', 'ai', 'prompt', 'backtest', 'paper', 'walk forward', 'robustness', 'deploy'], icon: 'candlestick', tab: 'strategy-studio', rankBoost: 1.25 });
registerPage({ id: 'page-research-data', kind: 'page', title: 'Research Data', aliases: ['research data', 'datasets', 'data quality', 'dataset explorer', 'verification', 'provenance', 'universe'], keywords: ['research', 'data', 'dataset', 'quality', 'providers', 'verification', 'provenance', 'calendar', 'universe'], icon: 'activity', tab: 'research-data', rankBoost: 1.2 });
  registerPage({ id: 'page-factor-lab', kind: 'page', title: 'Factor Lab', aliases: ['factor lab', 'factor', 'factors', 'alpha', 'alpha research', 'ic', 'rank ic', 'information coefficient', 'quantile portfolio', 'factor library', 'alpha composer'], keywords: ['factor', 'alpha', 'ic', 'rank ic', 'momentum', 'value', 'quality', 'quantile', 'portfolio', 'decay', 'validation', 'research'], icon: 'activity', tab: 'factor-lab', rankBoost: 1.2 });
  registerPage({ id: 'page-ml-lab', kind: 'page', title: 'ML Lab', aliases: ['ml lab', 'machine learning', 'ml research', 'model training', 'train model', 'dataset builder', 'model registry', 'walk forward', 'experiments'], keywords: ['ml', 'machine learning', 'model', 'training', 'dataset', 'feature', 'target', 'experiment', 'registry', 'walk forward', 'purged', 'leakage', 'evaluation', 'drift'], icon: 'activity', tab: 'ml-lab', rankBoost: 1.2 });
// Sidebar-visible screens that previously had no palette entry.
registerPage({ id: 'page-overview', kind: 'page', title: 'Graph Studio', aliases: ['graph studio', 'overview', 'graph', 'workflows', 'workflow gallery'], keywords: ['graph', 'studio', 'overview', 'workflow', 'gallery', 'nodes', 'canvas'], icon: 'dashboard', tab: 'overview', rankBoost: 1.1 });
registerPage({ id: 'page-sdk', kind: 'page', title: 'Eclipse SDK', aliases: ['eclipse sdk', 'sdk', 'sdk console', 'extensibility'], keywords: ['sdk', 'eclipse', 'extensibility', 'blueprint', 'capabilities'], icon: 'sdk', tab: 'sdk', rankBoost: 1.1 });
registerPage({ id: 'page-artifacts', kind: 'page', title: 'Artifacts', aliases: ['artifacts', 'artifact center', 'artifact gallery', 'files center'], keywords: ['artifacts', 'artifact', 'gallery', 'files', 'deliverables'], icon: 'artifacts', tab: 'artifacts', rankBoost: 1.1 });
registerPage({ id: 'page-tables', kind: 'page', title: 'Tables', aliases: ['tables', 'data tables', 'table editor'], keywords: ['tables', 'table', 'data', 'rows'], icon: 'tables', tab: 'tables' });
// Shell-reachable screens outside the sidebar (ChatBot tools land here).
registerPage({ id: 'page-tasks', kind: 'page', title: 'Tasks', aliases: ['tasks', 'task list', 'agent tasks', 'todo'], keywords: ['tasks', 'task', 'todo', 'plan', 'checklist'], icon: 'tasks', tab: 'tasks' });
registerPage({ id: 'page-code', kind: 'page', title: 'Builds', aliases: ['builds', 'code tasks', 'eclipse builds', 'builder', 'changes eclipse made', 'self-build'], keywords: ['builds', 'code', 'self-build', 'builder', 'diff', 'land', 'checks', 'rollback', 'approval', 'scorecard'], icon: 'code', tab: 'code', rankBoost: 1.05 });
registerPage({ id: 'page-pages', kind: 'page', title: 'Saved Pages', aliases: ['saved pages', 'pages', 'my pages', 'blueprints', 'custom pages'], keywords: ['pages', 'blueprint', 'saved', 'custom', 'page'], icon: 'pages', tab: 'pages' });
registerPage({ id: 'page-ui-builder', kind: 'page', title: 'UI Builder', aliases: ['ui builder', 'capability studio', 'component builder'], keywords: ['ui', 'builder', 'capability', 'components', 'studio'], icon: 'ui-builder', tab: 'ui-builder' });

// Market Regime — not a tab. Selecting it opens the top-bar Market Regime panel
// (the shell handles the `action: 'open-regime'` param and returns before any tab
// switch). Discoverable by searching "market regime", "risk on", "sentiment", etc.
registerPage({ id: 'page-market-regime', kind: 'page', title: 'Market Regime', aliases: ['market regime', 'regime', 'risk on', 'risk off', 'risk-on', 'risk-off', 'market sentiment', 'market breadth', 'volatility regime', 'aurora'], keywords: ['market regime', 'regime', 'sentiment', 'risk on', 'risk off', 'breadth', 'volatility', 'vix', 'aurora', 'macro'], icon: 'activity', tab: 'dashboard', params: { action: 'open-regime' }, rankBoost: 1.2 });

// ─── Generated sub-pages (Skills / Memory / Journal) ──────────────────────────
// Those screens render ONE tab bar each and consume subroutes by matching the
// RENDERED tab id (`useSubroute` + `screenTab`). Hand-writing palette entries
// for them drifted twice (stale labels, missing views), so the entries are
// generated from the same arrays the bars render (`app-screens.ts`,
// `journal-tabs.ts`). `SUB_PAGE_HINTS` carries only curated search vocabulary
// (aliases / boosts) — never ids or labels.
const SUB_PAGE_HINTS: Record<string, { aliases?: string[]; keywords?: string[]; rankBoost?: number }> = {
  'memory.memories': { aliases: ['memory explorer', 'saved memory', 'facts'], keywords: ['explorer', 'facts', 'saved'] },
  'memory.history': { aliases: ['session history', 'session search', 'past sessions', 'conversation history'], keywords: ['recall'], rankBoost: 1.1 },
  'memory.reviews': { aliases: ['learning reviews', 'learning review', 'self improvement'], keywords: ['learning', 'review'] },
  'memory.health': { aliases: ['memory health', 'health export', 'database identity'], keywords: ['export'] },
  'memory.lifecycle': { aliases: ['memory lifecycle', 'expired memory', 'superseded memory'], keywords: ['expired', 'superseded', 'conflicts'] },
  'memory.policies': { aliases: ['memory policies', 'memory retention'], keywords: ['policy', 'retention'] },
  'memory.profile': { aliases: ['memory profile', 'persistent context', 'user profile'], keywords: ['profile', 'context'] },
  'memory.activity': { aliases: ['memory activity', 'retrieval diagnostics'], keywords: ['activity', 'retrieval'] },
  'skills.start': { aliases: ['start here', 'onboarding', 'getting started'], keywords: ['start', 'onboarding'], rankBoost: 1.2 },
  'skills.project': { aliases: ['project skills', 'repository skills', 'trust project'], keywords: ['project', 'repository'], rankBoost: 1.1 },
  'skills.learn': { aliases: ['learn a skill', 'learn from run', 'learn from document', 'guided learn'], keywords: ['learn', 'draft'], rankBoost: 1.15 },
  'skills.learning': { aliases: ['learning queue', 'learning candidates', 'learn from run', 'candidates'], keywords: ['learning', 'queue', 'candidates'], rankBoost: 1.15 },
  'skills.journey': { aliases: ['learning journey', 'provenance graph', 'how did this skill'], keywords: ['journey', 'provenance'] },
  'skills.maintenance': { aliases: ['skill maintenance', 'cleanup'], keywords: ['maintenance', 'cleanup'] },
  'skills.evaluation': { aliases: ['evaluation center', 'skill evaluation'], keywords: ['evaluation'] },
  'skills.bundles': { aliases: ['skill bundles', 'task profiles'], keywords: ['bundles'] },
  'journal.trades': { aliases: ['journal trades', 'my trades', 'trade log'], keywords: ['trades', 'log'], rankBoost: 1.1 },
  'journal.analytics': { aliases: ['journal analytics', 'performance', 'stats'], keywords: ['analytics', 'performance'], rankBoost: 1.1 },
  'journal.decisions': { aliases: ['advisory decisions', 'decision log'], keywords: ['advisory', 'decisions'] },
  'journal.notebook': { aliases: ['journal notebook', 'notes'], keywords: ['notes'] },
  'journal.playbook': { aliases: ['journal playbook', 'setups', 'strategies'], keywords: ['playbook', 'setups'] },
};

function dedupe(xs: Array<string | undefined>): string[] {
  return [...new Set(xs.filter((x): x is string => Boolean(x && x.trim())).map((x) => x.trim().toLowerCase()))];
}

function registerScreenSubPages(
  tab: 'memory' | 'skills' | 'journal',
  icon: string,
  defs: readonly { id: string; label: string; aliases?: string[] }[],
) {
  for (const def of defs) {
    const slug = `${tab}.${def.id}`;
    const hints = SUB_PAGE_HINTS[slug] ?? {};
    const label = def.label.toLowerCase();
    const words = label.split(/[^a-z0-9]+/).filter(Boolean);
    registerPage({
      id: `sub-${tab}-${def.id}`,
      kind: 'page',
      title: def.label,
      aliases: dedupe([label, `${tab} ${label}`, ...(def.aliases ?? []), ...(hints.aliases ?? [])]),
      keywords: dedupe([tab, ...words, ...(def.aliases ?? []), ...(hints.keywords ?? [])]),
      icon,
      tab,
      subroute: slug,
      group: tab,
      child: true,
      ...(hints.rankBoost ? { rankBoost: hints.rankBoost } : {}),
    });
  }
}

registerScreenSubPages('skills', 'skills', SKILLS_TABS);
registerScreenSubPages('memory', 'memory', MEMORY_TABS);
registerScreenSubPages('journal', 'book', JOURNAL_TABS);

// ── Sub-pages ────────────────────────────────────────────────────────────────
// Every internal view that used to be unreachable (the shell ignored
// `Destination.subroute`). These are real destinations: each `subroute` is
// consumed by its screen via the `useSubroute` hook. Grouped by parent tab so
// the palette's "Go to" list nests them instead of flattening the top level.

// Economics — section tabs + the indicator-focused calendar.
registerPage({ id: 'sub-econ-overview', kind: 'page', title: 'Overview', aliases: ['economics overview', 'macro snapshot'], keywords: ['economics', 'overview', 'snapshot', 'macro'], icon: 'globe', tab: 'economics', subroute: 'economics.overview', group: 'economics', child: true });
registerPage({ id: 'sub-econ-calendar', kind: 'page', title: 'Calendar', aliases: ['economic calendar', 'econ calendar', 'releases'], keywords: ['economics', 'calendar', 'events', 'releases'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', group: 'economics', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-econ-explorer', kind: 'page', title: 'Time-series Explorer', aliases: ['econ explorer', 'time series', 'macro data'], keywords: ['economics', 'explorer', 'time series', 'series'], icon: 'globe', tab: 'economics', subroute: 'economics.explorer', group: 'economics', child: true });

// Journal sub-pages are generated above from 'journal-tabs.ts' — one row per rendered tab.

// Screener — asset-class tabs.
registerPage({ id: 'sub-disc-markets', kind: 'page', title: 'Markets', aliases: ['screener markets', 'global markets'], keywords: ['screener', 'markets', 'indices'], icon: 'screen', tab: 'discovery', subroute: 'discovery.markets', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-stocks', kind: 'page', title: 'Stocks', aliases: ['screener stocks'], keywords: ['screener', 'stocks', 'equities'], icon: 'screen', tab: 'discovery', subroute: 'discovery.stocks', group: 'discovery', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-disc-etfs', kind: 'page', title: 'ETFs', aliases: ['screener etfs'], keywords: ['screener', 'etf', 'funds'], icon: 'screen', tab: 'discovery', subroute: 'discovery.etfs', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-funds', kind: 'page', title: 'Funds', aliases: ['screener funds', 'mutual funds'], keywords: ['screener', 'funds'], icon: 'screen', tab: 'discovery', subroute: 'discovery.funds', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-dividends', kind: 'page', title: 'Dividend Stocks', aliases: ['dividends', 'dividend stocks', 'yield'], keywords: ['screener', 'dividend', 'yield'], icon: 'screen', tab: 'discovery', subroute: 'discovery.dividend_stocks', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-crypto', kind: 'page', title: 'Crypto', aliases: ['screener crypto', 'cryptocurrencies'], keywords: ['screener', 'crypto', 'coins'], icon: 'screen', tab: 'discovery', subroute: 'discovery.crypto', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-forex', kind: 'page', title: 'Forex', aliases: ['screener forex', 'currencies', 'fx'], keywords: ['screener', 'forex', 'fx', 'currencies'], icon: 'screen', tab: 'discovery', subroute: 'discovery.forex', group: 'discovery', child: true });
registerPage({ id: 'sub-disc-commodities', kind: 'page', title: 'Commodities', aliases: ['screener commodities', 'metals', 'energy'], keywords: ['screener', 'commodities', 'metals', 'energy'], icon: 'screen', tab: 'discovery', subroute: 'discovery.commodities', group: 'discovery', child: true });

// Alerts — view tabs.
registerPage({ id: 'sub-alerts-watches', kind: 'page', title: 'Live Watches', aliases: ['live watches', 'my alerts'], keywords: ['alerts', 'watches'], icon: 'bell', tab: 'alerts', subroute: 'alerts.watches', group: 'alerts', child: true, rankBoost: 1.05 });
registerPage({ id: 'sub-alerts-create', kind: 'page', title: 'Create Watch', aliases: ['new alert', 'create alert', 'new watch'], keywords: ['alerts', 'create', 'new', 'watch'], icon: 'bell', tab: 'alerts', subroute: 'alerts.create', group: 'alerts', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-alerts-history', kind: 'page', title: 'Alert History', aliases: ['alert history', 'fired alerts'], keywords: ['alerts', 'history', 'fired'], icon: 'bell', tab: 'alerts', subroute: 'alerts.history', group: 'alerts', child: true });

// Settings — modal sections (the shell opens the Settings modal for these).
// Sections are named for WHAT is configured, not backend concepts:
//   General (startup + theme/customization) · Sound · AI / LLM · Investor Eye ·
//   Market Data · News · Charts · Sidebar & Navigation · Alerts · Data &
//   Storage · System.
registerPage({ id: 'sub-set-general', kind: 'page', title: 'General', aliases: ['startup', 'start screen', 'preferences', 'general', 'currency', 'timezone', 'refresh', 'confirm', 'theme', 'branding', 'logo', 'favicon', 'app name', 'brand color', 'preset', 'density', 'radius', 'font', 'typography', 'language', 'translate', 'locale', 'accessibility', 'a11y', 'reduce motion', 'high contrast', 'text size', 'font size', 'rtl'], keywords: ['settings', 'general', 'startup', 'start screen', 'market', 'currency', 'timezone', 'refresh', 'customization', 'theme', 'branding', 'logo', 'favicon', 'font', 'colors', 'brand color', 'language', 'accessibility', 'motion', 'contrast', 'text size'], icon: 'settings', tab: 'settings', subroute: 'settings.general', group: 'settings', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-set-persona', kind: 'page', title: 'Persona', aliases: ['persona', 'personas', 'personality', 'system prompt', 'custom instructions', 'prompt', 'tone', 'style', 'chat behavior'], keywords: ['settings', 'persona', 'personality', 'prompt', 'instructions', 'tone', 'style', 'draft', 'active', 'reset'], icon: 'settings', tab: 'settings', subroute: 'settings.persona', group: 'settings', child: true, rankBoost: 1.3 });
registerPage({ id: 'sub-set-sound', kind: 'page', title: 'Sound', aliases: ['sound', 'sounds', 'audio', 'ui sounds', 'volume', 'click sound', 'tick sound', 'toggle sound', 'notification sound', 'sound pack', 'mute sounds', 'silence'], keywords: ['settings', 'sound', 'sounds', 'audio', 'volume', 'click', 'tick', 'toggle', 'notification', 'feedback', 'pack', 'mute'], icon: 'settings', tab: 'settings', subroute: 'settings.sound', group: 'settings', child: true, rankBoost: 1.35 });
registerPage({ id: 'sub-set-voice', kind: 'page', title: 'Voice', aliases: ['tts', 'text to speech', 'text-to-speech', 'read aloud', 'read out loud', 'speak replies', 'narration', 'voice', 'speech', 'auto speak', 'dictation', 'voice input', 'microphone', 'mic', 'whisper', 'transcribe', 'transcription'], keywords: ['settings', 'voice', 'tts', 'speech', 'read', 'aloud', 'narration', 'rate', 'pitch', 'auto', 'accessibility', 'dictation', 'microphone', 'whisper', 'transcribe'], icon: 'settings', tab: 'settings', subroute: 'settings.voice', group: 'settings', child: true, rankBoost: 1.35 });
registerPage({ id: 'sub-set-ai', kind: 'page', title: 'AI / LLM', aliases: ['llm provider', 'ai model', 'agent settings', 'openai', 'anthropic', 'ollama', 'api key', 'model'], keywords: ['settings', 'ai', 'llm', 'model', 'provider', 'openai', 'anthropic', 'ollama', 'key'], icon: 'settings', tab: 'settings', subroute: 'settings.ai', group: 'settings', child: true, rankBoost: 1.3 });
registerPage({ id: 'sub-set-investor-eye', kind: 'page', title: 'Investor Eye', aliases: ['investor eye settings', 'world state sources', 'gdelt', 'usgs', 'firms', 'event sources'], keywords: ['settings', 'investor eye', 'world state', 'sources', 'gdelt', 'usgs', 'events'], icon: 'settings', tab: 'settings', subroute: 'settings.investor-eye', group: 'settings', child: true, rankBoost: 1.25 });
registerPage({ id: 'sub-set-economics', kind: 'page', title: 'Economics', aliases: ['economics settings', 'economics api', 'macro providers', 'fred', 'economics providers'], keywords: ['settings', 'economics', 'macro', 'providers', 'fred', 'calendar', 'indicators'], icon: 'settings', tab: 'settings', subroute: 'settings.economics', group: 'settings', child: true, rankBoost: 1.2 });
registerPage({ id: 'sub-set-market', kind: 'page', title: 'Market Data', aliases: ['market data settings', 'markets', 'exchanges', 'jdds data', 'screener providers', 'fundamentals api', 'market providers', 'crypto api'], keywords: ['settings', 'market', 'data', 'exchange', 'markets', 'screener', 'fundamentals', 'crypto'], icon: 'settings', tab: 'settings', subroute: 'settings.market', group: 'settings', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-set-news', kind: 'page', title: 'News', aliases: ['news settings', 'rss feeds', 'news providers', 'news api'], keywords: ['settings', 'news', 'feeds', 'rss', 'providers'], icon: 'settings', tab: 'settings', subroute: 'settings.news', group: 'settings', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-set-analytics', kind: 'page', title: 'Analytics', aliases: ['token usage', 'token consumption', 'usage analytics', 'llm analytics', 'agent analytics', 'cost', 'spend', 'tokens'], keywords: ['settings', 'analytics', 'usage', 'tokens', 'token', 'consumption', 'cost', 'spend', 'runs', 'metrics', 'stats', 'llm'], icon: 'settings', tab: 'settings', subroute: 'settings.analytics', group: 'settings', child: true, rankBoost: 1.2 });
registerPage({ id: 'sub-set-mcp', kind: 'page', title: 'MCP Servers', aliases: ['mcp', 'model context protocol', 'mcp servers', 'external tools', 'stdio servers', 'tool servers', 'plugins'], keywords: ['settings', 'mcp', 'servers', 'tools', 'external', 'stdio', 'integration', 'protocol'], icon: 'settings', tab: 'settings', subroute: 'settings.mcp', group: 'settings', child: true, rankBoost: 1.2 });
registerPage({ id: 'sub-set-sidebar', kind: 'page', title: 'Sidebar & Navigation', aliases: ['sidebar settings', 'shortcuts', 'navigation'], keywords: ['settings', 'sidebar', 'shortcuts', 'navigation'], icon: 'settings', tab: 'settings', subroute: 'settings.sidebar', group: 'settings', child: true });
registerPage({ id: 'sub-set-alerts', kind: 'page', title: 'Alerts', aliases: ['alert channels', 'alert settings', 'notifications'], keywords: ['settings', 'alerts', 'channels', 'notifications'], icon: 'settings', tab: 'settings', subroute: 'settings.alerts', group: 'settings', child: true });
registerPage({ id: 'sub-set-data', kind: 'page', title: 'Data & Storage', aliases: ['data hygiene', 'clear cache', 'reset', 'storage'], keywords: ['settings', 'data', 'hygiene', 'reset', 'cache', 'storage'], icon: 'settings', tab: 'settings', subroute: 'settings.data', group: 'settings', child: true });
registerPage({ id: 'sub-set-system', kind: 'page', title: 'System', aliases: ['integrations', 'system health', 'database', 'jdds status', 'internal'], keywords: ['settings', 'system', 'integrations', 'health', 'database', 'jdds'], icon: 'settings', tab: 'settings', subroute: 'settings.system', group: 'settings', child: true });

// Economic indicators (curated — full set arrives with Phase 2/5).
registerInstrument({ id: 'ind-nfp', kind: 'indicator', title: 'Non-Farm Payrolls', symbol: 'NFP', assetClass: 'indicator', market: 'US', aliases: ['nfp', 'non farm', 'non-farm', 'payrolls', 'jobs report', 'us jobs data', 'job report'], keywords: ['non farm payrolls', 'nfp', 'jobs', 'employment', 'payrolls', 'labor'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'NFP' }, rankBoost: 1.2 });
registerInstrument({ id: 'ind-cpi', kind: 'indicator', title: 'Consumer Price Index', symbol: 'CPI', assetClass: 'indicator', market: 'US', aliases: ['cpi', 'consumer price index', 'inflation'], keywords: ['cpi', 'inflation', 'consumer price index', 'prices'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'CPI' }, rankBoost: 1.2 });
registerInstrument({ id: 'ind-gdp', kind: 'indicator', title: 'Gross Domestic Product', symbol: 'GDP', assetClass: 'indicator', market: 'US', aliases: ['gdp', 'gross domestic product', 'economic growth'], keywords: ['gdp', 'growth', 'domestic product'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'GDP' }, rankBoost: 1.15 });
registerInstrument({ id: 'ind-fomc', kind: 'indicator', title: 'FOMC Rate Decision', symbol: 'FOMC', assetClass: 'indicator', market: 'US', aliases: ['fomc', 'federal reserve', 'fed rate', 'interest rate decision', 'monetary policy'], keywords: ['fomc', 'federal reserve', 'interest rate', 'monetary policy', 'fed'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'FOMC' }, rankBoost: 1.2 });
registerInstrument({ id: 'ind-ue', kind: 'indicator', title: 'Unemployment Rate', symbol: 'UNEMP', assetClass: 'indicator', market: 'US', aliases: ['unemployment', 'jobless', 'unemployment rate'], keywords: ['unemployment', 'jobless', 'labor market'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'Unemployment' }, rankBoost: 1.1 });
registerInstrument({ id: 'ind-pmi', kind: 'indicator', title: 'Purchasing Managers Index', symbol: 'PMI', assetClass: 'indicator', market: 'US', aliases: ['pmi', 'manufacturing', 'ism'], keywords: ['pmi', 'manufacturing', 'ism', 'activity'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', params: { focus: 'PMI' }, rankBoost: 1.1 });

// Major crypto instruments.
registerInstrument({ id: 'crypto-btc', kind: 'security', title: 'Bitcoin', symbol: 'BTC', assetClass: 'crypto', market: 'CRYPTO', aliases: ['bitcoin', 'btc', 'btcusd', 'btc-usd'], keywords: ['bitcoin', 'btc', 'crypto'], icon: 'chart', tab: 'chart', params: { symbol: 'BTC' }, rankBoost: 1.3 });
registerInstrument({ id: 'crypto-eth', kind: 'security', title: 'Ethereum', symbol: 'ETH', assetClass: 'crypto', market: 'CRYPTO', aliases: ['ethereum', 'eth', 'ethusd'], keywords: ['ethereum', 'eth', 'crypto'], icon: 'chart', tab: 'chart', params: { symbol: 'ETH' }, rankBoost: 1.25 });

// Major equities.
registerInstrument({ id: 'eq-aapl', kind: 'security', title: 'Apple Inc.', symbol: 'AAPL', assetClass: 'equity', market: 'US', aliases: ['apple', 'aapl', 'apple inc', 'apple stock', 'aapl stock'], keywords: ['apple', 'iphone', 'tech'], icon: 'chart', tab: 'chart', params: { symbol: 'AAPL' }, rankBoost: 1.3 });
registerInstrument({ id: 'eq-msft', kind: 'security', title: 'Microsoft Corp.', symbol: 'MSFT', assetClass: 'equity', market: 'US', aliases: ['microsoft', 'msft', 'microsoft stock'], keywords: ['microsoft', 'windows', 'azure', 'tech'], icon: 'chart', tab: 'chart', params: { symbol: 'MSFT' }, rankBoost: 1.25 });
registerInstrument({ id: 'eq-nvda', kind: 'security', title: 'NVIDIA Corp.', symbol: 'NVDA', assetClass: 'equity', market: 'US', aliases: ['nvidia', 'nvda', 'nvidia stock', 'nvda earnings'], keywords: ['nvidia', 'gpu', 'ai', 'semiconductor', 'earnings'], icon: 'chart', tab: 'chart', params: { symbol: 'NVDA' }, rankBoost: 1.3 });
registerInstrument({ id: 'eq-tsla', kind: 'security', title: 'Tesla Inc.', symbol: 'TSLA', assetClass: 'equity', market: 'US', aliases: ['tesla', 'tsla', 'tesla stock'], keywords: ['tesla', 'ev', 'electric'], icon: 'chart', tab: 'chart', params: { symbol: 'TSLA' }, rankBoost: 1.2 });
registerInstrument({ id: 'eq-amzn', kind: 'security', title: 'Amazon.com Inc.', symbol: 'AMZN', assetClass: 'equity', market: 'US', aliases: ['amazon', 'amzn', 'amazon stock'], keywords: ['amazon', 'aws', 'ecommerce'], icon: 'chart', tab: 'chart', params: { symbol: 'AMZN' }, rankBoost: 1.2 });
registerInstrument({ id: 'eq-googl', kind: 'security', title: 'Alphabet Inc.', symbol: 'GOOGL', assetClass: 'equity', market: 'US', aliases: ['google', 'alphabet', 'googl', 'goog'], keywords: ['google', 'alphabet', 'search', 'tech'], icon: 'chart', tab: 'chart', params: { symbol: 'GOOGL' }, rankBoost: 1.2 });

// Forex.
registerInstrument({ id: 'fx-eurusd', kind: 'instrument', title: 'Euro / US Dollar', symbol: 'EURUSD', assetClass: 'forex', market: 'US', aliases: ['eurusd', 'eur/usd', 'euro dollar'], keywords: ['euro', 'dollar', 'eurusd', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'EURUSD' }, rankBoost: 1.15 });
registerInstrument({ id: 'fx-gbpusd', kind: 'instrument', title: 'British Pound / US Dollar', symbol: 'GBPUSD', assetClass: 'forex', market: 'US', aliases: ['gbpusd', 'gbp/usd', 'pound dollar', 'cable'], keywords: ['pound', 'dollar', 'gbpusd', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'GBPUSD' }, rankBoost: 1.1 });
registerInstrument({ id: 'fx-usdjpy', kind: 'instrument', title: 'US Dollar / Japanese Yen', symbol: 'USDJPY', assetClass: 'forex', market: 'US', aliases: ['usdjpy', 'usd/jpy', 'dollar yen'], keywords: ['dollar', 'yen', 'usdjpy', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'USDJPY' }, rankBoost: 1.1 });
registerInstrument({ id: 'fx-usdchf', kind: 'instrument', title: 'US Dollar / Swiss Franc', symbol: 'USDCHF', assetClass: 'forex', market: 'US', aliases: ['usdchf', 'usd/chf', 'dollar franc'], keywords: ['dollar', 'franc', 'usdchf', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'USDCHF' }, rankBoost: 1.05 });
registerInstrument({ id: 'fx-audusd', kind: 'instrument', title: 'Australian Dollar / US Dollar', symbol: 'AUDUSD', assetClass: 'forex', market: 'US', aliases: ['audusd', 'aud/usd', 'aussie'], keywords: ['australian', 'dollar', 'audusd', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'AUDUSD' }, rankBoost: 1.05 });
registerInstrument({ id: 'fx-usdcad', kind: 'instrument', title: 'US Dollar / Canadian Dollar', symbol: 'USDCAD', assetClass: 'forex', market: 'US', aliases: ['usdcad', 'usd/cad', 'loonie'], keywords: ['dollar', 'canadian', 'usdcad', 'fx'], icon: 'chart', tab: 'chart', params: { symbol: 'USDCAD' }, rankBoost: 1.05 });

// Commodities.
registerInstrument({ id: 'com-gold', kind: 'instrument', title: 'Gold', symbol: 'XAUUSD', assetClass: 'commodity', market: 'US', aliases: ['gold', 'xau', 'xauusd', 'gold price'], keywords: ['gold', 'precious metal', 'xau'], icon: 'chart', tab: 'chart', params: { symbol: 'GOLD' }, rankBoost: 1.15 });
registerInstrument({ id: 'com-silver', kind: 'instrument', title: 'Silver', symbol: 'XAGUSD', assetClass: 'commodity', market: 'US', aliases: ['silver', 'xag', 'xagusd', 'silver price'], keywords: ['silver', 'precious metal', 'xag'], icon: 'chart', tab: 'chart', params: { symbol: 'SILVER' }, rankBoost: 1.1 });
registerInstrument({ id: 'com-oil', kind: 'instrument', title: 'Crude Oil (WTI)', symbol: 'CL', assetClass: 'commodity', market: 'US', aliases: ['oil', 'crude', 'wti', 'crude oil'], keywords: ['oil', 'crude', 'wti', 'energy'], icon: 'chart', tab: 'chart', params: { symbol: 'OIL' }, rankBoost: 1.15 });
registerInstrument({ id: 'com-brent', kind: 'instrument', title: 'Brent Crude Oil', symbol: 'BZ', assetClass: 'commodity', market: 'US', aliases: ['brent', 'brent oil'], keywords: ['brent', 'oil', 'energy'], icon: 'chart', tab: 'chart', params: { symbol: 'BRENT' }, rankBoost: 1.1 });
registerInstrument({ id: 'com-natgas', kind: 'instrument', title: 'Natural Gas', symbol: 'NG', assetClass: 'commodity', market: 'US', aliases: ['natural gas', 'natgas', 'ng'], keywords: ['natural gas', 'natgas', 'energy'], icon: 'chart', tab: 'chart', params: { symbol: 'NATGAS' }, rankBoost: 1.05 });
registerInstrument({ id: 'com-copper', kind: 'instrument', title: 'Copper', symbol: 'HG', assetClass: 'commodity', market: 'US', aliases: ['copper', 'hg'], keywords: ['copper', 'industrial metal'], icon: 'chart', tab: 'chart', params: { symbol: 'COPPER' }, rankBoost: 1.05 });

// Major indices — GENERATED from the index registry (`@/lib/indices`) so the
// palette can never drift from what the chart can actually fetch. The
// destination carries the CANONICAL ticker (`^GSPC`, `^KSE100`), not the
// TradingView-style alias: the old hand-written entries shipped `SPX`/`DJI`,
// which Yahoo has no instrument for, so selecting one produced "Symbol not
// found". Aliases/keywords come from the registry too, so "nifty", "ftse" and
// "KSE 100" all resolve.
//
// Deliberately NO generic 'index'/'indices' keyword: those are substrings of
// very short queries ("IN" matches "index"), so every index would flood the
// results and push the real `market-IN` country entry out of the top slice.
for (const def of INDEX_DEFS) {
  const slug = def.symbol.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || def.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const aliasList = [def.symbol, ...def.aliases, ...(def.searchOnly ?? [])].map(a => a.toLowerCase());
  registerInstrument({
    id: `idx-${slug}`,
    kind: 'instrument',
    title: def.name,
    symbol: def.symbol,
    assetClass: 'index',
    market: def.market,
    aliases: aliasList,
    keywords: [...new Set([def.name.toLowerCase(), ...aliasList])],
    icon: 'chart',
    tab: 'chart',
    // Only the symbol is passed: `params.market` would also switch the Market
    // Screener tab (see stock-chat's destination handler) as a side effect of
    // opening a chart. The index's own market and currency come from the
    // registry via `resolveIndex`, so the chart is correct without it.
    params: { symbol: def.symbol },
    rankBoost: 1.2,
  });
}

// ── Actions (command palette) ────────────────────────────────────────────────
registerAction({
  id: 'act-new-chat',
  verb: 'new',
  title: 'Start new chat',
  keywords: ['new chat', 'start chat', 'reset conversation', 'clear chat'],
  icon: 'bot',
  static: true,
  run: () => ({ tab: 'chat', params: { action: 'new-chat' } }),
});
registerAction({
  id: 'act-open-journal',
  verb: 'open',
  title: 'Open Trading Journal',
  keywords: ['open journal', 'open trading journal', 'journal'],
  icon: 'book',
  run: () => ({ tab: 'journal' }),
});
registerAction({
  id: 'act-open-econ-calendar',
  verb: 'show',
  title: "Show today's economic events",
  keywords: ['economic events today', 'today events', 'calendar today', 'events today'],
  icon: 'globe',
  run: () => ({ tab: 'economics', subroute: 'economics.calendar' }),
});
registerAction({
  id: 'act-open-portfolio',
  verb: 'open',
  title: 'Open Portfolio',
  keywords: ['open portfolio', 'my portfolio', 'portfolio'],
  icon: 'pie',
  run: () => ({ tab: 'portfolio' }),
});
registerAction({
  id: 'act-open-screener',
  verb: 'open',
  title: 'Open Market Discover',
  keywords: ['open screener', 'market screener', 'market discover', 'discover', 'screener', 'discovery'],
  icon: 'screen',
  run: () => ({ tab: 'discovery' }),
});
registerAction({
  id: 'act-open-news',
  verb: 'open',
  title: 'Open Market News',
  keywords: ['open news', 'market news', 'news'],
  icon: 'news',
  run: () => ({ tab: 'news' }),
});
registerAction({
  id: 'act-open-alerts',
  verb: 'open',
  title: 'Open Price Alerts',
  keywords: ['open alerts', 'price alerts', 'alerts'],
  icon: 'bell',
  run: () => ({ tab: 'alerts' }),
});
registerAction({
  id: 'act-open-settings',
  verb: 'open',
  title: 'Open Settings',
  keywords: ['open settings', 'settings', 'preferences'],
  icon: 'settings',
  run: () => ({ tab: 'settings' }),
});
registerAction({
  id: 'act-open-heatmap',
  verb: 'open',
  title: 'Open Market Bubbles',
  keywords: ['open heatmap', 'market bubbles', 'heatmap', 'bubbles'],
  icon: 'orbit',
  run: () => ({ tab: 'heatmap' }),
});
registerAction({
  id: 'act-open-market-workspace',
  verb: 'open',
  title: 'Open Chart Workspace',
  keywords: ['open chart workspace', 'open market workspace', 'multi chart', 'trading terminal', 'charts', 'workspace'],
  icon: 'candlestick',
  run: () => ({ tab: 'market-workspace' }),
});
registerAction({
  id: 'act-open-investor-eye',
  verb: 'open',
  title: "Open Investor Eye",
  keywords: ['open investor eye', 'investor eye', 'gods eye', 'world map', 'geopolitical map', 'global events'],
  icon: 'eye',
  run: () => ({ tab: 'investor-eye' }),
});

registerAction({
  id: 'act-open-skills',
  verb: 'open',
  title: 'Open Skills',
  keywords: ['open skills', 'agent skills', 'skill library', 'capabilities'],
  icon: 'skills',
  run: () => ({ tab: 'skills' }),
});
registerAction({
  id: 'act-open-memory',
  verb: 'open',
  title: 'Open Eclipse Memory',
  keywords: ['open memory', 'eclipse memory', 'agent memory', 'memory control room'],
  icon: 'memory',
  run: () => ({ tab: 'memory' }),
});

// ── Parameterized commands ───────────────────────────────────────────────────
// These are not matched as ordinary actions (they require an argument). The
// palette's `detectParamCommand` recognizes the verb and runs the side effect
// (create an alert / add to watchlist) before navigating.

registerAction({
  id: 'act-alert-symbol',
  verb: 'alert',
  title: 'Set price alert',
  keywords: ['alert', 'price alert', 'set alert', 'notify'],
  icon: 'bell',
  requiresArg: true,
  run: () => ({ tab: 'alerts' }),
});

registerAction({
  id: 'act-watch-symbol',
  verb: 'watch',
  title: 'Add to watchlist',
  keywords: ['watch', 'watchlist', 'add to watchlist', 'follow'],
  icon: 'pie',
  requiresArg: true,
  run: () => ({ tab: 'dashboard' }),
});

export { registerPage, registerInstrument, registerAction };
