// ── Anatomy 3D smoke (screenshot regression) ──────────────────────────────────
//
// Drives the REAL app in a headless browser: sends a `/anatomy` prompt, waits for
// the `model3d` WebGL canvas, asserts the context is alive and non-blank-ish, and
// writes a screenshot for eyeballing. Run with the app up:
//
//   node scripts/anatomy-smoke.cjs            (default http://127.0.0.1:3000)
//   BLACK_ECLIPSE_URL=https://blackeclipse node scripts/anatomy-smoke.cjs
//
// It is NOT part of `npm test` (it needs a running server + a model provider);
// `npm run test:anatomy` is the opt-in entry point.

const { chromium } = require('playwright');
const path = require('path');
const os = require('os');

const BASE = process.env.BLACK_ECLIPSE_URL || 'http://127.0.0.1:3000';
const OUT = process.env.ANATOMY_SHOT || path.join(os.tmpdir(), 'anatomy-smoke.png');
const PROMPT = process.env.ANATOMY_PROMPT || '/anatomy a simple gear turning a shaft';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console.error: ${m.text()}`); });

  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);

  const textarea = page.locator('textarea').first();
  await textarea.waitFor({ state: 'visible', timeout: 30000 });
  await textarea.fill(PROMPT);
  await textarea.press('Enter');

  let canvas = 0;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(3000);
    canvas = await page.locator('.be-model3d canvas').count();
    if (canvas > 0) break;
  }
  if (!canvas) {
    console.error('FAIL: no model3d canvas appeared within the wait window');
    console.error(errors.slice(-10).join('\n'));
    await page.screenshot({ path: OUT, fullPage: false });
    await browser.close();
    process.exit(1);
  }

  await page.locator('.be-model3d').first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(1200);
  await page.locator('.be-model3d').first().screenshot({ path: OUT });

  const state = await page.evaluate(() => {
    const cv = document.querySelector('.be-model3d canvas');
    if (!cv) return { err: 'no canvas' };
    let gl = null;
    try { gl = cv.getContext('webgl2') || cv.getContext('webgl'); } catch (e) { return { err: String(e) }; }
    return { lost: gl ? gl.isContextLost() : 'no-gl', w: cv.width, h: cv.height };
  });

  const fatal = errors.filter((e) => !/GL Driver Message|ReadPixels|GPU stall/i.test(e));
  console.log('canvas:', JSON.stringify(state));
  console.log('screenshot:', OUT);
  if (state.lost !== false || fatal.length) {
    console.error('FAIL:', JSON.stringify({ state, fatal: fatal.slice(0, 5) }));
    await browser.close();
    process.exit(1);
  }
  console.log('PASS');
  await browser.close();
})().catch((err) => {
  console.error('SMOKE-ERROR', err);
  process.exit(1);
});
