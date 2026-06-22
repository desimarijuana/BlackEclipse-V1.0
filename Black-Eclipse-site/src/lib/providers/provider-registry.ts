import { ProviderAdapter } from "./provider-interface";
import { BinanceProvider } from "./binance-provider";
import { YahooFinanceProvider } from "./yahoo-provider";
import { StooqProvider } from "./stooq-provider";
import { TwelveDataProvider } from "./twelvedata-provider";
import { AlphaVantageProvider } from "./alphavantage-provider";
import { FinnhubProvider } from "./finnhub-provider";
import { PSXProvider } from "./psx-provider";
import { SyntheticProvider } from "./synthetic-provider";

const providers: ProviderAdapter[] = [
  new BinanceProvider(),
  new YahooFinanceProvider(),
  new StooqProvider(),
  new TwelveDataProvider(),
  new AlphaVantageProvider(),
  new FinnhubProvider(),
  new PSXProvider(),
  new SyntheticProvider(),
];

export function getProviders(): ProviderAdapter[] {
  return providers;
}

export function getBestProvider(assetClass: string, symbol: string, timeframe: string): ProviderAdapter {
  const isPakistan = symbol.startsWith("PSX:") || symbol.endsWith(".KA");
  
  const filtered = providers.filter(p => {
    const caps = p.getCapabilities();
    
    // Asset class checks
    if (assetClass === "crypto" && !caps.supportsCrypto) return false;
    if (assetClass === "forex" && !caps.supportsForex) return false;
    if (assetClass === "commodity" && !caps.supportsCommodities) return false;
    if (assetClass === "stock" && !caps.supportsStocks) return false;
    
    // Country / exchange checks
    if (isPakistan && !caps.supportsPakistanMarket) return false;
    
    // Timeframe checks
    const isIntraday = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"].includes(timeframe);
    if (isIntraday && !caps.supportsIntraday) return false;
    if (!isIntraday && !caps.supportsDaily) return false;

    // Key configuration verification
    if (caps.requiresApiKey) {
      if (p.name === "TwelveData" && !process.env.TWELVEDATA_API_KEY) return false;
      if (p.name === "AlphaVantage" && !process.env.ALPHAVANTAGE_API_KEY) return false;
    }

    return true;
  });

  // Sort by priority (lower priority number first)
  filtered.sort((a, b) => a.getCapabilities().priority - b.getCapabilities().priority);

  // Fallback to Synthetic if none matched
  return filtered[0] || providers.find(p => p.name === "Synthetic") || providers[providers.length - 1];
}
