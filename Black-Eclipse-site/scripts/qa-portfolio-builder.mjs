import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const results = [];
function check(name, cond, extra = "") {
  results.push({ name, pass: !!cond, extra });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? " — " + extra : ""}`);
}

const b = await chromium.launch({ headless: true });
const page = await (await b.newContext({ viewport: { width: 1720, height: 1100 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

// ── Setup: reach the My Portfolio screen ────────────────────────────────────
await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForTimeout(3000);
const sidebarBtn = page.locator("button:has-text('My Portfolio')").first();
await sidebarBtn.waitFor({ state: "visible", timeout: 30000 }).catch(() => {});
await sidebarBtn.click();
await page.waitForTimeout(3500);
const reached = await page.locator("button[title='Rearrange, show/hide, and resize dashboard widgets']").first().isVisible().catch(() => false);
check("portfolio screen reachable", reached);

// ── Overview customize panel ─────────────────────────────────────────────────
const customizeBtn = page.locator("button[title='Rearrange, show/hide, and resize dashboard widgets']");
await customizeBtn.waitFor({ state: "visible", timeout: 30000 }).catch(() => {});
check("customize button visible", await customizeBtn.isVisible().catch(() => false));
await customizeBtn.first().click();
await page.waitForTimeout(800);
const tmplBtns = page.locator("button", { hasText: "Layout templates" });
const dashTemplates = await page.locator("text=Layout templates").first().isVisible().catch(() => false);
check("overview templates shown", dashTemplates);

// Apply "Split" overview template
const splitBtn = page.locator("button[title*='Charts on the left']").first();
await splitBtn.waitFor({ state: "visible", timeout: 20000 });
await splitBtn.click();
await page.waitForTimeout(600);
const overviewLayout = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}"));
check("overview split template persisted", overviewLayout?.widgets?.some?.((w) => w.id === "fund-compare" && w.span === 3),
  JSON.stringify(overviewLayout?.widgets ?? []));

// Grid-dense layout: no element overflowing container horizontally at lg
const gridOverflow = await page.evaluate(() => {
  const g = document.querySelector(".overview-widget-grid");
  if (!g) return true;
  const gr = g.getBoundingClientRect();
  return [...g.children].some((c) => c.getBoundingClientRect().right - gr.right > 2);
});
check("overview widgets stay inside grid", !gridOverflow);

// Drag reorder on overview customize tiles
await page.waitForTimeout(300);
const tiles = await page.$$(".animate-fade-in-up .cursor-grab");
check("overview drag tiles present", tiles.length >= 5, `count=${tiles.length}`);
if (tiles.length >= 2) {
  const before = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}")).widgets.map(w => w.id);
  const s = await tiles[0].boundingBox();
  const d = await tiles[1].boundingBox();
  await page.mouse.move(s.x + s.width / 2, s.y + s.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) await page.mouse.move(s.x + ((d.x - s.x) * i) / 10, s.y + ((d.y - s.y) * i) / 10, { steps: 1 });
  await page.mouse.up();
  await page.waitForTimeout(600);
  const after = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}")).widgets.map(w => w.id);
  check("overview drag reorder works", JSON.stringify(before) !== JSON.stringify(after), `${before[0]}→${after[0]}`);
}

// Visibility toggle
const eyeBtn = page.locator(".animate-fade-in-up button[title='Hide widget']").first();
const widgetCountBefore = await page.evaluate(() => document.querySelectorAll(".overview-widget-grid > div").length);
await eyeBtn.click();
await page.waitForTimeout(400);
const widgetCountAfter = await page.evaluate(() => document.querySelectorAll(".overview-widget-grid > div").length);
check("overview visibility toggle hides widget", widgetCountAfter === widgetCountBefore - 1, `${widgetCountBefore}→${widgetCountAfter}`);
await eyeBtn.click(); // restore
await page.waitForTimeout(300);

// Leave overview customize mode
await page.locator("button", { hasText: "Done" }).first().click();
await page.waitForTimeout(400);

// ── Open a fund page ─────────────────────────────────────────────────────────
const fundCard = page.locator("text=Click a card to open that fund").first();
const cardLink = page.locator("[class*='FundCard'], .group.cursor-pointer").first();
let openedFund = false;
const anyCard = page.locator("button:has-text('Open'), .cursor-pointer").first();
// Try clicking first fund card region: cards render fund names; click the first card inside fund cards grid
const cardsGrid = page.locator(".grid.md\\:grid-cols-2").first();
if (await cardsGrid.isVisible().catch(() => false)) {
  const firstCard = cardsGrid.locator("> *").first();
  await firstCard.click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(1500);
  openedFund = await page.locator("button", { hasText: "Customize" }).first().isVisible().catch(() => false);
}
check("fund page opens", openedFund);

if (openedFund) {
  // ── Fund customize: templates, selection, resize, keyboard ────────────────
  await page.locator("button", { hasText: "Customize" }).first().click();
  await page.waitForTimeout(500);
  const fundTemplates = await page.locator("text=Templates").first().isVisible().catch(() => false);
  check("fund templates panel shown", fundTemplates);
  const tmplCount = await page.locator(".animate-fade-in-up .grid button[title]").count();
  check("9 fund templates available", tmplCount >= 9, `count=${tmplCount}`);

  // Apply Mosaic template → dense grid, mixed spans
  const mosaic = page.locator("button", { hasText: "Mosaic" }).first();
  await mosaic.click();
  await page.waitForTimeout(700);
  const fundLayout = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  const mosaicSpans = (fundLayout.widgets ?? []).filter(w => w.visible).map(w => w.span);
  const mixed = new Set(mosaicSpans).size >= 3;
  check("mosaic template persists mixed spans", mixed, JSON.stringify(mosaicSpans));
  const heights = (fundLayout.widgets ?? []).filter(w => w.visible).map(w => w.height);
  check("mosaic template includes heights", heights.some(h => h > 0));

  // Dense grid: measure that widgets actually flow side-by-side at lg width
  const flow = await page.evaluate(() => {
    const g = document.querySelector(".fund-widget-flow");
    if (!g) return { found: false };
    const cols = new Set([...g.children].map((c) => Math.round(c.getBoundingClientRect().left)));
    return { found: true, distinctCols: cols.size, rows: g.children.length };
  });
  check("dense flow renders side-by-side", flow.found && flow.distinctCols >= 3, `cols=${flow.distinctCols}`);

  // No horizontal overflow
  const overflow = await page.evaluate(() => {
    const g = document.querySelector(".fund-widget-flow");
    const gr = g.getBoundingClientRect();
    return [...g.children].some((c) => c.getBoundingClientRect().right - gr.right > 2);
  });
  check("fund widgets stay inside grid", !overflow);

  // Corner-resize: pick a widget, drag corner right-down
  const target = await page.locator("[data-widget-card]").nth(1).boundingBox();
  await page.mouse.move(target.x + target.width - 4, target.y + target.height - 4);
  await page.mouse.down();
  for (let i = 1; i <= 14; i++) {
    await page.mouse.move(target.x + target.width - 4 + (i * 10), target.y + target.height - 4 + (i * 8));
    await page.waitForTimeout(20);
  }
  await page.mouse.up();
  await page.waitForTimeout(500);
  const afterResize = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("corner resize changes layout", JSON.stringify(afterResize.widgets) !== JSON.stringify(fundLayout.widgets));

  // Click-to-select + keyboard nudge
  const card = page.locator("[data-widget-card]").first();
  await card.click();
  await page.waitForTimeout(300);
  const beforeKb = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  await page.keyboard.press("ArrowRight"); // nudge down in order
  await page.waitForTimeout(400);
  const afterKb = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("keyboard arrow reorders selected widget", JSON.stringify(beforeKb.widgets) !== JSON.stringify(afterKb.widgets));
  await page.keyboard.press("Shift+ArrowLeft"); // narrow
  await page.waitForTimeout(400);
  const afterShift = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("keyboard shift+arrow resizes width", JSON.stringify(afterKb.widgets) !== JSON.stringify(afterShift));
  await page.keyboard.press("Escape");

  // Drag reorder a widget card itself
  const cards = await page.$$("[data-widget-card]");
  check("widget cards present", cards.length >= 10, `count=${cards.length}`);
  const c0 = await cards[0].boundingBox();
  const c2 = await cards[2].boundingBox();
  await page.mouse.move(c0.x + c0.width / 2, c0.y + 14);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) await page.mouse.move(c0.x + ((c2.x - c0.x) * i) / 12 + 40, c0.y + ((c2.y - c0.y) * i) / 12 + 20);
  await page.mouse.up();
  await page.waitForTimeout(700);
  const afterDrag = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("fund widget drag reorder works", JSON.stringify(afterDrag.widgets) !== JSON.stringify(afterShift.widgets));

  // Left-edge narrow handle: drag from widget's left edge inward
  const w3 = await page.locator("[data-widget-card]").nth(0).boundingBox();
  const beforeNarrow = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  await page.mouse.move(w3.x + w3.width + 2, w3.y + w3.height / 2); // right handle zone
  await page.mouse.down();
  await page.mouse.move(w3.x + w3.width - 140, w3.y + w3.height / 2, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const afterNarrow = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  const narrowChanged = JSON.stringify(beforeNarrow.widgets) !== JSON.stringify(afterNarrow.widgets);
  check("edge handle resize works", narrowChanged);

  // Height stepper buttons in panel
  const plus = page.locator(".animate-fade-in-up button[title*='Taller']").first();
  await plus.click();
  await page.waitForTimeout(300);
  const afterPlus = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("height stepper works", JSON.stringify(afterPlus.widgets) !== JSON.stringify(afterNarrow.widgets));

  // Templates applied cleanly — reset back to default
  await page.locator("button", { hasText: "Classic" }).first().click();
  await page.waitForTimeout(500);
  const resetLayout = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("template re-apply resets layout", resetLayout.widgets.length === 18);

  // ── Responsiveness: tablet & mobile widths ────────────────────────────────
  for (const [w, h, name] of [[768, 1024, "tablet"], [390, 844, "mobile"]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(900);
    const respOverflow = await page.evaluate(() => {
      const g = document.querySelector(".fund-widget-flow");
      if (!g) return true;
      const gr = g.getBoundingClientRect();
      const doc = document.documentElement;
      return [...g.children].some((c) => c.getBoundingClientRect().right - gr.right > 4) ||
        doc.scrollWidth > doc.clientWidth + 2;
    });
    check(`${name} no horizontal overflow`, !respOverflow);
  }
  await page.setViewportSize({ width: 1720, height: 1100 });
  await page.waitForTimeout(600);

  // Done → exit customize mode, verify normal view renders & heights applied
  await page.locator("button", { hasText: "Done" }).first().click();
  await page.waitForTimeout(500);
  const normalRenders = await page.evaluate(() => {
    const g = document.querySelector(".fund-widget-flow");
    return g && g.children.length >= 10;
  });
  check("normal (non-edit) fund view renders", normalRenders);
}

// ── Regression: no console/page errors during the whole run ──────────────────
const meaningfulErrors = errors.filter((e) => !e.includes("favicon") && !e.includes("Download the React DevTools"));
check("no runtime errors", meaningfulErrors.length === 0, meaningfulErrors.slice(0, 3).join(" | "));

await page.evaluate(() => localStorage.clear());
await b.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);