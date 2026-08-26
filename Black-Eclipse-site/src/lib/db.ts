import { PrismaClient } from "../generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import path from "path";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

// JDDS SQLite database file. Prisma `db push` creates it at the project root
// (per prisma.config.ts `file:./jdds.db`). Zero-config: auto-created on first use.
const dbPath = path.join(process.cwd(), "jdds.db");
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
