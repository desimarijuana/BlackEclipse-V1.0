// Runs once when the Next.js server starts.
// Starts the price_scraper scheduler and pre-warms every market's universe so
// users get instant, fully-priced tables the moment they click a country.

const globalForBoot = globalThis as unknown as {
  __beInstrumentationRan?: boolean;
  __beBootBackgroundRan?: boolean;
};

export async function register() {
  console.log("[startup] instrumentation register() running");
  if (process.env.NEXT_RUNTIME === "nodejs") {
    // Next.js can invoke register() more than once in the same process (the app
    // server and the router worker both load instrumentation). Without this
    // guard that meant TWO schedulers, TWO `seedUniverse` passes and two boot
    // warm-ups all writing to the same SQLite file at once — the lock contention
    // produced P1008 timeouts and starved the event loop for minutes, so page
    // loads timed out during startup. Run the boot pipeline exactly once.
    if (globalForBoot.__beInstrumentationRan) {
      console.log("[startup] instrumentation already ran — skipping duplicate boot");
      return;
    }
    globalForBoot.__beInstrumentationRan = true;

    // ── Critical path (kept fast; this is awaited before the server listens) ──
    // `register()` is awaited by Next during startup, so anything awaited here
    // delays the moment the app can answer its FIRST request. Only the work a
    // request actually depends on belongs here (the deployment-exposure log and
    // the LLM-config flag the client reads). Every DB seed, cron, warm-up and
    // ingest yields to the request path anyway, so it is deferred to
    // `runBackgroundBootTasks()` below instead of blocking readiness.
    //
    // Deployment guard: this app is single-user local with no authentication or
    // tenancy isolation. Log the exposure assessment at boot so a public bind or
    // a missing CRON_SECRET is visible rather than silently mistaken as secure.
    try {
      const { warnOnDeploymentExposure } = await import("@/lib/api-guard");
      warnOnDeploymentExposure();
    } catch (err) {
      console.error("[startup] deployment exposure check failed:", err);
    }
    // Expose whether a real LLM provider is configured so the client registry
    // (which cannot read server env from a bundled build) can pick the right
    // provider without shipping server code to the browser.
    const llmConfigured =
      Boolean(process.env.OPENAI_API_KEY) ||
      Boolean(process.env.OLLAMA_BASE_URL) ||
      Boolean(process.env.ANTHROPIC_API_KEY);
    if (llmConfigured) {
      process.env.NEXT_PUBLIC_LLM_CONFIGURED = "1";
    } else {
      // No env key — but the settings vault may hold one, and a keyless local
      // server (Ollama/LM Studio) is a valid provider. Resolve the real config
      // so a provider configured in the UI is not hidden from the chat UI.
      try {
        const { getLLMConfig } = await import("@/lib/settings");
        const { isLocalBaseUrl } = await import("@/lib/agent/presets");
        const cfg = await getLLMConfig();
        const usable =
          cfg.provider !== "mock" && (Boolean(cfg.apiKey) || isLocalBaseUrl(cfg.baseUrl));
        process.env.NEXT_PUBLIC_LLM_CONFIGURED = usable ? "1" : "0";
        if (usable) {
          console.log(`[startup] LLM configured (${cfg.provider}) — chat uses the real provider`);
        }
      } catch {
        process.env.NEXT_PUBLIC_LLM_CONFIGURED = "0";
      }
    }

    // Everything else — DB seeding, crons, warm-up, ingests, the Python runtime
    // — runs AFTER register() resolves, so the server binds and serves without
    // waiting on the heavy boot pipeline. Not awaited; a failure is logged and
    // never crashes boot.
    void runBackgroundBootTasks().catch((err) =>
      console.error("[startup] background boot pipeline failed:", err)
    );
  }
}

/**
 * The heavy, non-critical half of boot: the daily DB backup, US universe
 * seed, provider-key apply, journal demo seed, the four cron registrations,
 * the production warm-up, the Python runtime pre-start, the alert monitor and
 * the one-shot news / Investor-Eye ingests.
 *
 * Runs once, AFTER `register()` resolves, so it never delays the server's
 * readiness (and therefore the first page load). Each step is independently
 * guarded and logged, so one failure cannot abort the rest. The heavy jobs
 * already yield to user-triggered work and to each other via the scheduler's
 * busy flags; deferring them keeps the whole pipeline off the critical path.
 *
 * IMPORTANT — this module is compiled for BOTH the Node and Edge runtimes (the
 * app ships a middleware). The dynamic imports below reach server-only native
 * modules (`@/lib/investor-eye/scheduler` → `@/lib/db` → `better-sqlite3` →
 * `fs`), which the Edge bundle cannot resolve. Physically wrapping every import
 * in the constant `process.env.NEXT_RUNTIME === "nodejs"` condition is what lets
 * webpack's ConstPlugin drop that import graph from the edge build. Do NOT hoist
 * these imports out of the block (e.g. into a helper the edge build still parses)
 * — that reintroduces `Module not found: Can't resolve 'fs'`.
 */
