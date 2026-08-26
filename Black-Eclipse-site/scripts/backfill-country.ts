import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { PrismaClient } from "../src/generated/prisma/client";
import path from "path";

const dbPath = path.join(process.cwd(), "jdds.db");
const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
const prisma = new PrismaClient({ adapter });

async function main() {
  const markets = await prisma.market.findMany({ select: { id: true } });
  let total = 0;
  for (const m of markets) {
    const r = await prisma.asset.updateMany({ where: { marketId: m.id, OR: [{ country: null }, { country: "" }] }, data: { country: m.id } });
    total += r.count;
  }
  console.log("backfilled country on", total, "assets");
}

main().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
