const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

  await page.goto("http://localhost:3000/", { waitUntil: "networkidle", timeout: 60000 });
  await page.locator("text=Market News").first().click({ timeout: 15000 });
  await page.waitForTimeout(4000);

  const firstCard = page.locator("button.cursor-pointer").filter({ has: page.locator("h3") }).first();
  const headline = (await firstCard.locator("h3").textContent()).trim();

  const [popup] = await Promise.all([
    page.waitForEvent("popup", { timeout: 10000 }),
    firstCard.click({ timeout: 15000 }),
  ]);
  console.log("popup opened:", !!popup);
  console.log("popup url:", popup.url().slice(0, 90));
  console.log("clicked headline:", headline.slice(0, 70));
  await popup.close();

  // Click the SAME card again — must open another popup (the old bug: card became unclickable)
  const [popup2] = await Promise.all([
    page.waitForEvent("popup", { timeout: 10000 }),
    firstCard.click({ timeout: 15000 }),
  ]);
  console.log("second click popup opened:", !!popup2);
  await popup2.close();

  // Confirm no in-app dialog opened
  const dialogCount = await page.locator("[data-slot='dialog-content']").count();
  console.log("in-app dialog count:", dialogCount);
  console.log("errors:", errors.length ? errors.slice(0, 5) : "none");
  await browser.close();
})().catch((e) => { console.error("TEST FAILED:", e.message); process.exit(1); });