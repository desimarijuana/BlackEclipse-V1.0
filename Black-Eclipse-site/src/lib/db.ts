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
// `BE_DB_PATH` overrides ONLY the market/journal SQLite file. The dev profile
// uses it to share the checked-in JDdS snapshot while keeping its agent memory
// isolated (see scripts/lib/profiles.js); doctor.js/db-guard.js already honour it.
const dataDir = process.env.BE_DATA_DIR
  ? path.resolve(process.env.BE_DATA_DIR)
  : process.cwd();
const dbPath = process.env.BE_DB_PATH
  ? path.resolve(process.env.BE_DB_PATH)
  : path.join(dataDir, "jdds.db");
const adapter = new PrismaBetterSqlite3({
  url: `file:${dbPath}`,
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
