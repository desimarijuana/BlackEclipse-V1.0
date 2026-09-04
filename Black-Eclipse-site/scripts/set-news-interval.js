const { PrismaClient } = require("@prisma/client");
const p = new PrismaClient();
p.cronJob
  .upsert({
    where: { type: "news_refresh" },
    update: { intervalMinutes: 5 },
    create: { type: "news_refresh", intervalMinutes: 5, enabled: true },
  })
  .then((r) => {
    console.log("updated:", r.type, r.intervalMinutes);
    return p.$disconnect();
  })
  .catch((e) => {
    console.error(e.message);
    process.exit(1);
  });