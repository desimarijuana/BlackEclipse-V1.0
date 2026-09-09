// ── Settings options as searchable entities ─────────────────────────────────
// Static list of settings/preferences the user can jump to. Registered as a
// search source so "dark mode", "LLM provider", "data sources" etc. resolve.

import type { SearchEntity } from './types';

const SETTINGS_OPTIONS: { title: string; keywords: string[] }[] = [
  { title: 'LLM Provider', keywords: ['llm', 'ai', 'model', 'openai', 'anthropic', 'gemini', 'ollama', 'provider'] },
  { title: 'Market Data Sources', keywords: ['data', 'sources', 'market data', 'yfinance', 'tradingview', 'scraper'] },
  { title: 'News Feeds', keywords: ['news', 'feeds', 'rss', 'sources'] },
  { title: 'App Preferences', keywords: ['preferences', 'app', 'theme', 'dark mode', 'light mode'] },
  { title: 'Data Hygiene', keywords: ['data', 'hygiene', 'clear', 'reset', 'cache'] },
  { title: 'Price Alerts', keywords: ['alerts', 'price', 'notifications', 'watch'] },
  { title: 'Trading Journal Settings', keywords: ['journal', 'trading', 'risk', 'account', 'currency'] },
  { title: 'Portfolio Settings', keywords: ['portfolio', 'fund', 'tax', 'fifo', 'lifo'] },
];

export function settingsEntities(): SearchEntity[] {
  return SETTINGS_OPTIONS.map((o, i) => ({
    id: `settings-${i}`,
    kind: 'page',
    title: o.title,
    keywords: o.keywords,
    icon: 'settings',
    destination: { tab: 'settings' },
    subtitle: 'Settings',
  }));
}
