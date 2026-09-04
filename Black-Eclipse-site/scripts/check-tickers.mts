import path from "path";
import { PrismaClient } from "../src/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";

const prisma = new PrismaClient({
  adapter: new PrismaBetterSqlite3({ url: `file:${process.cwd()}/jdds.db` }),
});

async function main() {
  const grouped = await prisma.newsItem.groupBy({
    by: ["ticker"],
    where: { ticker: { not: null } },
    _count: { _all: true },
    orderBy: { _count: { ticker: "desc" } },
    take: 25,
  });
  console.log("top tickers in news:", grouped.map((g) => `${g.ticker}:${g._count._all}`).join(" "));
  const recentWithTicker = await prisma.newsItem.count({
    where: { ticker: { not: null }, timestamp: { gte: new Date(Date.now() - 24 * 3600 * 1000) } },
  });
  console.log("news with ticker in last 24h:", recentWithTicker);
  await prisma.$disconnect();
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});