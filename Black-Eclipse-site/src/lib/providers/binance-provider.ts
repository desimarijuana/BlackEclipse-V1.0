import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";

export class BinanceProvider implements ProviderAdapter {
  name = "Binance";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: true,
      supportsForex: false,
      supportsStocks: false,
      supportsCommodities: false,
      supportsIntraday: true,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: false,
      rateLimitPerMinute: 1200,
      maxHistoryDays: 365 * 5, // 5 years
      requiresApiKey: false,
      isFree: true,
      priority: 1, // Primary for Crypto
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    // Map timeframes
    const intervalMap: Record<string, string> = {
      "1m": "1m",
      "3m": "3m",
      "5m": "5m",
      "15m": "15m",
      "30m": "30m",
      "1h": "1h",
      "4h": "4h",
      "1d": "1d",
      "1w": "1w",
      "1M": "1M"
    };

    const interval = intervalMap[timeframe] || "1d";
    let binanceSymbol = symbol.toUpperCase().trim();
    if (["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOT", "DOGE"].includes(binanceSymbol)) {
      binanceSymbol = `${binanceSymbol}USDT`;
    } else if (!binanceSymbol.endsWith("USDT") && !binanceSymbol.endsWith("BUSD") && !binanceSymbol.endsWith("BTC")) {
      binanceSymbol = `${binanceSymbol}USDT`;
    }

    const startTime = startDate.getTime();
    const endTime = endDate.getTime();
    const limit = 1000;

    const allCandles: NormalizedCandle[] = [];
    let currentStart = startTime;
    let iterations = 0;
    const maxIterations = 10; // Up to 10,000 candles per download request

    while (currentStart < endTime && iterations < maxIterations) {
      iterations++;
      const url = `https://api.binance.com/api/v3/klines?symbol=${binanceSymbol}&interval=${interval}&startTime=${currentStart}&endTime=${endTime}&limit=${limit}`;
      const res = await fetch(url);
      if (!res.ok) {
        if (allCandles.length > 0) break;
        throw new Error(`Binance API returned status ${res.status}`);
      }

      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        break;
      }

      const mapped = data.map((item: any) => ({
        symbol,
        assetClass,
        exchange: "binance",
        timeframe,
        timestamp: new Date(item[0]),
        open: parseFloat(item[1]),
        high: parseFloat(item[2]),
        low: parseFloat(item[3]),
        close: parseFloat(item[4]),
        volume: parseFloat(item[5]),
        source: "Binance",
      }));

      allCandles.push(...mapped);

      const lastTimestamp = data[data.length - 1][0];
      if (lastTimestamp <= currentStart || data.length < limit) {
        break;
      }
      currentStart = lastTimestamp + 1;
    }

    return allCandles;
  }
}
