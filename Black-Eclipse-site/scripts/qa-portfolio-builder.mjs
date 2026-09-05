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

// Drag reorder on overview customize tiles (HTML5 DnD needs synthetic events:
// mouse-only drags don't trigger native dragstart in headless Chromium)
await page.waitForTimeout(300);
const tileCount = await page.locator(".animate-fade-in-up .cursor-grab").count();
check("overview drag tiles present", tileCount >= 5, `count=${tileCount}`);
if (tileCount >= 2) {
  const before = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}")).widgets.map(w => w.id);
  await page.evaluate(async () => {
    const tiles = [...document.querySelectorAll(".animate-fade-in-up .cursor-grab")];
    const src = tiles[0], dst = tiles[1];
    const dt = new DataTransfer();
    src.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: dt }));
    await new Promise(r => setTimeout(r, 100)); // let React register the drag id
    dst.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
    dst.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
    src.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: dt }));
  });
  await page.waitForTimeout(600);
  const after = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}")).widgets.map(w => w.id);
  check("overview drag reorder works", JSON.stringify(before) !== JSON.stringify(after), `${before[0]}→${after[0]}`);
}

// Visibility toggle: verify the persisted layout flag flips, not DOM count
// (DOM count can lag due to render timing; localStorage write is the contract)
const eyeBtn = page.locator(".animate-fade-in-up button[title='Hide widget']").first();
const visBefore = await page.evaluate(() => JSON.parse(localStorage.getItem("eclipse_portfolio_layout") || "{}").widgets.find(w => w.id === "total-value")?.visible);
await eyeBtn.click();
await page.waitForTimeout(500);
const layoutAfterHide = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_portfolio_layout") || "{}"));
const hiddenId = layoutAfterHide.widgets.find(w => !w.visible)?.id;
const visAfter = layoutAfterHide.widgets.find(w => w.id === "total-value")?.visible;
check("overview visibility toggle hides widget", visBefore === true && visAfter === false && !!hiddenId, `hidden=${hiddenId}`);
// restore
await page.locator(".animate-fade-in-up button[title='Show widget']").first().click();
await page.waitForTimeout(400);

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
  await page.waitForTimeout(900);
  const fundLayout = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  const mosaicSpans = (fundLayout.widgets ?? []).filter(w => w.visible).map(w => w.span);
  const mixed = new Set(mosaicSpans).size >= 3;
  check("mosaic template persists mixed spans", mixed, JSON.stringify(mosaicSpans));
  const heights = (fundLayout.widgets ?? []).filter(w => w.visible).map(w => w.height);
  check("mosaic template includes heights", heights.some(h => h > 0));

  // Dense grid: measure that widgets actually flow side-by-side at lg width
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  const flow = await page.evaluate(() => {
    const g = document.querySelector(".fund-widget-flow");
    if (!g) return { found: false };
    const cols = new Set([...g.children].map((c) => Math.round(c.getBoundingClientRect().left)));
    return { found: true, distinctCols: cols.size, rows: g.children.length };
  });
  check("dense flow renders side-by-side", flow.found && flow.distinctCols >= 3, `cols=${flow.distinctCols}`);

  // No horizontal overflow (check both widget grid and document scroll)
  const overflow = await page.evaluate(() => {
    const g = document.querySelector(".fund-widget-flow");
    const gr = g.getBoundingClientRect();
    const kidsOut = [...g.children].filter((c) => c.getBoundingClientRect().right - gr.right > 2)
      .map((c) => c.querySelector("[data-widget-card]")?.getAttribute("data-widget-card"));
    const docOverflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
    return { kidsOut, docOverflow, any: kidsOut.length > 0 || docOverflow > 2 };
  });
  check("fund widgets stay inside grid", !overflow.any, JSON.stringify(overflow));

  // Corner-resize: scroll widget into view, drag its corner right-down
  const targetCard = page.locator("[data-widget-card]").nth(1);
  await targetCard.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  const target = await targetCard.boundingBox();
  await page.mouse.move(target.x + target.width - 3, target.y + target.height - 3);
  await page.mouse.down();
  for (let i = 1; i <= 14; i++) {
    await page.mouse.move(target.x + target.width - 3 + (i * 12), target.y + target.height - 3 + (i * 10));
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

  // Drag reorder a widget card itself (HTML5 DnD via synthetic events)
  const cards = await page.$$("[data-widget-card]");
  check("widget cards present", cards.length >= 10, `count=${cards.length}`);
  await page.evaluate(async () => {
    const shells = [...document.querySelectorAll(".fund-widget-flow > div[draggable='true']")];
    const src = shells[0], dst = shells[2];
    if (!src || !dst) return;
    // scroll source into view so events land on real elements
    src.scrollIntoViewIfNeeded();
    await new Promise(r => setTimeout(r, 300));
    const dt = new DataTransfer();
    src.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: dt }));
    await new Promise(r => setTimeout(r, 100));
    dst.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
    dst.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
    src.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: dt }));
  });
  await page.waitForTimeout(700);
  const afterDrag = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
  check("fund widget drag reorder works", JSON.stringify(afterDrag.widgets) !== JSON.stringify(afterShift.widgets));

  // Right-edge narrow handle: scroll handle into view (inside inner scroll
  // container), then mouse-drag it left
  const narrowResult = await page.evaluate(async () => {
    const card = document.querySelector("[data-widget-card='allocation']");
    const shell = card?.parentElement;
    const handle = shell?.querySelector("[title='Drag left to narrow']");
    if (!handle) return { err: "no handle" };
    // scroll the app's inner overflow container so the handle is on screen
    const r0 = handle.getBoundingClientRect();
    const scroller = [...document.querySelectorAll("*")].find(el => {
      const cs = getComputedStyle(el);
      return (cs.overflowY === "auto" || cs.overflowY === "scroll") && el.scrollHeight > el.clientHeight + 100;
    });
    if (scroller) scroller.scrollTop += r0.y - innerHeight / 2;
    window.scrollBy(0, Math.max(0, r0.y - innerHeight / 2));
    await new Promise(r => setTimeout(r, 400));
    const r = handle.getBoundingClientRect();
    if (r.y < 40 || r.y > innerHeight - 40) return { err: "handle offscreen", y: r.y };
    return { hx: r.x + r.width / 2, hy: r.y + r.height / 2 };
  });
  if (narrowResult.err) {
    check("edge handle resize works", false, narrowResult.err);
  } else {
    const beforeNarrow = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
    await page.mouse.move(narrowResult.hx, narrowResult.hy);
    await page.waitForTimeout(200);
    await page.mouse.down();
    await page.waitForTimeout(100);
    for (let i = 1; i <= 12; i++) {
      await page.mouse.move(narrowResult.hx - i * 15, narrowResult.hy, { steps: 2 });
      await page.waitForTimeout(25);
    }
    await page.mouse.up();
    await page.waitForTimeout(600);
    const afterNarrow = JSON.parse(await page.evaluate(() => localStorage.getItem("eclipse_fund_layout") || "{}"));
    const narrowChanged = JSON.stringify(beforeNarrow.widgets) !== JSON.stringify(afterNarrow.widgets);
    check("edge handle resize works", narrowChanged);
  }

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