export interface NormalizedCandle {
  symbol: string;
  assetClass: string;
  exchange?: string;
  timeframe: string;
  timestamp: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  source: string;
}

export interface ProviderCapabilities {
  supportsCrypto: boolean;
  supportsForex: boolean;
  supportsStocks: boolean;
  supportsCommodities: boolean;
  supportsIntraday: boolean;
  supportsDaily: boolean;
  supportsHistorical: boolean;
  supportsPakistanMarket: boolean;
  rateLimitPerMinute: number;
  maxHistoryDays: number;
  requiresApiKey: boolean;
  isFree: boolean;
  priority: number; // Lower means higher priority (e.g. 1 is high, 10 is low)
}

export interface ProviderAdapter {
  name: string;
  getCapabilities(): ProviderCapabilities;
  fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]>;
}
