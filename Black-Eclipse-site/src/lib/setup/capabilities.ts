// ── Capability map ──────────────────────────────────────────────────────────
// Users choose outcomes, not vendors. This maps the source catalog onto the
// seven data capabilities shown on the onboarding screen. Every source must
// belong to exactly one capability (asserted by a test), so nothing is
// invisible in setup and nothing appears twice.

import type { CapabilityDef, CapabilityId, SourceDef, SourceId } from "./types";
import { SOURCES } from "./source-catalog";

export const CAPABILITIES: CapabilityDef[] = [
  {
    id: "company",
    label: "Company research",
    description: "Filings, fundamentals, ratios and company facts.",
    included: ["sec"],
    connected: ["fmp", "finnhub"],
    advanced: [],
  },
  {
    id: "macro",
    label: "Macro & economics",
    description: "Rates, inflation, GDP and global indicators.",
    included: ["fred", "bea", "bls", "worldbank", "eurostat"],
    connected: ["tradingeconomics"],
    advanced: [],
  },
  {
    id: "events",
    label: "World events",
    description: "Geopolitical, seismic and thermal events for Investor Eye.",
    included: ["gdelt", "usgs", "firms"],
    connected: [],
    advanced: [],
  },
  {
    id: "prices",
    label: "Live prices & charts",
    description: "Quotes, charts and screening. Requires a provider you are licensed to use.",
    included: [],
    connected: ["polygon", "twelvedata", "alphavantage", "marketstack", "finnhub"],
    advanced: ["tradingview", "yfinance", "http", "browser", "scrapling"],
  },
  {
    id: "news",
    label: "News headlines",
    description: "Regulatory, central-bank and market headlines.",
    included: ["news-rss"],
    connected: ["finnhub"],
    advanced: [],
  },
  {
    id: "search",
    label: "Research web search",
    description: "Web sources for research and the agent.",
    included: [],
    connected: ["tavily", "brave", "exa", "serper"],
    advanced: ["duckduckgo"],
  },
  {
    id: "crypto",
    label: "Crypto",
    description: "Crypto prices and market data.",
    included: [],
    connected: ["coinmarketcap", "coingecko-paid"],
    advanced: ["binance", "kraken", "coingecko"],
  },
];

/** Chat is an AI choice, not a data source; it is rendered separately. */
export const DATA_CAPABILITIES = CAPABILITIES;

export const CAPABILITY_BY_ID: Record<string, CapabilityDef> = Object.fromEntries(
  CAPABILITIES.map((c) => [c.id, c]),
);

export function capabilityForSource(id: SourceId): CapabilityDef | undefined {
  return CAPABILITIES.find(
    (c) => c.included.includes(id) || c.connected.includes(id) || c.advanced.includes(id),
  );
}

export function sourcesForCapability(id: CapabilityId): SourceDef[] {
  const cap = CAPABILITY_BY_ID[id];
  if (!cap) return [];
  const ids: SourceId[] = [...cap.included, ...cap.connected, ...cap.advanced];
  return ids
    .map((sid) => SOURCES.find((s) => s.id === sid))
    .filter((s): s is SourceDef => Boolean(s));
}

export function capabilitySourceIds(): SourceId[] {
  return CAPABILITIES.flatMap((c) => [...c.included, ...c.connected, ...c.advanced]);
}
