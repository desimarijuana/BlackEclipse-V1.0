import "dotenv/config";
import { prisma } from "../src/lib/prisma";

async function main() {
  console.log("=== Database Price Check ===");
  const cryptos = await prisma.cryptoAsset.findMany({
    where: { symbol: { in: ["BTC", "ETH"] } },
    include: { price: true }
  });
  
  const stocks = await prisma.stockAsset.findMany({
    where: { symbol: { in: ["AAPL", "MSFT"] } },
    include: { price: true }
  });

  for (const c of cryptos) {
    console.log(`\nCrypto: ${c.symbol} (Active: ${c.isActive})`);
    if (c.price) {
      console.log(`  Price: ${c.price.price} | Vol: ${c.price.volume} | Change24h: ${c.price.change24h}% | Updated: ${c.price.lastUpdated.toISOString()}`);
    } else {
      console.log("  No price record!");
    }
  }

  for (const s of stocks) {
    console.log(`\nStock: ${s.symbol} (Name: ${s.name})`);
    if (s.price) {
      console.log(`  Price: ${s.price.price} | ChangePercent: ${s.price.changePercent}% | Cap: ${s.price.marketCap} | Updated: ${s.price.lastUpdated.toISOString()}`);
    } else {
      console.log("  No price record!");
    }
  }

  await (prisma as any).$disconnect();
}

main().catch(console.error);
