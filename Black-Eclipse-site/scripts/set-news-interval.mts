import { prisma } from "../src/lib/db";

async function main() {
  const r = await prisma.cronJob.upsert({
    where: { type: "news_refresh" },
    update: { intervalMinutes: 5 },
    create: { type: "news_refresh", intervalMinutes: 5, enabled: true },
  });
  console.log("updated:", r.type, r.intervalMinutes);
  await prisma.$disconnect();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});