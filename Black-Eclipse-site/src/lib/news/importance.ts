// ─── News importance ("high alert") scoring ──────────────────────────────────
// The feed is a stream; a trader needs a signal. This module answers ONE
// question, deterministically and explainably:
//
//   "How likely is this story to move price soon?"
//
// It is NOT a buy/sell recommendation. Direction comes from the sentiment
// label; confidence comes from source tier + cross-source corroboration.
// Every point added is recorded in `reasons` so the UI can show WHY a story
// is flagged instead of presenting an unexplained number.
//
// No network, no LLM, no randomness — pure function, cheap enough to score a
// few hundred rows per request.

export type NewsAlertLevel = "critical" | "high" | "medium" | "low";
export type NewsConfidence = "high" | "medium" | "low";
export type NewsDirection = "bullish" | "bearish" | "neutral";
export type NewsHorizon = "intraday" | "days" | "macro";

export interface ImportanceNewsInput {
  headline: string;
  summary?: string | null;
  /** Feed source tier: 1 = wires, 4 = blogs. */
  tier?: number | null;
  category?: string | null;
  region?: string | null;
  ticker?: string | null;
  sentiment?: string | null;
  timestamp: string | Date;
  /** Cross-source corroboration from the story cluser (1 = single outlet). */
  sourceCount?: number;
  clusterSources?: string[];
}

export interface ImportanceContext {
  /** Override "now" for deterministic tests. */
  now?: number;
  /** Symbols the user follows (watchlist). */
  watchlist?: readonly string[];
  /** Symbols the user actually holds (portfolio). */
  portfolio?: readonly string[];
}

export interface ImportanceResult {
  /** 0..100 — market-moving likelihood, never a price forecast. */
  score: number;
  level: NewsAlertLevel;
  /** Human-readable reasons, safe to render verbatim. */
  reasons: string[];
  /** Instruments/symbols this story most plausibly touches. */
  affected: string[];
  isBreaking: boolean;
  confidence: NewsConfidence;
  direction: NewsDirection;
  horizon: NewsHorizon;
  /** "What would change this read" — generic, honest, never advice. */
  invalidates: string[];
}

const TIER_POINTS: Record<number, number> = { 1: 30, 2: 20, 3: 10, 4: 2 };

/** Categories that routinely move indices/rates/FX. */
const HIGH_IMPACT_CATEGORIES = new Set([
  "CENTRAL BANKS", "INFLATION", "JOBS", "ECONOMIC", "GEOPOLITICS",
  "WAR", "TRADE", "REGULATORY", "ENERGY",
]);

/** Categories that matter but are narrower / more idiosyncratic. */
const MARKET_CATEGORIES = new Set([
  "MARKETS", "STOCKS", "BONDS", "FOREX", "CRYPTO", "COMMODITIES", "DEFENSE",
]);

/** Broad events with a macro transmission channel. */
const MACRO_KEYWORDS = [
  "rate decision", "rate hike", "rate cut", "interest rate", "fomc",
  "central bank", "ecb", "boj", "boe", "fed ", "cpi", "inflation",
  "nonfarm", "non-farm", "payroll", "unemployment", "gdp", "recession",
  "monetary policy", "quantitative", "stimulus", "austerity", "debt ceiling",
];

/** Company-level events that re-price a single name. */
const CORPORATE_KEYWORDS = [
  "earnings", "guidance", "profit warning", "bankruptcy", "default",
  "halted", "halt", "suspended", "delisted", "merger", "acquisition",
  "buyout", "takeover", "ipo", "dividend", "buyback", "fraud",
  "investigation", "recall", "resign", "ceo", "restatement", "short seller",
];

/** Geopolitical / supply shocks. */
const GEOPOLITICAL_KEYWORDS = [
  "sanctions", "sanction", "tariff", "embargo", "war", "invasion",
  "airstrike", "air strike", "ceasefire", "opec", "shipping", "blockade",
  "cyberattack", "nationalize", "coup", "martial law",
];

/** Market-structure / volatility events. */
const SHOCK_KEYWORDS = [
  "crash", "plunge", "selloff", "sell-off", "circuit breaker", "meltdown",
  "record high", "record low", "flash crash", "contagion", "bailout",
];

