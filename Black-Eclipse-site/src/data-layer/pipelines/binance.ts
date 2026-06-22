import { prisma } from "@/lib/prisma";

// List of major crypto base symbols to track and categorise
export const CORE_CRYPTO = [
  // Tier 1 - Mega Cap
  { symbol: "BTC", name: "Bitcoin", sector: "Layer 1" },
  { symbol: "ETH", name: "Ethereum", sector: "Layer 1" },
  { symbol: "BNB", name: "Binance Coin", sector: "Exchange Tokens" },
  { symbol: "SOL", name: "Solana", sector: "Layer 1" },
  { symbol: "XRP", name: "Ripple", sector: "Payment" },
  { symbol: "USDC", name: "USD Coin", sector: "Stablecoins" },
  { symbol: "DOGE", name: "Dogecoin", sector: "Meme Coins" },
  { symbol: "ADA", name: "Cardano", sector: "Layer 1" },
  { symbol: "TRX", name: "TRON", sector: "Layer 1" },
  { symbol: "AVAX", name: "Avalanche", sector: "Layer 1" },
  { symbol: "TON", name: "Toncoin", sector: "Layer 1" },
  { symbol: "LINK", name: "Chainlink", sector: "DeFi" },
  { symbol: "SHIB", name: "Shiba Inu", sector: "Meme Coins" },
  { symbol: "DOT", name: "Polkadot", sector: "Layer 1" },
  { symbol: "BCH", name: "Bitcoin Cash", sector: "Payment" },
  { symbol: "NEAR", name: "Near Protocol", sector: "Layer 1" },
  { symbol: "LTC", name: "Litecoin", sector: "Payment" },
  { symbol: "UNI", name: "Uniswap", sector: "DeFi" },
  { symbol: "SUI", name: "Sui", sector: "Layer 1" },
  { symbol: "APT", name: "Aptos", sector: "Layer 1" }
];

export async function syncBinanceSymbols() {
  console.log("[binance-sync] Syncing Binance symbol universe...");
  try {
    const res = await fetch("https://api.binance.com/api/v3/exchangeInfo");
    if (!res.ok) throw new Error(`Binance exchangeInfo returned status ${res.status}`);
    const info = await res.json();
    
    if (!info || !Array.isArray(info.symbols)) {
      throw new Error("Invalid exchangeInfo response structure");
    }

    interface BinanceSymbol {
      symbol: string;
      baseAsset: string;
      quoteAsset: string;
      status: string;
    }

    const usdtSymbols = (info.symbols as BinanceSymbol[]).filter(
      (s) => s.quoteAsset === "USDT" && 
             !s.symbol.includes("UP") && 
             !s.symbol.includes("DOWN") && 
             !s.symbol.includes("BULL") && 
             !s.symbol.includes("BEAR")
    );

    console.log(`[binance-sync] Found ${usdtSymbols.length} active USDT symbols. Syncing into symbols table...`);

    let synced = 0;
    for (const sym of usdtSymbols) {
      // 1. Permanent Symbol Universe table upsert
      const asset = await prisma.cryptoAsset.upsert({
        where: { symbol: sym.baseAsset },
        update: {
          isActive: sym.status === "TRADING",
        },
        create: {
          symbol: sym.baseAsset,
          isActive: sym.status === "TRADING",
        },
      });

      // 2. Insert/update CryptoMarket
      await prisma.cryptoMarket.upsert({
        where: { symbol: sym.symbol },
        update: {
          status: sym.status,
        },
        create: {
          assetId: asset.id,
          symbol: sym.symbol,
          baseAsset: sym.baseAsset,
          quoteAsset: sym.quoteAsset,
          exchange: "binance",
          status: sym.status,
        }
      });

      // Ensure price point exists
      const existingPrice = await prisma.cryptoPrice.findUnique({
        where: { assetId: asset.id }
      });
      if (!existingPrice) {
        await prisma.cryptoPrice.create({
          data: {
            assetId: asset.id,
            price: 0,
            volume: 0,
            change24h: 0,
          }
        });
      }
      
      synced++;
    }

    console.log(`[binance-sync] Completed. Synced ${synced} symbols.`);
    return synced;
  } catch (err) {
    console.error("[binance-sync] Failed to sync Binance symbol universe:", err);
    throw err;
  }
}
