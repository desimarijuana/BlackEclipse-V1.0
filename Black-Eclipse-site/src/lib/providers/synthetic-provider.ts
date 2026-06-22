import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class SyntheticProvider implements ProviderAdapter {
  name = "Synthetic";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: true,
      supportsForex: true,
      supportsStocks: true,
      supportsCommodities: true,
      supportsIntraday: true,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: true,
      rateLimitPerMinute: 9999,
      maxHistoryDays: 365 * 10,
      requiresApiKey: false,
      isFree: true,
      priority: 10, // Lowest priority, default fallback
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    const candles: NormalizedCandle[] = [];
    let currentTime = new Date(startDate.getTime());
    let currentClose = 100.0; // Starting price

    // Map interval to milliseconds
    const intervalMsMap: Record<string, number> = {
      "1m": 60 * 1000,
      "3m": 3 * 60 * 1000,
      "5m": 5 * 60 * 1000,
      "15m": 15 * 60 * 1000,
      "30m": 30 * 60 * 1000,
      "1h": 60 * 60 * 1000,
      "4h": 4 * 60 * 60 * 1000,
      "1d": 24 * 60 * 60 * 1000,
      "1w": 7 * 24 * 60 * 60 * 1000,
      "1M": 30 * 24 * 60 * 60 * 1000
    };

    const stepMs = intervalMsMap[timeframe] || 24 * 60 * 60 * 1000;

    // Seed randomness from symbol string hash
    let hash = 0;
    for (let i = 0; i < symbol.length; i++) {
      hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
    }
    const seed = Math.abs(hash) % 1000 / 1000;
    currentClose = 50 + seed * 150;

    while (currentTime <= endDate) {
      // Random walk price changes
      const changePercent = (Math.random() - 0.49) * 0.02; // Slight upward bias
      const open = currentClose;
      const close = open * (1 + changePercent);
      const high = Math.max(open, close) * (1 + Math.random() * 0.01);
      const low = Math.min(open, close) * (1 - Math.random() * 0.01);
      const volume = Math.round(1000 + Math.random() * 10000);

      candles.push({
        symbol,
        assetClass,
        exchange: "synthetic",
        timeframe,
        timestamp: new Date(currentTime.getTime()),
        open,
        high,
        low,
        close,
        volume,
        source: "Synthetic",
      });

      currentClose = close;
      currentTime = new Date(currentTime.getTime() + stepMs);

      // Limit candles to prevent runaways (max 2000 per request)
      if (candles.length >= 2000) break;
    }

    return candles;
  }
}
