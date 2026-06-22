import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class AlphaVantageProvider implements ProviderAdapter {
  name = "AlphaVantage";

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
      rateLimitPerMinute: 5,
      maxHistoryDays: 365,
      requiresApiKey: true,
      isFree: true,
      priority: 5,
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    const apiKey = process.env.ALPHAVANTAGE_API_KEY;
    if (!apiKey) return [];

    let func = "TIME_SERIES_DAILY";
    let keyStr = "Time Series (Daily)";

    if (timeframe === "1m" || timeframe === "5m" || timeframe === "15m" || timeframe === "30m" || timeframe === "1h") {
      func = "TIME_SERIES_INTRADAY";
      const intervalMap: Record<string, string> = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "60min"
      };
      const interval = intervalMap[timeframe];
      const url = `https://www.alphavantage.co/query?function=${func}&symbol=${symbol}&interval=${interval}&apikey=${apiKey}`;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`AlphaVantage HTTP ${res.status}`);
        const data = await res.json();
        const timeSeries = data[`Time Series (${interval})`] || data[`Time Series (Intraday)`];
        if (!timeSeries) return [];

        const candles: NormalizedCandle[] = [];
        for (const [timestamp, bar] of Object.entries(timeSeries)) {
          const date = new Date(timestamp);
          if (date < startDate || date > endDate) continue;

          const anyBar = bar as any;
          candles.push({
            symbol,
            assetClass,
            exchange: "alphavantage",
            timeframe,
            timestamp: date,
            open: parseFloat(anyBar["1. open"]),
            high: parseFloat(anyBar["2. high"]),
            low: parseFloat(anyBar["3. low"]),
            close: parseFloat(anyBar["4. close"]),
            volume: parseFloat(anyBar["5. volume"] || "0"),
            source: "AlphaVantage",
          });
        }
        return candles.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
      } catch (e) {
        return [];
      }
    } else {
      if (timeframe === "1w") {
        func = "TIME_SERIES_WEEKLY";
        keyStr = "Weekly Time Series";
      } else if (timeframe === "1M") {
        func = "TIME_SERIES_MONTHLY";
        keyStr = "Monthly Time Series";
      }

      const url = `https://www.alphavantage.co/query?function=${func}&symbol=${symbol}&apikey=${apiKey}`;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`AlphaVantage HTTP ${res.status}`);
        const data = await res.json();
        const timeSeries = data[keyStr];
        if (!timeSeries) return [];

        const candles: NormalizedCandle[] = [];
        for (const [timestamp, bar] of Object.entries(timeSeries)) {
          const date = new Date(timestamp);
          if (date < startDate || date > endDate) continue;

          const anyBar = bar as any;
          candles.push({
            symbol,
            assetClass,
            exchange: "alphavantage",
            timeframe,
            timestamp: date,
            open: parseFloat(anyBar["1. open"]),
            high: parseFloat(anyBar["2. high"]),
            low: parseFloat(anyBar["3. low"]),
            close: parseFloat(anyBar["4. close"]),
            volume: parseFloat(anyBar["5. volume"] || "0"),
            source: "AlphaVantage",
          });
        }
        return candles.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
      } catch (e) {
        return [];
      }
    }
  }
}
