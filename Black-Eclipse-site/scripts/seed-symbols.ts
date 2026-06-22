import "dotenv/config";
import { prisma } from "../src/lib/prisma";

const SYMBOLS_SEED = [
  // --- CRYPTO ---
  { symbol: "BTCUSDT", displayName: "Bitcoin / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },
  { symbol: "ETHUSDT", displayName: "Ethereum / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },
  { symbol: "SOLUSDT", displayName: "Solana / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },
  { symbol: "BNBUSDT", displayName: "Binance Coin / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },
  { symbol: "XRPUSDT", displayName: "Ripple / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },
  { symbol: "DOGEUSDT", displayName: "Dogecoin / Tether", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global", currency: "USDT", timezone: "UTC", dataSource: "Binance" },

  // --- FOREX ---
  { symbol: "EURUSD", displayName: "EUR/USD", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "GBPUSD", displayName: "GBP/USD", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "USDJPY", displayName: "USD/JPY", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "JPY", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "USDCHF", displayName: "USD/CHF", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "CHF", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "AUDUSD", displayName: "AUD/USD", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "USDCAD", displayName: "USD/CAD", assetClass: "forex", market: "Forex", exchange: "Oanda", country: "Global", currency: "CAD", timezone: "UTC", dataSource: "YahooFinance" },

  // --- COMMODITIES ---
  { symbol: "XAUUSD", displayName: "Gold Spot / US Dollar", assetClass: "commodity", market: "Commodities", exchange: "NYMEX", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "XAGUSD", displayName: "Silver Spot / US Dollar", assetClass: "commodity", market: "Commodities", exchange: "NYMEX", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "USOIL", displayName: "Crude Oil (WTI)", assetClass: "commodity", market: "Commodities", exchange: "NYMEX", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "UKOIL", displayName: "Brent Crude Oil", assetClass: "commodity", market: "Commodities", exchange: "ICE", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },
  { symbol: "NATGAS", displayName: "Natural Gas", assetClass: "commodity", market: "Commodities", exchange: "NYMEX", country: "Global", currency: "USD", timezone: "UTC", dataSource: "YahooFinance" },

  // --- US STOCKS ---
  { symbol: "AAPL", displayName: "Apple Inc.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "MSFT", displayName: "Microsoft Corp.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "NVDA", displayName: "NVIDIA Corp.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "TSLA", displayName: "Tesla Inc.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "AMZN", displayName: "Amazon.com Inc.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "GOOGL", displayName: "Alphabet Inc. (Class A)", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },
  { symbol: "AMD", displayName: "Advanced Micro Devices", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US", currency: "USD", timezone: "EST", dataSource: "YahooFinance" },

  // --- PAKISTAN STOCK EXCHANGE ---
  { symbol: "PSX:HBL", displayName: "Habib Bank Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:UBL", displayName: "United Bank Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:MCB", displayName: "MCB Bank Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:OGDC", displayName: "Oil & Gas Development Company", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:PPL", displayName: "Pakistan Petroleum Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:PSO", displayName: "Pakistan State Oil", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:ENGRO", displayName: "Engro Corporation", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:HUBC", displayName: "Hub Power Company", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:LUCK", displayName: "Lucky Cement Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:MARI", displayName: "Mari Petroleum Company", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:SYS", displayName: "Systems Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },
  { symbol: "PSX:TRG", displayName: "TRG Pakistan Limited", assetClass: "stock", market: "Pakistan Stocks", exchange: "PSX", country: "Pakistan", currency: "PKR", timezone: "PKT", dataSource: "PSXProvider" },

  // --- UK STOCKS ---
  { symbol: "SHEL.L", displayName: "Shell plc", assetClass: "stock", market: "UK Stocks", exchange: "LSE", country: "UK", currency: "GBp", timezone: "GMT", dataSource: "YahooFinance" },
  { symbol: "BP.L", displayName: "BP plc", assetClass: "stock", market: "UK Stocks", exchange: "LSE", country: "UK", currency: "GBp", timezone: "GMT", dataSource: "YahooFinance" },

  // --- EUROPE STOCKS ---
  { symbol: "ASML", displayName: "ASML Holding N.V.", assetClass: "stock", market: "Europe Stocks", exchange: "EURONEXT", country: "Netherlands", currency: "EUR", timezone: "CET", dataSource: "YahooFinance" },
  { symbol: "SAP.DE", displayName: "SAP SE", assetClass: "stock", market: "Europe Stocks", exchange: "XETRA", country: "Germany", currency: "EUR", timezone: "CET", dataSource: "YahooFinance" },

  // --- INDIA STOCKS ---
  { symbol: "RELIANCE.NS", displayName: "Reliance Industries", assetClass: "stock", market: "India Stocks", exchange: "NSE", country: "India", currency: "INR", timezone: "IST", dataSource: "YahooFinance" },
  { symbol: "TCS.NS", displayName: "Tata Consultancy Services", assetClass: "stock", market: "India Stocks", exchange: "NSE", country: "India", currency: "INR", timezone: "IST", dataSource: "YahooFinance" },

  // --- GULF STOCKS ---
  { symbol: "ARAMCO.SR", displayName: "Saudi Aramco", assetClass: "stock", market: "Gulf Stocks", exchange: "TADAWUL", country: "Saudi Arabia", currency: "SAR", timezone: "AST", dataSource: "YahooFinance" },

  // --- ASIA STOCKS ---
  { symbol: "7203.T", displayName: "Toyota Motor Corp", assetClass: "stock", market: "Asia Stocks", exchange: "TSE", country: "Japan", currency: "JPY", timezone: "JST", dataSource: "YahooFinance" },
];

async function main() {
  console.log("Seeding Backtesting Asset Symbols Universe...");
  let count = 0;
  for (const sym of SYMBOLS_SEED) {
    try {
      await prisma.assetSymbol.upsert({
        where: {
          symbol_exchange_assetClass: {
            symbol: sym.symbol,
            exchange: sym.exchange,
            assetClass: sym.assetClass,
          }
        },
        update: {
          displayName: sym.displayName,
          market: sym.market,
          country: sym.country,
          currency: sym.currency,
          timezone: sym.timezone,
          dataSource: sym.dataSource,
          availableTimeframes: ["1m", "5m", "15m", "1h", "1d", "1w", "1M"],
          isActive: true
        },
        create: {
          symbol: sym.symbol,
          displayName: sym.displayName,
          assetClass: sym.assetClass,
          market: sym.market,
          exchange: sym.exchange,
          country: sym.country,
          currency: sym.currency,
          timezone: sym.timezone,
          dataSource: sym.dataSource,
          availableTimeframes: ["1m", "5m", "15m", "1h", "1d", "1w", "1M"],
          isActive: true,
          isBacktestEnabled: true,
        }
      });
      count++;
    } catch (e) {
      console.error(`Failed to upsert ${sym.symbol}:`, e);
    }
  }
  console.log(`Successfully seeded ${count} symbols into the Backtesting Symbol Universe.`);
  process.exit(0);
}

main().catch(err => {
  console.error("Error seeding symbols:", err);
  process.exit(1);
});
