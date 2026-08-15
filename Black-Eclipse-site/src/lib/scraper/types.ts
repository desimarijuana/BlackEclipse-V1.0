// price_scraper — types and failure classification.

export interface Quote {
  symbol: string;
  name?: string;
  price: number;
  changePct: number;
  marketCap?: number;
  volume?: number;
}

export type FetchStatus =
  | "ok"
  | "blocked" // 403/429, CAPTCHA, bot-wall
  | "structure_changed" // page parsed but expected selectors missing
  | "timeout" // request hung
  | "empty" // page loaded but no price found
  | "rate_limited" // per-domain limit hit
  | "network_error"; // DNS/connection failure

export interface FetchResult {
  status: FetchStatus;
  quote?: Quote;
  error?: string;
  source: string; // strategy id that produced this result
}

export interface DataSource {
  id: string; // 'http', 'browser', 'search', 'crypto'
  market: string; // 'US', 'PK', 'IN', 'CN', 'CRYPTO', ...
  symbol: string;
  getQuote(): Promise<FetchResult>;
}

export interface ScrapeOutcome {
  symbol: string;
  market: string;
  status: FetchStatus;
  source: string;
  price?: number;
  error?: string;
}

export type AssetType = "stocks" | "crypto" | "etfs";

export interface ScraperConfig {
  markets: string[]; // selected markets to scrape
  assetTypes: AssetType[];
  intervalMinutes: number;
}

/** Normalized view of an unknown thrown error, for failure classification. */
export interface ErrorLike {
  message?: string;
  name?: string;
  code?: string;
  response?: { status?: number };
  stdout?: string;
  stderr?: string;
}

export function toErrorLike(err: unknown): ErrorLike {
  if (err && typeof err === "object") return err as ErrorLike;
  return { message: String(err) };
}
