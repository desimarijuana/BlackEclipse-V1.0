import { chromium } from "playwright";
const b = await chromium.launch({ headless: true });
const page = await (await b.newContext({ viewport: { width: 1720, height: 1100 } })).newPage();
const timeout = 90000;
async function openScreener(p, tries = 5) {
  for (let t = 0; t < tries; t++) {
    try {
      await p.waitForTimeout(2500);
      await p.click("text=Market Screener", { timeout });
      await p.waitForSelector("[data-gm-card]", { timeout });
      await p.waitForTimeout(1500);
      return;
    } catch (e) { console.log("retry", t + 1); await p.reload({ waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {}); }
  }
  throw new Error("could not open screener");
}
await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.evaluate(() => localStorage.clear());
await openScreener(page);

// Overview prices + tickers for key markets.
const overview = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll("[data-gm-card]").forEach(card => {
    const id = card.getAttribute("data-gm-id");
    if (!["PK","IN","CN","US","CA"].includes(id)) return;
    const rows = [...card.querySelectorAll("tbody tr")].slice(0, 2).map(tr =>
      [...tr.querySelectorAll("td")].map(td => td.textContent.trim()).join(" | ")
    );
    out.push({ id, rows });
  });
  return out;
});
console.log("=== OVERVIEW ===");
console.log(JSON.stringify(overview, null, 1));
await b.close();
