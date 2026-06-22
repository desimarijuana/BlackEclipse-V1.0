import "dotenv/config";
import { auth } from "../src/lib/auth";
import { prisma } from "../src/lib/prisma";

async function main() {
  console.log("[seed-admin] Seeding Developer Admin...");

  const email = "admin@blackeclipse.com";
  const password = "A03e09M02$";

  try {
    // Signup using better-auth api
    const response = await auth.api.signUpEmail({
      body: {
        email,
        password,
        name: "Developer Admin",
      },
    });
    console.log("[seed-admin] Created new admin account.");
  } catch (err) {
    console.log("[seed-admin] Account already exists or failed signup. Attempting role update directly...");
  }

  // Set role to admin in postgres
  try {
    const updated = await prisma.user.update({
      where: { email },
      data: { role: "admin" },
    });
    console.log("[seed-admin] Admin role assigned successfully in JDdS Database:", updated.email);
  } catch (err) {
    console.error("[seed-admin] Failed to update user role:", err);
  }

  process.exit(0);
}

main().catch((err) => {
  console.error("[seed-admin] Seeding crashed:", err);
  process.exit(1);
});
