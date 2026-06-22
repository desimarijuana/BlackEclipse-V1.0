import "dotenv/config";
import { prisma } from "../src/lib/prisma";

async function main() {
  const adminUser = await prisma.user.findFirst({
    where: { email: "admin@blackeclipse.com" }
  });
  if (adminUser) {
    const profile = await prisma.portfolioProfile.findFirst({
      where: { userId: adminUser.id }
    });
    if (profile) {
      await prisma.portfolioTransaction.deleteMany({ where: { profileId: profile.id } });
      await prisma.portfolioSnapshot.deleteMany({ where: { profileId: profile.id } });
      await prisma.portfolioAlert.deleteMany({ where: { profileId: profile.id } });
      console.log("Admin portfolio data cleared. Next API request will reseed comprehensive sample records.");
    }
  }
}

main().catch(console.error);
