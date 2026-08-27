import { chromium } from "playwright";
const b = await chromium.launch({ headless: true });
const page = await (await b.newContext({ viewport: { width: 1720, height: 1100 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

async function openScreener(p, tries = 4) {
  for (let t = 0; t < tries; t++) {
    try {
      await p.waitForTimeout(2500);
      await p.click("text=Market Screener", { timeout: 60000 });
      await p.waitForSelector("[data-gm-card]", { timeout: 90000 });
      await p.waitForTimeout(1500);
      return;
    } catch (e) { console.log("retry", t + 1); await p.reload({ waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {}); }
  }
  throw new Error("could not open screener");
}

await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await openScreener(page);

// TEST 1: DOM prices use country currencies, not dollars.
const priceCheck = await page.evaluate(() => {
  const out = {};
  document.querySelectorAll("[data-gm-card]").forEach(card => {
    const id = card.getAttribute("data-gm-id");
    if (!["PK","IN","CN","CA"].includes(id)) return;
    const priceText = card.querySelector("tbody td:nth-child(3)")?.textContent?.trim();
    out[id] = priceText;
  });
  return out;
});
console.log("prices:", JSON.stringify(priceCheck));
const dollarLeak = Object.values(priceCheck).some(v => v && /^\$\s/.test(v));
const hasNative = Object.entries(priceCheck).every(([id, v]) => {
  if (id === "PK") return v.includes("PKR");
  if (id === "IN") return v.includes("INR");
  if (id === "CN") return v.includes("CNY");
  if (id === "CA") return v.includes("CAD");
  return true;
});
console.log("DOLLAR LEAK:", dollarLeak, "| NATIVE CURRENCIES:", hasNative);

// TEST 2: numeric ticker markets show real names.
const nameCheck = await page.evaluate(() => {
  const out = {};
  document.querySelectorAll("[data-gm-card]").forEach(card => {
    const id = card.getAttribute("data-gm-id");
    if (!["CN","KR","HK","TW"].includes(id)) return;
    const firstRow = card.querySelector("tbody tr");
    out[id] = firstRow ? firstRow.textContent.trim().slice(0, 60) : "";
  });
  return out;
});
console.log("numeric rows:", JSON.stringify(nameCheck, null, 1));
const namesResolved = ["CN","KR","HK","TW"].every(id => {
  const t = nameCheck[id] || "";
  return t.includes("CXMT") || t.includes("Samsung") || t.includes("Tencent") || t.includes("TSMC");
});

// TEST 3: drag still works + no full re-render.
await page.evaluate(() => {
  window.__gridMutations = 0;
  const grid = document.querySelector("[data-gm-card]").parentElement;
  new MutationObserver(muts => { for (const m of muts) if (m.type === "childList" && m.addedNodes.length) window.__gridMutations++; }).observe(grid, { childList: true });
});
const ids = await page.$$eval("[data-gm-card]", els => els.map(e => e.getAttribute("data-gm-id")));
const headers = await page.$$("[data-gm-header]");
await headers[1].scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
const src = await headers[1].boundingBox();
const dst = await headers[0].boundingBox();
const sx = src.x + src.width / 2, sy = src.y + src.height / 2;
const dx = dst.x + dst.width / 2, dy = dst.y + dst.height / 2;
await page.mouse.move(sx, sy);
await page.mouse.down();
for (let i = 1; i <= 14; i++) {
  await page.mouse.move(sx + ((dx - sx) * i) / 14, sy + ((dy - sy) * i) / 14);
  await page.waitForTimeout(25);
}
const floatPresent = await page.evaluate(() => [...document.querySelectorAll("body > div")].some(d => d.textContent.includes("moving…")));
const mutations = await page.evaluate(() => window.__gridMutations);
await page.mouse.up();
await page.waitForTimeout(900);
const order = (JSON.parse(await page.evaluate(() => localStorage.getItem("be_gm_config") || "{}")).order) || [];
const domOrder = await page.$$eval("[data-gm-card]", els => els.map(e => e.getAttribute("data-gm-id")));
const reorder = order[0] === ids[1] && domOrder[0] === ids[1];
console.log("DRAG: float=" + floatPresent + " mutations=" + mutations + " reorder=" + reorder);

const pass = !dollarLeak && hasNative && namesResolved && floatPresent && mutations <= 3 && reorder && errors.length === 0;
if (!pass) { console.log("errors:", errors.slice(0, 4)); process.exit(1); }
console.log("ALL QA CHECKS DONE — PASS");
await b.close();
process.exit(0);
