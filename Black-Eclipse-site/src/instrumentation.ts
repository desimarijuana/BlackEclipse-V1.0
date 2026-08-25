// Runs once when the Next.js server starts.
// Starts the price_scraper scheduler and pre-warms every market's universe so
// users get instant, fully-priced tables the moment they click a country.

export async function register() {
  console.log("[startup] instrumentation register() running");
  if (process.env.NEXT_RUNTIME === "nodejs") {
    // Dynamic import keeps this out of the client bundle.
    const { startScheduler, warmUpAllMarkets, startUniverseSync } = await import("@/lib/scraper/scheduler");
    const { seedUniverse } = await import("@/lib/scraper/price-scraper");

    try {
      await seedUniverse(["US"]);
    } catch (err) {
      console.error("[startup] seedUniverse failed:", err);
    }

    try {
      await startScheduler();
    } catch (err) {
      console.error("[startup] scheduler start failed:", err);
    }

    // Daily universe-sync cron: auto-adds new listings to JDDS and keeps the
    // full universe + prices current for all TradingView-covered markets.
    try {
      await startUniverseSync();
    } catch (err) {
      console.error("[startup] universe-sync start failed:", err);
    }

    // Background bulk warm-up: price all markets' full universes so page loads
    // are instant. Non-blocking — the server is fully up while this runs.
    try {
      void warmUpAllMarkets();
    } catch (err) {
      console.error("[startup] warm-up failed:", err);
    }
  }
}
