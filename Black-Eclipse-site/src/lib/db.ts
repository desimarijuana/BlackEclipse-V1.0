import { PrismaClient } from "../generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import path from "path";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

// JDDS SQLite database file. Prisma `db push` creates it at the project root
// (per prisma.config.ts `file:./jdds.db`). Zero-config: auto-created on first use.
//
// `BE_DATA_DIR` relocates the personal databases onto an encrypted volume (see
// scripts/setup-data-vault.ps1). It is the SAME variable prisma.config.ts and the
// Python stores read, and it must be a real directory on that volume: SQLite
// writes its `-wal`/`-shm` sidecars next to this path, so a file symlink would
// leave the newest transactions outside the encrypted volume.
//
// `BE_DB_PATH` overrides ONLY the market/journal SQLite file. The Dev channel
// uses it to share the checked-in JDdS snapshot while keeping its agent memory
// isolated (see the data dir in scripts/lib/channels.js); doctor.js/db-guard.js
// already honour it.
const dataDir = process.env.BE_DATA_DIR
  ? path.resolve(process.env.BE_DATA_DIR)
  : process.cwd();
const dbPath = process.env.BE_DB_PATH
  ? path.resolve(process.env.BE_DB_PATH)
  : path.join(dataDir, "jdds.db");
const adapter = new PrismaBetterSqlite3({
  url: `file:${dbPath}`,
  // A first run can collide with the boot-time integrity check or a second
  // (stale) Eclipse process holding the write lock for a moment. Without a
  // bounded busy timeout, `SQLITE_BUSY` surfaces as an instant failure; with
  // it, a short wait usually lets the other writer finish. Five seconds keeps
  // the whole finish inside its 30 s deadline (three retried upserts, see
  // `completeOnboarding`) so the user gets the real cause instead of a timeout.
  timeout: 5_000,
});

export const prisma =
  globalForPrisma.prisma ?? new PrismaClient({ adapter });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}

/**
 * Yield control back to the event loop.
 *
 * better-sqlite3 statements are synchronous — a large batch of writes blocks
 * every other request until it finishes. Calling this between write chunks
 * lets queued HTTP responses, rendering, and timers run, so bulk background
 * work never freezes the UI.
 */
export function yieldToEventLoop(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}
