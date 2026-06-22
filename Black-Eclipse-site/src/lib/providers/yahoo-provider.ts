import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";
import YahooFinance from "yahoo-finance2";

const yahooFinance = new YahooFinance();

export class YahooFinanceProvider implements ProviderAdapter {
  name = "YahooFinance";

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: true,
      supportsForex: true,
      supportsStocks: true,
      supportsCommodities: true,
      supportsIntraday: true,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: true, // via Yahoo tickers like .KA
      rateLimitPerMinute: 60,
      maxHistoryDays: 365 * 10, // 10 years
      requiresApiKey: false,
      isFree: true,
      priority: 2,
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
      "1m": "1m",
      "5m": "5m",
      "15m": "15m",
      "30m": "30m",
      "1h": "1h",
      "1d": "1d",
      "1w": "1wk",
      "1M": "1mo"
    };

    const interval = intervalMap[timeframe] || "1d";

    // Symbol Normalization for Yahoo Finance
    let ticker = symbol.toUpperCase().trim();

    if (assetClass === "crypto") {
      if (!ticker.endsWith("-USD")) {
        ticker = ticker.replace("USDT", "-USD");
        if (!ticker.endsWith("-USD")) {
          ticker = `${ticker}-USD`;
        }
      }
    } else if (assetClass === "forex") {
      if (!ticker.endsWith("=X")) {
        ticker = `${ticker}=X`;
      }
    } else if (assetClass === "commodity") {
      const commMap: Record<string, string> = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "USOIL": "CL=F",
        "UKOIL": "BZ=F",
        "NATGAS": "NG=F",
        "COPPER": "HG=F",
      };
      if (commMap[ticker]) {
        ticker = commMap[ticker];
      }
    } else if (assetClass === "stock" && symbol.includes("PSX:")) {
      // PSX symbols on Yahoo are like HBL.KA
      ticker = ticker.replace("PSX:", "") + ".KA";
    }

    const queryOptions = {
      period1: Math.floor(startDate.getTime() / 1000),
      period2: Math.floor(endDate.getTime() / 1000),
      interval: interval as any,
    };

    try {
      const chartResult = await yahooFinance.chart(ticker, queryOptions);
      const results = chartResult.quotes || [];

      return results
        .filter(bar => 
          bar.close !== null && bar.close !== undefined &&
          bar.open !== null && bar.open !== undefined &&
          bar.high !== null && bar.high !== undefined &&
          bar.low !== null && bar.low !== undefined
        )
        .map(bar => ({
          symbol,
          assetClass,
          exchange: chartResult.meta.exchangeName || "yahoo",
          timeframe,
          timestamp: new Date(bar.date),
          open: bar.open!,
          high: bar.high!,
          low: bar.low!,
          close: bar.close!,
          volume: bar.volume || 0,
          source: "YahooFinance",
        }));
    } catch (err: any) {
      console.warn(`[YahooFinanceProvider] Failed to fetch chart for ${ticker}: ${err.message}`);
      // Return empty array instead of throwing to allow cascading fallbacks
      return [];
    }
  }
}