async function runBackgroundBootTasks(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    if (globalForBoot.__beBootBackgroundRan) return;
    globalForBoot.__beBootBackgroundRan = true;

    // Pre-start the Python agent runtime FIRST. A cold spawn imports the entire
    // agent stack (~9s on a warm machine, longer on a loaded one), and Bots is
    // usually the first surface a user opens that needs it. The DB seeds and
    // schedulers below run sequentially and can take a while, so scheduling this
    // last meant Bots paid the whole cold start. Starting it here boots Python
    // while the rest of the pipeline runs; concurrent requests still coalesce
    // onto this same spawn. Non-blocking: the server is fully up.
    void import("@/lib/harness/python-runtime")
      .then((m) => m.ensurePythonRuntime())
      .then((ok) => {
        if (!ok) console.error("[startup] Python runtime unavailable — agent runs will 503");
      })
      .catch((err) => console.error("[startup] python runtime warm-up failed:", err));

    // Graph Studio workflow schedules: start this FIRST (after the Python
    // warm-up kick-off), not at the end of the boot pipeline. The pipeline
    // below can take minutes on a cold boot, and a schedule must not miss its
    // first fire because a universe sync was running. One 60 s timer, never
    // storms on boot (missed fires follow catch-up), and only the DB-claimed
    // winner of a due fire starts a run.
    try {
      const { runDueSchedules } = await import("@/lib/graph-studio/schedule-tick");
      const tick = () => {
        void runDueSchedules().catch((err) =>
          console.error("[startup] workflow schedule tick failed:", err),
        );
      };
      // One grace-period tick after boot, then every minute.
      setTimeout(tick, 90_000);
      const timer = setInterval(tick, 60_000);
      if (typeof timer.unref === "function") timer.unref();
    } catch (err) {
      console.error("[startup] workflow schedule timer start failed:", err);
    }

    // Dynamic import keeps these out of the client bundle.
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
      const fs = await import("fs");
      const guardScript = path.join(process.cwd(), "scripts", "db-guard.js");
      // Set durability PRAGMAs on the live DB (idempotent, quick).
      void execFileP(process.execPath, [guardScript, "check"]).catch((err) =>
        console.error("[db-guard] durability check failed:", err?.message)
      );
      // Rolling local backup ONCE per day. The backup does `VACUUM INTO` on the
      // whole DB (hundreds of MB); running it on every boot spawned a heavy
      // 200 MB+ write storm at startup that contended for SQLite and starved
      // the event loop while the first page loads were compiling. Skip unless
      // the newest rolling backup is older than BACKUP_MIN_AGE_MS.
      const BACKUP_MIN_AGE_MS = 20 * 60 * 60 * 1000;
      const backupsDir = path.join(process.cwd(), "backups");
      let backupDue = true;
      try {
        const stamps = fs
          .readdirSync(backupsDir)
          .filter((f) => /^jdds-.*\.db$/.test(f))
          .map((f) => fs.statSync(path.join(backupsDir, f)).mtimeMs);
        if (stamps.length > 0 && Date.now() - Math.max(...stamps) < BACKUP_MIN_AGE_MS) {
          backupDue = false;
        }
      } catch {
        // No backups dir yet → back up on this boot.
      }
      if (backupDue) {
        void execFileP(process.execPath, [guardScript, "backup"]).catch((err) =>
          console.error("[db-guard] daily backup failed:", err?.message)
        );
      }
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

    // Journal ↔ broker auto-sync. Opt-in per link; one timer, cheap when no
    // link has autoSync enabled. It only reads the broker mirror and projects
    // trades — never a broker mutation.
    try {
      const { startJournalBrokerSync } = await import("@/lib/journal/broker/scheduler");
      startJournalBrokerSync();
    } catch (err) {
      console.error("[startup] journal broker auto-sync failed to start:", err);
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
