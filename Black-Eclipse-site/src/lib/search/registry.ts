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

// ── Default registrations ────────────────────────────────────────────────────
// Pages.
registerPage({ id: 'page-dashboard', kind: 'page', title: 'Command Center', aliases: ['dashboard', 'command center', 'home', 'overview', 'workspace'], keywords: ['dashboard', 'command center', 'home', 'overview', 'workspace', 'widgets'], icon: 'dashboard', tab: 'dashboard', rankBoost: 1.15 });
registerPage({ id: 'page-market-workspace', kind: 'page', title: 'Market Workspace', aliases: ['market workspace', 'multi chart', 'charts', 'terminal', 'workspace', 'trading terminal', 'grid'], keywords: ['market workspace', 'multi chart', 'charts', 'terminal', 'grid', 'layout', 'linked charts'], icon: 'dashboard', tab: 'market-workspace', rankBoost: 1.2 });
registerPage({ id: 'page-chat', kind: 'page', title: 'ChatBot', aliases: ['chat', 'ai', 'assistant', 'ask ai'], keywords: ['chatbot', 'chat', 'conversation', 'ai'], icon: 'bot', tab: 'chat' });
registerPage({ id: 'page-screener', kind: 'page', title: 'Market Screener', aliases: ['screener', 'discovery', 'stocks', 'discover', 'screen'], keywords: ['screener', 'market', 'stocks', 'discovery'], icon: 'chart', tab: 'discovery' });
registerPage({ id: 'page-portfolio', kind: 'page', title: 'Portfolio', aliases: ['my portfolio', 'holdings', 'watchlist', 'positions'], keywords: ['portfolio', 'holdings', 'watchlist', 'positions'], icon: 'briefcase', tab: 'portfolio', rankBoost: 1.1 });
registerPage({ id: 'page-journal', kind: 'page', title: 'Trading Journal', aliases: ['journal', 'trading journal', 'my trades', 'trade log'], keywords: ['journal', 'trading', 'trades', 'log'], icon: 'book', tab: 'journal', rankBoost: 1.1 });
registerPage({ id: 'page-news', kind: 'page', title: 'Market News', aliases: ['news', 'bulletin', 'headlines'], keywords: ['news', 'market news', 'headlines'], icon: 'news', tab: 'news' });
registerPage({ id: 'page-heatmap', kind: 'page', title: 'Market Bubbles', aliases: ['heatmap', 'bubbles', 'market map', 'treemap'], keywords: ['heatmap', 'bubbles', 'treemap'], icon: 'orbit', tab: 'heatmap' });
registerPage({ id: 'page-economics', kind: 'page', title: 'Economics', aliases: ['economics', 'economic calendar', 'macro', 'calendar', 'events'], keywords: ['economics', 'macro', 'calendar', 'indicators'], icon: 'globe', tab: 'economics' });
registerPage({ id: 'page-alerts', kind: 'page', title: 'Price Alerts', aliases: ['alerts', 'price alerts', 'notifications'], keywords: ['alerts', 'price', 'notifications'], icon: 'bell', tab: 'alerts' });
registerPage({ id: 'page-settings', kind: 'page', title: 'Settings', aliases: ['settings', 'preferences', 'config', 'options'], keywords: ['settings', 'preferences', 'config'], icon: 'settings', tab: 'settings' });

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

// Major indices.
registerInstrument({ id: 'idx-spx', kind: 'instrument', title: 'S&P 500', symbol: 'SPX', assetClass: 'index', market: 'US', aliases: ['spx', 's&p 500', 's&p', 'sp500'], keywords: ['s&p 500', 'spx', 'index'], icon: 'chart', tab: 'chart', params: { symbol: 'SPX' }, rankBoost: 1.2 });
registerInstrument({ id: 'idx-ndx', kind: 'instrument', title: 'Nasdaq 100', symbol: 'NDX', assetClass: 'index', market: 'US', aliases: ['nasdaq', 'ndx', 'nasdaq 100'], keywords: ['nasdaq', 'ndx', 'index'], icon: 'chart', tab: 'chart', params: { symbol: 'NDX' }, rankBoost: 1.15 });
registerInstrument({ id: 'idx-dji', kind: 'instrument', title: 'Dow Jones Industrial Average', symbol: 'DJI', assetClass: 'index', market: 'US', aliases: ['dow', 'dji', 'dow jones'], keywords: ['dow', 'dji', 'index'], icon: 'chart', tab: 'chart', params: { symbol: 'DJI' }, rankBoost: 1.1 });
registerInstrument({ id: 'idx-rut', kind: 'instrument', title: 'Russell 2000', symbol: 'RUT', assetClass: 'index', market: 'US', aliases: ['russell', 'rut', 'russell 2000'], keywords: ['russell', 'rut', 'small cap'], icon: 'chart', tab: 'chart', params: { symbol: 'RUT' }, rankBoost: 1.05 });

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
  icon: 'briefcase',
  run: () => ({ tab: 'portfolio' }),
});
registerAction({
  id: 'act-open-screener',
  verb: 'open',
  title: 'Open Market Screener',
  keywords: ['open screener', 'market screener', 'screener', 'discovery'],
  icon: 'chart',
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
  title: 'Open Market Workspace',
  keywords: ['open market workspace', 'multi chart', 'trading terminal', 'charts', 'workspace'],
  icon: 'dashboard',
  run: () => ({ tab: 'market-workspace' }),
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
  icon: 'briefcase',
  requiresArg: true,
  run: () => ({ tab: 'dashboard' }),
});

export { registerPage, registerInstrument, registerAction };
