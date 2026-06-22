import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class StooqProvider implements ProviderAdapter {
  name = "Stooq";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: false,
      supportsForex: true,
      supportsStocks: true,
      supportsCommodities: true,
      supportsIntraday: false,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: false,
      rateLimitPerMinute: 30,
      maxHistoryDays: 365 * 20, // 20 years
      requiresApiKey: false,
      isFree: true,
      priority: 3,
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    const intervalMap: Record<string, string> = {
      "1d": "d",
      "1w": "w",
      "1M": "m"
    };

    const interval = intervalMap[timeframe];
    if (!interval) {
      return []; // Stooq only supports daily/weekly/monthly
    }

    let ticker = symbol.toUpperCase().trim();
    // Stooq tickers: e.g. AAPL.US, EURUSD, etc.
    if (assetClass === "stock") {
      if (!ticker.includes(".")) {
        ticker = `${ticker}.US`;
      }
    }

    const url = `https://stooq.com/q/d/l/?s=${ticker}&i=${interval}`;
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Stooq HTTP ${res.status}`);

      const csvText = await res.text();
      const lines = csvText.split("\n");
      const candles: NormalizedCandle[] = [];

      // Header format: Date,Open,High,Low,Close,Volume
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const parts = line.split(",");
        if (parts.length < 5) continue;

        const date = new Date(parts[0]);
        if (isNaN(date.getTime())) continue;

        if (date < startDate || date > endDate) continue;

        candles.push({
          symbol,
          assetClass,
          exchange: "stooq",
          timeframe,
          timestamp: date,
          open: parseFloat(parts[1]),
          high: parseFloat(parts[2]),
          low: parseFloat(parts[3]),
          close: parseFloat(parts[4]),
          volume: parts[5] ? parseFloat(parts[5]) : 0,
          source: "Stooq",
        });
      }

      // Sort by date ascending
      return candles.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
    } catch (err) {
      console.warn(`[StooqProvider] Failed to fetch data for ${ticker}:`, err);
      return [];
    }
  }
}
