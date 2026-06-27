import "dotenv/config";
import { prisma } from "../src/lib/prisma";

async function main() {
  console.log("Checking Asset Symbol & Candle Stats in JDdS...");
  const symbols = await prisma.assetSymbol.findMany();
  console.log(`Total symbols in database: ${symbols.length}`);

  const counts = await prisma.historicalCandle.groupBy({
    by: ['symbolId', 'timeframe'],
    _count: {
      id: true
    }
  });

  for (const c of counts) {
    const sym = symbols.find(s => s.id === c.symbolId);
    if (sym) {
      console.log(`- ${sym.symbol} (${c.timeframe}): ${c._count.id} candles`);
    }
  }

  const jobs = await prisma.jDDSJob.findMany({
    where: { status: "pending" }
  });
  console.log(`Pending download jobs in queue: ${jobs.length}`);
}

main().catch(console.error);
