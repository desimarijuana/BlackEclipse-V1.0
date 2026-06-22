import { ProviderAdapter, ProviderCapabilities, NormalizedCandle } from "./provider-interface";
import { YahooFinanceProvider } from "./yahoo-provider";

export class PSXProvider implements ProviderAdapter {
  name = "PSXProvider";
  private yahoo = new YahooFinanceProvider();

  getCapabilities(): ProviderCapabilities {
    return {
      supportsCrypto: false,
      supportsForex: false,
      supportsStocks: true,
      supportsCommodities: false,
      supportsIntraday: false,
      supportsDaily: true,
      supportsHistorical: true,
      supportsPakistanMarket: true,
      rateLimitPerMinute: 60,
      maxHistoryDays: 365 * 10,
      requiresApiKey: false,
      isFree: true,
      priority: 1, // High priority for PSX market, but cascades internally
    };
  }

  async fetchCandles(
    symbol: string,
    assetClass: string,
    timeframe: string,
    startDate: Date,
    endDate: Date
  ): Promise<NormalizedCandle[]> {
    // Primary/Secondary: Try Yahoo Finance with .KA suffix
    let cleanSymbol = symbol.replace("PSX:", "").trim();
    const yahooSymbol = `${cleanSymbol}.KA`;
    
    console.log(`[PSXProvider] Trying Yahoo fallback for PSX symbol: ${yahooSymbol}`);
    const candles = await this.yahoo.fetchCandles(yahooSymbol, "stock", timeframe, startDate, endDate);
    
    if (candles && candles.length > 0) {
      // Re-map the symbol back to original query symbol
      return candles.map(c => ({
        ...c,
        symbol,
        source: "PSX (Yahoo Fallback)"
      }));
    }

    // Third/Fourth: Fallback to manual uploaded data (handled in worker by DB check or manual upload CSV)
    console.log(`[PSXProvider] No online Yahoo Finance data found for ${yahooSymbol}. Awaiting manual CSV import.`);
    return [];
  }
}
