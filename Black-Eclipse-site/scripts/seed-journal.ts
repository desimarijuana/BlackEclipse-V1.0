// ── Journal seed — populate the journal with realistic demo data ─────────────
// Run: npx tsx scripts/seed-journal.ts
// Idempotent: skips when the journal already has trades or the one-time marker
// is set. The generator lives in src/lib/journal/demo.ts so the boot hook and
// this script share exactly one implementation.

import { prisma } from "../src/lib/db";
import { seedJournalDemo } from "../src/lib/journal/demo";

async function main() {
  const result = await seedJournalDemo({ force: true });
  if (result.seeded) {
    console.log(`Seeded ${result.trades} demo trades.`);
  } else {
    console.log(`Nothing seeded — ${result.reason ?? "unknown reason"}.`);
  }
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
