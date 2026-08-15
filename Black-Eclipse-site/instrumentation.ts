// Runs once when the Next.js server starts.
// Starts the price_scraper scheduler and seeds the JDDS universe.

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    // Dynamic import keeps this out of the client bundle.
    const { startScheduler } = await import("@/lib/scraper/scheduler");
    const { seedUniverse } = await import("@/lib/scraper/price-scraper");

    try {
      await seedUniverse(["US"]);
    } catch (err) {
      console.error("[startup] seedUniverse failed:", err);
    }

    try {
      startScheduler();
    } catch (err) {
      console.error("[startup] scheduler start failed:", err);
    }
  }
}
