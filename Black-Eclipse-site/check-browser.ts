import { chromium } from "playwright";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  });
  await page.goto("https://www.google.com/finance/quote/AAPL:NYSE", { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(3000);

  // Try to find price via different strategies
  const priceEls = await page.evaluate(() => {
    const results: Record<string, string> = {};
    // Strategy 1: data-last-price
    const d = document.querySelector("[data-last-price]");
    if (d) results["data-last-price"] = d.getAttribute("data-last-price") || "";
    // Strategy 2: common class YMlKec
    const y = document.querySelector(".YMlKec");
    if (y) results["YMlKec"] = y.textContent || "";
    // Strategy 3: any element with $ followed by digits
    const els = Array.from(document.querySelectorAll("div span, div div"));
    for (const el of els.slice(0, 50)) {
      const t = (el.textContent || "").trim();
      if (/\$\d+/.test(t)) {
        results["price-like"] = t;
        break;
      }
    }
    return results;
  });
  console.log("Found:", JSON.stringify(priceEls, null, 2));

  // Dump first 2000 chars of body text
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 1000));
  console.log("BODY:", bodyText);

  await browser.close();
}
main().catch((e) => {
  console.error("Error:", e?.message);
  process.exit(1);
});
