import path from "path";
import { PrismaClient } from "../src/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";

const prisma = new PrismaClient({
  adapter: new PrismaBetterSqlite3({ url: `file:${process.cwd()}/jdds.db` }),
});

async function main() {
  const total = await prisma.asset.count({ where: { isActive: true } });
  console.log("active assets:", total);
  const sample = await prisma.asset.findMany({
    where: { isActive: true, symbol: { in: ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL"] } },
    select: { symbol: true, market: true },
  });
  console.log("majors present:", JSON.stringify(sample));
  const withTicker = await prisma.newsItem.count({ where: { ticker: { not: null } } });
  const totalNews = await prisma.newsItem.count();
  console.log(`news with ticker: ${withTicker} / ${totalNews}`);
  await prisma.$disconnect();
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});