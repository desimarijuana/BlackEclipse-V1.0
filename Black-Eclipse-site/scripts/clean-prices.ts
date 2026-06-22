import "dotenv/config";
import { prisma } from "../src/lib/prisma";

async function main() {
  console.log("[clean-prices] Wiping existing prices from database...");
  const cryptoCount = await prisma.cryptoPrice.deleteMany({});
  const stockCount = await prisma.stockPrice.deleteMany({});
  console.log(`[clean-prices] Deleted ${cryptoCount.count} crypto prices and ${stockCount.count} stock prices.`);
  await (prisma as any).$disconnect();
}

main().catch(console.error);
