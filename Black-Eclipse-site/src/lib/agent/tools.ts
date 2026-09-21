// Research tools — the capabilities the agent can call during a research run.
// Each tool wraps existing BlackEclipse infrastructure (JDDS, scraper, RSS)
// and returns a plain-text result the LLM can reason over.

import { prisma } from "@/lib/db";
import { fetchQuoteWithFallback } from "@/lib/scraper/fetchers";
import { webSearch } from "@/lib/web-research";
import { DATASET_TOOLS } from "./dataset-tools";
import { INVESTOR_EYE_TOOLS } from "./investor-eye-tools";

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, { type: string; description: string }>;
    required?: string[];
  };
  execute: (args: Record<string, unknown>) => Promise<string>;
}

// News is served from JDDS (background-ingested NewsItem rows) — no live
// RSS fetching here, keeping agent runs fast and deterministic.

async function getPrice(symbol: string, market = "US"): Promise<string> {
  const result = await fetchQuoteWithFallback(symbol, market);
  if (result.status === "ok" && result.quote) {
    const q = result.quote;
    return [
      `Price for ${symbol} (${market}):`,
      `  Price: ${q.price}`,
      `  Change: ${q.changePct}%`,
      q.marketCap ? `  Market Cap: ${q.marketCap}` : null,
      q.volume ? `  Volume: ${q.volume}` : null,
      `  Source: ${result.source}`,
    ].filter(Boolean).join("\n");
  }
  return `Could not fetch price for ${symbol} (${market}). Status: ${result.status}. ${result.error || ""}`;
}

async function getNews(query: string): Promise<string> {
  const q = query.toLowerCase().trim();
  // Serve from JDDS (background-ingested) instead of fetching ~55 feeds live.
  const items = await prisma.newsItem.findMany({
    where: q
      ? {
          OR: [
            { headline: { contains: q } },
            { summary: { contains: q } },
          ],
        }
      : {},
    orderBy: { timestamp: "desc" },
    take: 8,
  });

  if (items.length === 0) {
    return `No news found matching "${query}".`;
  }

  return items.map((i) => {
    return `[${i.source}] (${i.sentiment}) ${i.headline}\n  ${(i.summary || "").slice(0, 200)}\n  ${i.url || ""}`;
  }).join("\n\n");
}

async function getFundamentals(symbol: string): Promise<string> {
  // JDDS stores symbols uppercase (BTC, AAPL). SQLite's Prisma connector does
  // not support `mode: "insensitive"`, so normalize the input to uppercase.
  const asset = await prisma.asset.findFirst({
    where: { symbol: symbol.toUpperCase() },
    include: { price: true, market: true },
  });

  if (!asset) {
    return `No asset "${symbol}" found in the JDDS universe. Try get_price to fetch live data, or check the symbol.`;
  }

  const lines = [
    `Fundamentals for ${asset.symbol} (${asset.name}):`,
    `  Sector: ${asset.sector || "N/A"}`,
    `  Industry: ${asset.industry || "N/A"}`,
    `  Security Type: ${asset.securityType || "N/A"}`,
    `  Asset Class: ${asset.assetClass || "N/A"}`,
    `  Market: ${asset.market.exchange} (${asset.market.country})`,
  ];
  if (asset.price) {
    lines.push(
      `  Price: ${asset.price.price}`,
      `  Change: ${asset.price.changePct}%`,
      asset.price.marketCap ? `  Market Cap: ${asset.price.marketCap}` : "",
      asset.price.volume ? `  Volume: ${asset.price.volume}` : ""
    );
  }
  return lines.filter(Boolean).join("\n");
}

async function getSourceHealth(): Promise<string> {
  const health = await prisma.sourceHealth.groupBy({
    by: ["source", "market"],
    _sum: { successCount: true, failCount: true },
    _max: { lastStatus: true },
  });
  if (health.length === 0) {
    return "No source health data recorded yet.";
  }
  return health.map((h) => {
    const ok = h._sum.successCount ?? 0;
    const fail = h._sum.failCount ?? 0;
    const rate = ok + fail > 0 ? Math.round((ok / (ok + fail)) * 100) : 0;
    return `  ${h.source} (${h.market}): ${ok} ok / ${fail} fail (${rate}% success, last: ${h._max.lastStatus})`;
  }).join("\n");
}

async function searchWeb(query: string): Promise<string> {
  // Delegates to the ONE shared web-research module (no second search system).
  const results = await webSearch(query, 5);
  if (results.length === 0) return `No web results parsed for "${query}".`;
  return results
    .map((r) => `${r.title}\n  ${r.snippet}\n  ${r.url}`)
    .join("\n\n");
}

export const TOOLS: ToolDefinition[] = [
  {
    name: "get_price",
    description: "Get the latest live price, change %, market cap and volume for a stock or crypto symbol.",
    parameters: {
      type: "object",
      properties: {
        symbol: { type: "string", description: "Ticker symbol, e.g. AAPL, SYS, BTC" },
        market: { type: "string", description: "Market: US, PK, IN, CRYPTO. Default US." },
      },
      required: ["symbol"],
    },
    execute: (a) => getPrice(String(a.symbol || ""), String(a.market || "US")),
  },
  {
    name: "get_news",
    description: "Get recent financial news headlines and summaries, optionally filtered by a keyword or ticker.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Optional keyword/ticker to filter news by, e.g. 'NVIDIA' or 'oil'." },
      },
    },
    execute: (a) => getNews(String(a.query || "")),
  },
  {
    name: "get_fundamentals",
    description: "Get fundamental profile of an asset from the JDDS universe: sector, industry, security type, market, and stored price data.",
    parameters: {
      type: "object",
      properties: {
        symbol: { type: "string", description: "Ticker symbol, e.g. AAPL, SYS" },
      },
      required: ["symbol"],
    },
    execute: (a) => getFundamentals(String(a.symbol || "")),
  },
  {
    name: "get_source_health",
    description: "Get the reliability/health of each data source (http, browser, crypto, scrapling) per market. Useful to know if live data is trustworthy.",
    parameters: {
      type: "object",
      properties: {},
    },
    execute: () => getSourceHealth(),
  },
  {
    name: "search_web",
    description: "Search the web for recent information, news, analyst opinions, or company details about a topic or ticker.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "The search query, e.g. 'PSX Systems Limited financial results 2025'" },
      },
      required: ["query"],
    },
    execute: (a) => searchWeb(String(a.query || "")),
  },
  // Operator-connected datasets (Universal Data Connector Layer). Read-only;
  // see `dataset-tools.ts`.
  ...DATASET_TOOLS,
  // Investor Eye world-state retrieval (the AI Analyst). Read-only; queries the
  // structured event/country/market/relationship data — see `investor-eye-tools.ts`.
  ...INVESTOR_EYE_TOOLS,
];

export function getTool(name: string): ToolDefinition | undefined {
  return TOOLS.find((t) => t.name === name);
}

export function toolSchemas() {
  return TOOLS.map((t) => ({
    type: "function",
    function: {
      name: t.name,
      description: t.description,
      parameters: t.parameters,
    },
  }));
}
