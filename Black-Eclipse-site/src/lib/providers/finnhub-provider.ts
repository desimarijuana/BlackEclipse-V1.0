import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class FinnhubProvider implements ProviderAdapter {
  name = "Finnhub";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: true,
      supportsForex: false,
      supportsStocks: true,
      supportsCommodities: false,
      supportsIntraday: true,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: false,
      rateLimitPerMinute: 60,
      maxHistoryDays: 365,
      requiresApiKey: true,
      isFree: true,
      priority: 6,
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    const token = process.env.FINNHUB_TOKEN || process.env.FINNHUB_API_KEY || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";
    if (!token) return [];

    const resolutionMap: Record<string, string> = {
      "1m": "1",
      "5m": "5",
      "15m": "15",
      "30m": "30",
      "1h": "60",
      "1d": "D",
      "1w": "W",
      "1M": "M"
    };

    const resolution = resolutionMap[timeframe] || "D";
    const from = Math.floor(startDate.getTime() / 1000);
    const to = Math.floor(endDate.getTime() / 1000);

    const url = `https://finnhub.io/api/v1/stock/candle?symbol=${symbol.toUpperCase()}&resolution=${resolution}&from=${from}&to=${to}&token=${token}`;
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Finnhub HTTP ${res.status}`);
      const data = await res.json();

      if (data.s !== "ok" || !Array.isArray(data.c)) {
        return [];
      }

      const candles: NormalizedCandle[] = [];
      for (let i = 0; i < data.c.length; i++) {
        candles.push({
          symbol,
          assetClass,
          exchange: "finnhub",
          timeframe,
          timestamp: new Date(data.t[i] * 1000),
          open: parseFloat(data.o[i]),
          high: parseFloat(data.h[i]),
          low: parseFloat(data.l[i]),
          close: parseFloat(data.c[i]),
          volume: data.v ? parseFloat(data.v[i]) : 0,
          source: "Finnhub",
        });
      }

      return candles;
    } catch (e) {
      console.warn(`[FinnhubProvider] Error fetching ${symbol}:`, e);
      return [];
    }
  }
}
