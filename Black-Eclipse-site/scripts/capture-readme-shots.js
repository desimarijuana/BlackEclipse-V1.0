#!/usr/bin/env node
/**
 * Capture the README screenshots that need the app's seeded state.
 *
 * Why a script instead of committed captures: Graph Studio needs a saved
 * workflow and Bots needs the finance pack, and neither exists on a fresh boot.
 * Run this with the app open on a machine whose vault is already seeded, and it
 * writes the two figures straight into docs/figures/readme/.
 *
 *   # 1. start the app (it seeds the vault and boots the Python runtime)
 *   npm run desktop:refresh
 *
 *   # 2. capture (the app must be listening on the port below)
 *   node scripts/capture-readme-shots.js
 *
 *   # a different port, or only one surface
 *   node scripts/capture-readme-shots.js --port 3101 --only bots
 *
 * Contract for anything this script writes into the README:
 *   - 1920x1080 viewport, cropped to 1600x868 by scripts/lib/readme-figure.js
 *   - a real, populated state: no "Loading", no empty reviewer pane
 *   - no machine-local paths in frame (the composer shows one on some routes)
 * Docs: docs/public-readme.md section 3.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs", "figures", "readme");

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
}

const PORT = arg("port", "3100");
const ONLY = arg("only", null);
const BASE = `http://127.0.0.1:${PORT}`;

const SHOTS = [
  {
    id: "graph-studio",
    out: "05-graph-studio",
    url: "/?tab=graph-studio",
    // A workflow must be open, otherwise the canvas is empty.
    ready: /Nodes|Canvas|Saved workflows|Run/i,
    settleMs: 4000,
  },
  {
    id: "bots",
    out: "06-bots",
    url: "/?tab=bots",
    // The finance pack should be seeded; the list is populated or seeding is offered.
    ready: /BOTS · [1-9]|Seed finance|Institution/i,
    settleMs: 4000,
  },
];

(async () => {
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch {
    console.error("playwright is not installed. Run: npm install");
    process.exit(1);
  }

  fs.mkdirSync(OUT, { recursive: true });
  const shots = ONLY ? SHOTS.filter((s) => s.id === ONLY) : SHOTS;
  if (!shots.length) {
    console.error(`nothing matches --only ${ONLY}; expected one of: ${SHOTS.map((s) => s.id).join(", ")}`);
    process.exit(1);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  try {
    for (const shot of shots) {
      process.stdout.write(`${shot.id}: ${BASE}${shot.url} ... `);
      const res = await page.goto(`${BASE}${shot.url}`, { waitUntil: "domcontentloaded", timeout: 120000 });
      if (!res || res.status() !== 200) throw new Error(`HTTP ${res ? res.status() : "no response"}`);

      await page
        .waitForFunction((src) => new RegExp(src, "i").test(document.body.innerText), shot.ready.source, {
          timeout: 45000,
        })
        .catch(() => {
          throw new Error(
            "the expected content never appeared. Open the tab by hand, make sure it is populated " +
              "(seeded vault, saved workflow), and run again.",
          );
        });

      await page.waitForTimeout(shot.settleMs);
      const png = await page.screenshot({ clip: { x: 0, y: 0, width: 1920, height: 1042 } });
      const file = path.join(OUT, `${shot.out}.png`);

      let sharp;
      try {
        sharp = require("sharp");
      } catch {
        fs.writeFileSync(file, png);
        console.log(`wrote ${path.relative(ROOT, file)} (uncropped, sharp unavailable)`);
        continue;
      }
      const info = await sharp(png)
        .resize({ width: 1600 })
        .png({ compressionLevel: 9, effort: 10 })
        .toFile(file);
      console.log(`${info.width}x${info.height}, ${Math.round(info.size / 1024)}KB`);
    }
  } finally {
    await browser.close();
  }

  console.log("\nNow add the figures to README.md's Screenshots table and record the capture in");
  console.log("docs/CHANGELOG.md. Check each image for machine-local paths before committing.");
})().catch((e) => {
  console.error(`\n${e.message}`);
  process.exit(1);
});
