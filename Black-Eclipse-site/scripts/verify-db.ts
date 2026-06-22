import "dotenv/config";
import { prisma } from "../src/lib/prisma";

async function main() {
  const [cryptoCount, stockCount, marketCount] = await Promise.all([
    prisma.cryptoAsset.count(),
    prisma.stockAsset.count(),
    prisma.cryptoMarket.count(),
  ]);

  console.log("=== DB verification ===");
  console.log(`Total Crypto Assets: ${cryptoCount}`);
  console.log(`Total Crypto Markets: ${marketCount}`);
  console.log(`Total Stock Assets: ${stockCount}`);

  const samples = await prisma.cryptoAsset.findMany({
    take: 10,
    orderBy: { symbol: "asc" },
    select: { symbol: true, isActive: true },
  });
  console.log("\nSample Cryptos:");
  console.table(samples);

  const stockSamples = await prisma.stockAsset.findMany({
    take: 10,
    orderBy: { symbol: "asc" },
    select: { symbol: true, name: true },
  });
  console.log("\nSample Stocks:");
  console.table(stockSamples);

  // Disconnect Prisma
  await (prisma as any).$disconnect();
}

main().catch(console.error);