/** Headlines that are commentary rather than a new event. */
const ANALYSIS_RE =
  /^(why|what|how|when|where|who|here'?s|explained|analysis|opinion|preview|recap|outlook|stocks? to|things to|3 |5 |7 |10 )/i;

function includesAny(haystack: string, needles: readonly string[]): boolean {
  for (const n of needles) if (haystack.includes(n)) return true;
  return false;
}

/**
 * Common ticker → company-name aliases. Feeds often mention the company
 * ("Nvidia unveils…") without an enriched ticker, so a watchlist match must
 * also work on the name, not only on `item.ticker`.
 */
const TICKER_ALIASES: Record<string, string> = {
  NVDA: "nvidia", AAPL: "apple", MSFT: "microsoft", TSLA: "tesla",
  AMZN: "amazon", GOOGL: "google", META: "meta", NFLX: "netflix",
  AMD: "amd", INTC: "intel", ORCL: "oracle", AVGO: "broadcom",
  COIN: "coinbase", PLTR: "palantir", HOOD: "robinhood", SPY: "s&p",
  QQQ: "nasdaq", BTC: "bitcoin", ETH: "ethereum",
};

/** Does a watchlist/portfolio symbol appear in the story text? */
function mentionsSymbol(symbol: string, textUpper: string, textLower: string): boolean {
  if (!symbol) return false;
  const alias = TICKER_ALIASES[symbol];
  if (alias && textLower.includes(alias)) return true;
  const token = symbol.replace(/[^A-Z0-9.-]/g, "");
  if (!token) return false;
  return new RegExp(`\\b${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(textUpper);
}

function ageMinutes(timestamp: string | Date, now: number): number {
  const ts = timestamp instanceof Date ? timestamp.getTime() : Date.parse(timestamp);
  if (!Number.isFinite(ts)) return 0;
  return Math.max(0, (now - ts) / 60_000);
}

function levelFor(score: number): NewsAlertLevel {
  if (score >= 75) return "critical";
  if (score >= 55) return "high";
  if (score >= 38) return "medium";
  return "low";
}

function normalizeDirection(sentiment?: string | null): NewsDirection {
  const s = (sentiment || "").toLowerCase();
  if (s === "bullish") return "bullish";
  if (s === "bearish") return "bearish";
  return "neutral";
}

/**
 * Score one news item. Deterministic: same input + same `now` = same output.
 */
export function scoreNewsImportance(
  item: ImportanceNewsInput,
  context: ImportanceContext = {},
): ImportanceResult {
  const now = context.now ?? Date.now();
  const reasons: string[] = [];
  const affected: string[] = [];
  const watchlist = new Set((context.watchlist ?? []).map((s) => s.toUpperCase()));
  const portfolio = new Set((context.portfolio ?? []).map((s) => s.toUpperCase()));

  let score = 0;

  // 1. Source tier — a wire flash outranks an aggregator repost.
  const tier = typeof item.tier === "number" ? item.tier : 3;
  score += TIER_POINTS[tier] ?? 8;
  if (tier === 1) reasons.push("Tier-1 wire");
  else if (tier === 2) reasons.push("Tier-2 outlet");

  // 2. Corroboration — the same story from several independent outlets is
  //    far more likely to be real than one outlet's take.
  const sources = Math.max(1, item.sourceCount ?? 1);
  if (sources >= 4) {
    score += 18;
    reasons.push(`${sources} sources`);
  } else if (sources === 3) {
    score += 12;
    reasons.push("3 sources");
  } else if (sources === 2) {
    score += 7;
    reasons.push("2 sources");
  }

  // 3. Recency — a 4-hour-old scoop is context, not a trade trigger.
  const age = ageMinutes(item.timestamp, now);
  if (age <= 15) {
    score += 22;
    reasons.push("just in");
  } else if (age <= 60) {
    score += 16;
    reasons.push("fresh");
  } else if (age <= 180) {
    score += 10;
  } else if (age <= 720) {
    score += 5;
  } else if (age <= 1440) {
    score += 2;
  }

  // 4. Category — some desks move whole indices, others move one name.
  const category = (item.category || "").toUpperCase();
  if (HIGH_IMPACT_CATEGORIES.has(category)) {
    score += 16;
    reasons.push(category.toLowerCase());
  } else if (MARKET_CATEGORIES.has(category)) {
    score += 9;
  } else if (category) {
    score += 3;
  }

  // 5. Event keywords — a rate decision or a profit warning is the reason
  //    people trade, independent of the category label.
  const text = `${item.headline} ${item.summary || ""}`.toLowerCase();
  let keywordPoints = 0;
  if (includesAny(text, MACRO_KEYWORDS)) {
    keywordPoints += 14;
    reasons.push("macro release");
  }
  if (includesAny(text, GEOPOLITICAL_KEYWORDS)) {
    keywordPoints += 14;
    reasons.push("geopolitical risk");
  }
  if (includesAny(text, CORPORATE_KEYWORDS)) {
    keywordPoints += 10;
    reasons.push("corporate event");
  }
  if (includesAny(text, SHOCK_KEYWORDS)) {
    keywordPoints += 10;
    reasons.push("market shock");
  }
  score += Math.min(20, keywordPoints);

  // 6. Personal relevance — the highest-value signal for a real decision.
  // The enriched ticker is only one path: a feed can name the company without
  // a ticker, so match watchlist/portfolio symbols against the story text too.
  const textUpper = text.toUpperCase();
  const itemTicker = item.ticker ? item.ticker.toUpperCase() : null;
  const portfolioHits = [...portfolio].filter(
    (s) => s === itemTicker || mentionsSymbol(s, textUpper, text),
  );
  const watchlistHits = [...watchlist].filter(
    (s) => s === itemTicker || mentionsSymbol(s, textUpper, text),
  );

  const relevance = new Set<string>(affected);
  if (itemTicker) relevance.add(itemTicker);
  for (const s of portfolioHits) relevance.add(s);
  for (const s of watchlistHits) relevance.add(s);
  affected.push(...relevance);

  if (portfolioHits.length > 0) {
    score += 18;
    reasons.push(`affects your holding · ${portfolioHits[0]}`);
  } else if (watchlistHits.length > 0) {
    score += 12;
    reasons.push(`on your watchlist · ${watchlistHits[0]}`);
  } else if (itemTicker) {
    score += 8;
  }

  // 7. Penalties — commentary and unconfirmed low-tier noise.
  if (ANALYSIS_RE.test(item.headline.trim())) {
    score -= 12;
    reasons.push("analysis, not a new event");
  }
  if (tier >= 4 && sources <= 1) {
    score -= 8;
    reasons.push("single low-tier source");
  }
  if (age > 24 * 60) {
    score -= 10;
    reasons.push("stale");
  }

  score = Math.max(0, Math.min(100, Math.round(score)));

  const level = levelFor(score);
  const isBreaking = age <= 15 && score >= 55;

  // Confidence is about corroboration, NOT about how strongly we feel.
  const confidence: NewsConfidence =
    sources >= 3 || (tier === 1 && sources >= 2)
      ? "high"
      : sources >= 2 || tier <= 2
        ? "medium"
        : "low";

  const direction = normalizeDirection(item.sentiment);
  const horizon: NewsHorizon =
    includesAny(text, MACRO_KEYWORDS) || category === "CENTRAL BANKS" ||
    category === "INFLATION" || category === "JOBS" || category === "ECONOMIC"
      ? "macro"
      : isBreaking || includesAny(text, CORPORATE_KEYWORDS)
        ? "intraday"
        : "days";

  const invalidates: string[] = [
    "If the source retracts or materially corrects the story",
  ];
  if (confidence !== "low") {
    invalidates.push("If a second independent wire reports the opposite");
  }
  if (horizon === "macro") {
    invalidates.push("If the print lands near forecast and the move fades");
  } else if (affected.length > 0) {
    invalidates.push(`If ${affected[0]} reverses after the session opens`);
  }

  return {
    score,
    level,
    reasons,
    affected,
    isBreaking,
    confidence,
    direction,
    horizon,
    invalidates,
  };
}

/** Score a batch and sort strongest-first (ties: newest first). */
export function rankNewsImportance<T extends ImportanceNewsInput>(
  items: readonly T[],
  context: ImportanceContext = {},
): Array<T & { importance: ImportanceResult }> {
  return items
    .map((item) => ({ ...item, importance: scoreNewsImportance(item, context) }))
    .sort((a, b) => {
      const d = b.importance.score - a.importance.score;
      if (d !== 0) return d;
      return Date.parse(String(b.timestamp)) - Date.parse(String(a.timestamp));
    });
}

export const ALERT_LEVEL_RANK: Record<NewsAlertLevel, number> = {
  critical: 3,
  high: 2,
  medium: 1,
  low: 0,
};
