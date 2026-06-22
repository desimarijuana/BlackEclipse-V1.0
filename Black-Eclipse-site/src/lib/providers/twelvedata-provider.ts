import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class TwelveDataProvider implements ProviderAdapter {
  name = "TwelveData";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: true,
      supportsForex: true,
      supportsStocks: true,
      supportsCommodities: true,
      supportsIntraday: true,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: false,
      rateLimitPerMinute: 8, // Free tier rate limits
      maxHistoryDays: 365,
      requiresApiKey: true,
      isFree: true,
      priority: 4,
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    const apiKey = process.env.TWELVEDATA_API_KEY;
    if (!apiKey) {
      return []; // Requires API key
    }

    const intervalMap: Record<string, string> = {
      "1m": "1min",
      "5m": "5min",
      "15m": "15min",
      "30m": "30min",
      "1h": "1h",
      "4h": "4h",
      "1d": "1day",
      "1w": "1week",
      "1M": "1month"
    };

    const interval = intervalMap[timeframe] || "1day";
    const startStr = startDate.toISOString().split("T")[0];
    const endStr = endDate.toISOString().split("T")[0];

    const url = `https://api.twelvedata.com/time_series?symbol=${symbol}&interval=${interval}&apikey=${apiKey}&start_date=${startStr}&end_date=${endStr}`;
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`TwelveData HTTP ${res.status}`);

      const data = await res.json();
      if (!data || !Array.isArray(data.values)) {
        return [];
      }

      return data.values.map((item: any) => ({
        symbol,
        assetClass,
        exchange: "twelvedata",
        timeframe,
        timestamp: new Date(item.datetime),
        open: parseFloat(item.open),
        high: parseFloat(item.high),
        low: parseFloat(item.low),
        close: parseFloat(item.close),
        volume: parseFloat(item.volume || "0"),
        source: "TwelveData",
      })).reverse(); // TwelveData returns newest first, reverse for asc chronological order
    } catch (err) {
      console.warn(`[TwelveData] Error fetching ${symbol}:`, err);
      return [];
    }
  }
}
