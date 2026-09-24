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
registerPage({ id: 'page-dashboard', kind: 'page', title: 'Command Center', aliases: ['dashboard', 'command center', 'home', 'overview', 'workspace'], keywords: ['dashboard', 'command center', 'home', 'overview', 'workspace', 'widgets'], icon: 'dashboard', tab: 'dashboard', rankBoost: 1.15 });
registerPage({ id: 'page-market-workspace', kind: 'page', title: 'Chart Workspace', aliases: ['chart workspace', 'market workspace', 'multi chart', 'charts', 'terminal', 'workspace', 'trading terminal', 'grid'], keywords: ['chart workspace', 'market workspace', 'multi chart', 'charts', 'terminal', 'grid', 'layout', 'linked charts'], icon: 'candlestick', tab: 'market-workspace', rankBoost: 1.2 });
registerPage({ id: 'page-investor-eye', kind: 'page', title: 'Investor Eye', aliases: ['investor eye', 'gods eye', 'god\'s eye', 'world map', 'geopolitical', 'geopolitics', 'global state', 'world state', 'events map'], keywords: ['investor eye', 'gods eye', 'world', 'map', 'geopolitical', 'events', 'global', 'geopolitics', 'intelligence'], icon: 'eye', tab: 'investor-eye', rankBoost: 1.25 });
registerPage({ id: 'page-chat', kind: 'page', title: 'ChatBot', aliases: ['chat', 'ai', 'assistant', 'ask ai'], keywords: ['chatbot', 'chat', 'conversation', 'ai'], icon: 'bot', tab: 'chat' });
registerPage({ id: 'page-screener', kind: 'page', title: 'Market Screener', aliases: ['screener', 'discovery', 'stocks', 'discover', 'screen'], keywords: ['screener', 'market', 'stocks', 'discovery'], icon: 'screen', tab: 'discovery' });
registerPage({ id: 'page-portfolio', kind: 'page', title: 'Portfolio', aliases: ['my portfolio', 'holdings', 'watchlist', 'positions'], keywords: ['portfolio', 'holdings', 'watchlist', 'positions'], icon: 'pie', tab: 'portfolio', rankBoost: 1.1 });
registerPage({ id: 'page-journal', kind: 'page', title: 'Trading Journal', aliases: ['journal', 'trading journal', 'my trades', 'trade log'], keywords: ['journal', 'trading', 'trades', 'log'], icon: 'book', tab: 'journal', rankBoost: 1.1 });
registerPage({ id: 'page-news', kind: 'page', title: 'Market News', aliases: ['news', 'bulletin', 'headlines'], keywords: ['news', 'market news', 'headlines'], icon: 'news', tab: 'news' });
registerPage({ id: 'page-heatmap', kind: 'page', title: 'Market Bubbles', aliases: ['heatmap', 'bubbles', 'market map', 'treemap'], keywords: ['heatmap', 'bubbles', 'treemap'], icon: 'orbit', tab: 'heatmap' });
registerPage({ id: 'page-economics', kind: 'page', title: 'Economics', aliases: ['economics', 'economic calendar', 'macro', 'calendar', 'events'], keywords: ['economics', 'macro', 'calendar', 'indicators'], icon: 'globe', tab: 'economics' });
registerPage({ id: 'page-alerts', kind: 'page', title: 'Price Alerts', aliases: ['alerts', 'price alerts', 'notifications'], keywords: ['alerts', 'price', 'notifications'], icon: 'bell', tab: 'alerts' });
registerPage({ id: 'page-skills', kind: 'page', title: 'Skills', aliases: ['skills', 'agent skills', 'skill library', 'capabilities'], keywords: ['skills', 'agent', 'library', 'capabilities', 'tools'], icon: 'skills', tab: 'skills', rankBoost: 1.1 });
registerPage({ id: 'page-memory', kind: 'page', title: 'Eclipse Memory', aliases: ['memory', 'eclipse memory', 'agent memory', 'memory control room'], keywords: ['memory', 'eclipse memory', 'agent', 'persistence', 'audit'], icon: 'memory', tab: 'memory', rankBoost: 1.1 });
registerPage({ id: 'page-settings', kind: 'page', title: 'Settings', aliases: ['settings', 'preferences', 'config', 'options'], keywords: ['settings', 'preferences', 'config'], icon: 'settings', tab: 'settings' });

