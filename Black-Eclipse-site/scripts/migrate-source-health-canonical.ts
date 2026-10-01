// One-time ledger migration (Harness closeout Phase 2.3).
//
// Folds legacy SourceHealth rows onto the CLOSED canonical vocabulary so the two
// readers of the one ledger (sourceHealth() and capabilityMatrix()) agree:
//   * a resolved market/source value is upper-cased / alias-collapsed;
//   * a literal `unknown` in `source` or `market` becomes the wildcard `*`.
//
// It is IDEMPOTENT and non-destructive: rows already canonical are untouched, and
// two rows that fold onto the SAME (source, market, symbol) key are MERGED
// (counters summed, latest timestamps kept) rather than silently dropped. Run it
// deliberately against jdds.db; it is NOT part of the boot path.
//
// Usage: npx tsx scripts/migrate-source-health-canonical.ts [--dry-run]
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { PrismaClient } from "../src/generated/prisma/client";
import { canonicalSource, canonicalMarket, isLiteralUnknown } from "../src/lib/harness/health-key";
import path from "path";

const dbPath = process.env.JDDS_DB_PATH || path.join(process.cwd(), "jdds.db");
const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
const prisma = new PrismaClient({ adapter });
const dryRun = process.argv.includes("--dry-run");

async function main() {
  const rows = await prisma.sourceHealth.findMany();
  let folded = 0;
  let merged = 0;

  for (const r of rows) {
    const source = canonicalSource(r.source);
    const market = canonicalMarket(r.market);
    const dirty = source !== r.source || market !== r.market
      || isLiteralUnknown(r.source) || isLiteralUnknown(r.market);
    if (!dirty) continue;

    const targetId = `${source}:${market}:${r.symbol}`;
    const existing = await prisma.sourceHealth.findUnique({ where: { id: targetId } });
    folded += 1;

    if (!dryRun) {
      if (existing && existing.id !== r.id) {
        // Merge into the canonical row, then delete the legacy row.
        await prisma.sourceHealth.update({
          where: { id: targetId },
          data: {
            successCount: existing.successCount + r.successCount,
            failCount: existing.failCount + r.failCount,
            lastStatus: r.updatedAt > existing.updatedAt ? r.lastStatus : existing.lastStatus,
            lastError: r.updatedAt > existing.updatedAt ? r.lastError : existing.lastError,
            lastSuccessAt: later(existing.lastSuccessAt, r.lastSuccessAt),
            lastFailureAt: later(existing.lastFailureAt, r.lastFailureAt),
          },
        });
        await prisma.sourceHealth.delete({ where: { id: r.id } });
        merged += 1;
      } else if (!existing) {
        // Rekey to the canonical id and store the canonical source/market.
        await prisma.sourceHealth.update({
          where: { id: r.id },
          data: { id: targetId, source, market },
        });
      }
    }
  }

  console.log(
    `[migrate-source-health] ${dryRun ? "DRY RUN — " : ""}` +
    `folded ${folded} row(s), merged ${merged} duplicate(s), scanned ${rows.length}.`,
  );
}

function later(a: Date | null, b: Date | null): Date | null {
  if (!a) return b;
  if (!b) return a;
  return a > b ? a : b;
}

main()
  .then(async () => { await prisma.$disconnect(); process.exit(0); })
  .catch(async (e) => { console.error(e); await prisma.$disconnect(); process.exit(1); });
