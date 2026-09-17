// Runs once when the Next.js server starts.
// Starts the price_scraper scheduler and pre-warms every market's universe so
// users get instant, fully-priced tables the moment they click a country.

export async function register() {
  console.log("[startup] instrumentation register() running");
  if (process.env.NEXT_RUNTIME === "nodejs") {
    // Expose whether a real LLM provider is configured so the client registry
    // (which cannot read server env from a bundled build) can pick the right
    // provider without shipping server code to the browser.
    const llmConfigured =
      Boolean(process.env.OPENAI_API_KEY) ||
      Boolean(process.env.OLLAMA_BASE_URL) ||
      Boolean(process.env.ANTHROPIC_API_KEY);
    process.env.NEXT_PUBLIC_LLM_CONFIGURED = llmConfigured ? "1" : "0";
    // Dynamic import keeps this out of the client bundle.
    const { startScheduler, warmUpAllMarkets, startUniverseSync } = await import("@/lib/scraper/scheduler");
    const { seedUniverse } = await import("@/lib/scraper/price-scraper");

    // DB durability guard: ensure WAL + synchronous=NORMAL are set on the
    // live connection and schedule a rolling local backup, so a crash or kill
    // mid-write can never silently corrupt the b-trees. Best-effort — never
    // blocks or fails the boot.
    try {
      const { execFile } = await import("child_process");
      const { promisify } = await import("util");
      const execFileP = promisify(execFile);
      const path = await import("path");
      const guardScript = path.join(process.cwd(), "scripts", "db-guard.js");
      // Set durability PRAGMAs on the live DB (idempotent, quick).
      void execFileP(process.execPath, [guardScript, "check"]).catch((err) =>
        console.error("[db-guard] durability check failed:", err?.message)
      );
      // Rolling local backup once per day.
      void execFileP(process.execPath, [guardScript, "backup"]).catch((err) =>
        console.error("[db-guard] daily backup failed:", err?.message)
      );
    } catch (err) {
      console.error("[db-guard] failed to schedule:", err);
    }

    try {
      await seedUniverse(["US"]);
    } catch (err) {
      console.error("[startup] seedUniverse failed:", err);
    }

    // Provider keys saved from Settings (encrypted in JDDS) are copied into the
    // process environment so every existing consumer — which reads env vars
    // directly — picks them up with no per-provider change. A REAL env var is
    // never overwritten, so a deployment stays authoritative. Values are not
    // logged; only the count.
    try {
      const { applyStoredKeysToEnv } = await import("@/lib/provider-keys");
      const applied = await applyStoredKeysToEnv();
      if (applied > 0) console.log(`[startup] applied ${applied} stored provider key(s)`);
    } catch (err) {
      console.error("[startup] provider-key apply failed:", err);
    }

    // Journal demo data — the journal is DB-backed, so without this a fresh
    // install shows an empty journal on every tab. Seeding is one-time and
    // conservative: it skips when any trade already exists and records a marker,
    // so a user who clears the demo data never gets it back. Every seeded row is
    // tagged source:'demo' and is removable from the Journal UI.
    try {
      const { seedJournalDemo } = await import("@/lib/journal/demo");
      const res = await seedJournalDemo();
      if (res.seeded) console.log(`[startup] seeded ${res.trades} demo journal trades`);
    } catch (err) {
      console.error("[startup] journal demo seed failed:", err);
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

    // News-refresh cron: ingests RSS feeds into JDDS on an interval so the
    // news page reads from the DB instead of fetching feeds per request.
    try {
      const { startNewsRefresh } = await import("@/lib/scraper/scheduler");
      await startNewsRefresh();
      // Kick one ingestion shortly after boot so the DB isn't empty on first load.
      setTimeout(() => {
        void import("@/lib/scraper/scheduler").then((m) => m.triggerNewsIngest());
      }, 15_000);
    } catch (err) {
      console.error("[startup] news-refresh start failed:", err);
    }

    // Background bulk warm-up: price all markets' full universes so page loads
    // are instant. Non-blocking — the server is fully up while this runs.
    try {
      void warmUpAllMarkets();
    } catch (err) {
      console.error("[startup] warm-up failed:", err);
    }

    // Price & condition alert monitor — starts exactly once, after the
    // scraper scheduler. Skipped in headless self-test runs.
    try {
      const { startAlertMonitor } = await import("@/lib/alerts/alertMonitor");
      await startAlertMonitor();
    } catch (err) {
      console.error("[startup] alert monitor start failed:", err);
    }

    // Operator data-source refresh. Runs on its own cron and yields to the
    // scraper's whole-market jobs (it skips a tick while they hold the write
    // path), so custom datasets stay current without competing for SQLite.
    try {
      const { startDatasetRefresh } = await import("@/lib/connectors/refresh-scheduler");
      await startDatasetRefresh();
    } catch (err) {
      console.error("[startup] dataset refresh start failed:", err);
    }

    // Investor Eye world-state ingestion (GDELT/USGS). Same discipline: one
    // cron, boot grace, and it skips a tick while the scraper holds the write
    // path. One refresh shortly after boot so the globe is not empty.
    try {
      const { startInvestorEyeIngest, runInvestorEyeIngest } = await import("@/lib/investor-eye/scheduler");
      await startInvestorEyeIngest();
      setTimeout(() => {
        void runInvestorEyeIngest();
      }, 30_000);
    } catch (err) {
      console.error("[startup] investor-eye ingest start failed:", err);
    }
  }
}