// Market Regime — not a tab. Selecting it opens the top-bar Market Regime panel
// (the shell handles the `action: 'open-regime'` param and returns before any tab
// switch). Discoverable by searching "market regime", "risk on", "sentiment", etc.
registerPage({ id: 'page-market-regime', kind: 'page', title: 'Market Regime', aliases: ['market regime', 'regime', 'risk on', 'risk off', 'risk-on', 'risk-off', 'market sentiment', 'market breadth', 'volatility regime', 'aurora'], keywords: ['market regime', 'regime', 'sentiment', 'risk on', 'risk off', 'breadth', 'volatility', 'vix', 'aurora', 'macro'], icon: 'activity', tab: 'dashboard', params: { action: 'open-regime' }, rankBoost: 1.2 });

// Skills sub-pages — so the Learning Queue and draft review are reachable from
// an originating chat run ("Learn from this run" → Learning Queue), not only by
// opening the Skills tab and hunting for the right sub-tab.
registerPage({ id: 'sub-skills-library', kind: 'page', title: 'Skill Library', aliases: ['skill library', 'skills'], keywords: ['skills', 'library'], icon: 'skills', tab: 'skills', subroute: 'skills.library', group: 'skills', child: true });
registerPage({ id: 'sub-skills-learning', kind: 'page', title: 'Learning Queue', aliases: ['learning queue', 'learning candidates', 'learn from run', 'candidates'], keywords: ['learning', 'candidates', 'queue', 'learn'], icon: 'skills', tab: 'skills', subroute: 'skills.learning', group: 'skills', child: true, rankBoost: 1.15 });
registerPage({ id: 'sub-skills-evaluation', kind: 'page', title: 'Evaluation Center', aliases: ['evaluation', 'skill evaluation'], keywords: ['evaluation', 'skills'], icon: 'skills', tab: 'skills', subroute: 'skills.evaluation', group: 'skills', child: true });
registerPage({ id: 'sub-skills-activity', kind: 'page', title: 'Execution Activity', aliases: ['skill activity', 'skill executions'], keywords: ['skills', 'activity', 'executions'], icon: 'skills', tab: 'skills', subroute: 'skills.activity', group: 'skills', child: true });
// Eclipse Memory sub-pages.
registerPage({ id: 'sub-memory-explorer', kind: 'page', title: 'Memory Explorer', aliases: ['memory explorer', 'saved memory'], keywords: ['memory', 'explorer'], icon: 'memory', tab: 'memory', subroute: 'memory.explorer', group: 'memory', child: true });
registerPage({ id: 'sub-memory-activity', kind: 'page', title: 'Memory Activity', aliases: ['memory activity', 'retrieval diagnostics'], keywords: ['memory', 'activity', 'retrieval'], icon: 'memory', tab: 'memory', subroute: 'memory.activity', group: 'memory', child: true });
registerPage({ id: 'sub-memory-health', kind: 'page', title: 'Memory Health', aliases: ['memory health', 'database identity'], keywords: ['memory', 'health', 'database'], icon: 'memory', tab: 'memory', subroute: 'memory.health', group: 'memory', child: true });

// ── Sub-pages ────────────────────────────────────────────────────────────────
// Every internal view that used to be unreachable (the shell ignored
// `Destination.subroute`). These are real destinations: each `subroute` is
// consumed by its screen via the `useSubroute` hook. Grouped by parent tab so
// the palette's "Go to" list nests them instead of flattening the top level.

