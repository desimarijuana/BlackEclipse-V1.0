// Research tools — the capabilities the agent can call during a research run.
// Each tool wraps existing BlackEclipse infrastructure (JDDS, scraper, RSS)
// and returns a plain-text result the LLM can reason over.

import { prisma } from "@/lib/db";
import { fetchQuoteWithFallback } from "@/lib/scraper/fetchers";
import { guessSentiment } from "@/lib/sentiment";
import { getNewsFeeds } from "@/lib/settings";
import Parser from "rss-parser";

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

// Shared source of truth with the market news page — uses the full
// ~55-feed catalog from settings (tier 1-4) so the agent sees the same news.
const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const parser = new Parser({
  requestOptions: {
    headers: { "User-Agent": BROWSER_UA, Accept: "application/rss+xml, application/xml, text/xml, */*" },
  },
});

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
  const q = query.toLowerCase();
  const feeds = await getNewsFeeds();
  const results = await Promise.allSettled(
    feeds.filter((f) => f.enabled).map(async (feed) => {
      const parsed = await parser.parseURL(feed.url);
      return (parsed.items || []).slice(0, 15).map((item) => ({
        source: feed.source,
        title: item.title || "",
        summary: (item.contentSnippet || item.content || "").slice(0, 200),
        url: item.link,
      }));
    })
  );

  const items: { source: string; title: string; summary: string; url?: string }[] = [];
  for (const r of results) if (r.status === "fulfilled") items.push(...r.value);

  const filtered = q
    ? items.filter((i) => `${i.title} ${i.summary}`.toLowerCase().includes(q))
    : items;

  if (filtered.length === 0) {
    return `No news found matching "${query}".`;
  }

  return filtered.slice(0, 8).map((i) => {
    const sentiment = guessSentiment(`${i.title} ${i.summary}`);
    return `[${i.source}] (${sentiment}) ${i.title}\n  ${i.summary}\n  ${i.url || ""}`;
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
  // Lightweight web search via DuckDuckGo HTML (no key required).
  try {
    const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return `Web search failed (HTTP ${res.status}).`;
    const html = await res.text();
    // Extract result titles + snippets from the HTML result blocks.
    const results: string[] = [];
    const blockRe = /<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)<\/a>/g;
    let m: RegExpExecArray | null;
    let count = 0;
    while ((m = blockRe.exec(html)) !== null && count < 5) {
      const href = m[1];
      const title = m[2].replace(/<[^>]+>/g, "").trim();
      const snippet = m[3].replace(/<[^>]+>/g, "").trim();
      results.push(`${title}\n  ${snippet}\n  ${href}`);
      count++;
    }
    if (results.length === 0) {
      return `No web results parsed for "${query}".`;
    }
    return results.join("\n\n");
  } catch (err) {
    return `Web search error: ${err instanceof Error ? err.message : String(err)}`;
  }
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
