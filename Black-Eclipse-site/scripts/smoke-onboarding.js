#!/usr/bin/env node
/*
 * Onboarding smoke test — real browser, real server.
 *
 *   npm run smoke:onboarding                    # http://127.0.0.1:3100
 *   SMOKE_URL=http://127.0.0.1:3101 npm run smoke:onboarding
 *
 * It opens ?setup=1, verifies the gate appears even after the app rewrites the
 * URL, then walks all five steps. By default it does NOT click Finish, so it
 * cannot change the configured instance.
 *
 *   SMOKE_FINISH=1 npm run smoke:onboarding
 * clicks Finish and asserts the app actually mounts. Only run it against a
 * throwaway data directory (`BE_DATA_DIR`), because finishing setup writes the
 * completion flag, the risk acknowledgement and the source preferences.
 */
"use strict";

const { chromium } = require("playwright");
const { STABLE } = require("./lib/channels");

const BASE = (process.env.SMOKE_URL || `http://127.0.0.1:${STABLE.appPort}`).replace(/\/$/, "");
const FINISH = process.env.SMOKE_FINISH === "1";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 940 } });
  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

  await page.goto(`${BASE}/?setup=1`, { waitUntil: "commit", timeout: 180_000 });
  await page.waitForFunction(
    () => document.body && document.body.innerText.includes("How will you use Eclipse?"),
    undefined,
    { timeout: 180_000 },
  );

  const dialog = page.locator('[role="dialog"][aria-label="BlackEclipse setup"]');
  await dialog.waitFor({ state: "visible", timeout: 30_000 });

  const steps = [
    ["Welcome", "Pick a starting point."],
    ["AI", "Connect a model so chat works"],
    ["Included", "Free, open data that ships with Eclipse"],
    ["Providers", "Optional providers for quotes"],
    ["Review", "Confirm what will work before you start"],
  ];

  for (let i = 0; i < steps.length; i++) {
    const [name, text] = steps[i];
    await page.waitForFunction((t) => document.body.innerText.includes(t), text, { timeout: 30_000 });
    console.log(`[smoke] ${name} visible`);
    if (i === 0) {
      // The first-run wizard requires the risk acknowledgement before Continue.
      await dialog.getByRole("checkbox").first().check();
    }
    if (i < steps.length - 1) {
      await dialog.getByRole("button", { name: /Continue/i }).click();
      await page.waitForTimeout(300);
    }
  }

  const setupVisible = await page.evaluate(() => document.body.innerText.includes("Confirm what will work before you start"));
  if (!setupVisible) throw new Error("Review step did not render");

  if (FINISH) {
    const started = Date.now();
    await dialog.getByRole("button", { name: /Finish setup/i }).click();
    // The wizard reloads `/` on finish, so wait on the app shell itself (a
    // locator survives the navigation; page.evaluate does not).
    await page.getByText("CHAT HISTORY").first().waitFor({ state: "visible", timeout: 120_000 });
    await dialog.waitFor({ state: "detached", timeout: 60_000 });
    console.log(`[smoke] finish -> app in ${Date.now() - started} ms`);
    console.log("[smoke] setup completed; the app mounted");
  }

  if (errors.length > 0) {
    throw new Error(`Console/page errors:\n${errors.slice(0, 5).join("\n")}`);
  }

  console.log("[smoke] onboarding OK");
  await browser.close();
})().catch((err) => {
  console.error("[smoke] FAILED:", err && err.message ? err.message : err);
  process.exit(1);
});