// Economics — section tabs + the indicator-focused calendar.
registerPage({ id: 'sub-econ-overview', kind: 'page', title: 'Overview', aliases: ['economics overview', 'macro snapshot'], keywords: ['economics', 'overview', 'snapshot', 'macro'], icon: 'globe', tab: 'economics', subroute: 'economics.overview', group: 'economics', child: true });
registerPage({ id: 'sub-econ-calendar', kind: 'page', title: 'Calendar', aliases: ['economic calendar', 'econ calendar', 'releases'], keywords: ['economics', 'calendar', 'events', 'releases'], icon: 'globe', tab: 'economics', subroute: 'economics.calendar', group: 'economics', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-econ-explorer', kind: 'page', title: 'Time-series Explorer', aliases: ['econ explorer', 'time series', 'macro data'], keywords: ['economics', 'explorer', 'time series', 'series'], icon: 'globe', tab: 'economics', subroute: 'economics.explorer', group: 'economics', child: true });

// Journal — one row per sub-tab.
registerPage({ id: 'sub-journal-overview', kind: 'page', title: 'Overview', aliases: ['journal overview'], keywords: ['journal', 'overview'], icon: 'book', tab: 'journal', subroute: 'journal.overview', group: 'journal', child: true });
registerPage({ id: 'sub-journal-calendar', kind: 'page', title: 'Calendar', aliases: ['journal calendar'], keywords: ['journal', 'calendar'], icon: 'book', tab: 'journal', subroute: 'journal.calendar', group: 'journal', child: true });
registerPage({ id: 'sub-journal-trades', kind: 'page', title: 'Trades', aliases: ['journal trades', 'my trades', 'trade log'], keywords: ['journal', 'trades', 'log'], icon: 'book', tab: 'journal', subroute: 'journal.trades', group: 'journal', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-journal-analytics', kind: 'page', title: 'Analytics', aliases: ['journal analytics', 'performance', 'stats'], keywords: ['journal', 'analytics', 'performance', 'stats'], icon: 'book', tab: 'journal', subroute: 'journal.analytics', group: 'journal', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-journal-psychology', kind: 'page', title: 'Psychology', aliases: ['journal psychology', 'emotions'], keywords: ['journal', 'psychology', 'emotions'], icon: 'book', tab: 'journal', subroute: 'journal.psychology', group: 'journal', child: true });
registerPage({ id: 'sub-journal-playbook', kind: 'page', title: 'Playbook', aliases: ['journal playbook', 'setups', 'strategies'], keywords: ['journal', 'playbook', 'setups', 'strategy'], icon: 'book', tab: 'journal', subroute: 'journal.playbook', group: 'journal', child: true });
registerPage({ id: 'sub-journal-reviews', kind: 'page', title: 'Reviews', aliases: ['journal reviews'], keywords: ['journal', 'reviews'], icon: 'book', tab: 'journal', subroute: 'journal.reviews', group: 'journal', child: true });
registerPage({ id: 'sub-journal-insights', kind: 'page', title: 'Insights', aliases: ['journal insights'], keywords: ['journal', 'insights'], icon: 'book', tab: 'journal', subroute: 'journal.insights', group: 'journal', child: true });

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
//   General · Customization · Aurora · AI / LLM · Investor Eye · Market Data ·
//   News · Charts · Sidebar & Navigation · Alerts · Data & Storage · System.
registerPage({ id: 'sub-set-general', kind: 'page', title: 'General', aliases: ['appearance', 'theme', 'dark mode', 'preferences', 'general', 'currency', 'timezone', 'refresh'], keywords: ['settings', 'general', 'appearance', 'theme', 'currency', 'timezone'], icon: 'settings', tab: 'settings', subroute: 'settings.general', group: 'settings', child: true, rankBoost: 1.1 });
registerPage({ id: 'sub-set-customization', kind: 'page', title: 'Customization', aliases: ['language', 'translate', 'locale', 'accessibility', 'a11y', 'reduce motion', 'high contrast', 'text size', 'font size', 'rtl', 'theme', 'branding', 'logo', 'favicon', 'app name', 'brand color', 'preset', 'density', 'radius', 'font', 'typography'], keywords: ['settings', 'customization', 'theme', 'branding', 'logo', 'favicon', 'font', 'colors', 'brand color', 'language', 'accessibility', 'motion', 'contrast', 'text size'], icon: 'settings', tab: 'settings', subroute: 'settings.customization', group: 'settings', child: true, rankBoost: 1.2 });
registerPage({ id: 'sub-set-sound', kind: 'page', title: 'Sound', aliases: ['sound', 'sounds', 'audio', 'ui sounds', 'volume', 'click sound', 'tick sound', 'toggle sound', 'notification sound', 'sound pack', 'mute sounds', 'silence'], keywords: ['settings', 'sound', 'sounds', 'audio', 'volume', 'click', 'tick', 'toggle', 'notification', 'feedback', 'pack', 'mute'], icon: 'settings', tab: 'settings', subroute: 'settings.sound', group: 'settings', child: true, rankBoost: 1.35 });
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
  title: 'Open Market Screener',
  keywords: ['open screener', 'market screener', 'screener', 'discovery'],
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
