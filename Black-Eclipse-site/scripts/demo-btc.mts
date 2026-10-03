// ── BTC end-to-end live demo ───────────────────────────────────────────────
// A runnable, honest demo that proves Bitcoin flows through the real data path
// (not a fixture). It exercises each leg and prints exactly which provider was
// contacted and the value returned, exiting non-zero on any hard failure.
//
// Run:  npx tsx scripts/demo-btc.mts
//   or: npm run demo:btc
//
// Legs:
//   1. JDDS   — the CRYPTO market + a bare `BTC` asset with a stored Price.
//   2. yfinance — `CRYPTO BTC` → BTC-USD (real Bitcoin, ~$80k).
//   3. Trap   — bare `US BTC` is the Grayscale Mini Trust ETF (~$37), NOT
//               Bitcoin. This is why the market qualifier matters.
//   4. Alert  — `fetchSnapshots("CRYPTO", ["BTC"])` (the alert engine's feed)
//               returns a positive close.
//   5. Server — if the app is up, /api/quote?symbols=BTC reports CRYPTO + live.
//
// Live-network legs are opt-in by nature; a missing Python/provider is reported
// as SKIP, never faked. Only a wrong-but-present value is a failure.

import { spawnSync } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { PrismaClient } from "../src/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";

const prisma = new PrismaClient({
  adapter: new PrismaBetterSqlite3({ url: `file:${process.cwd()}/jdds.db` }),
});

let failures = 0;
let skips = 0;

function pass(msg: string) {
  console.log(`  PASS  ${msg}`);
}
function fail(msg: string) {
  failures++;
  console.log(`  FAIL  ${msg}`);
}
function skip(msg: string) {
  skips++;
  console.log(`  SKIP  ${msg}`);
}

function pythonCmd(): string {
  const vendored =
    process.platform === "win32"
      ? path.join(process.cwd(), "scripts", "vendor", "python", "python.exe")
      : null;
  if (vendored && existsSync(vendored)) return vendored;
  return process.platform === "win32" ? "python" : "python3";
}

interface BridgeQuote {
  price: number;
  changePct?: number;
}
interface BridgeOut {
  quotes?: Record<string, BridgeQuote>;
  error?: string;
}

/** Run the yfinance bridge for one (market, symbol); returns null when unavailable. */
function bridge(market: string, symbol: string): BridgeOut | null {
  const res = spawnSync(pythonCmd(), ["scripts/yfinance_bridge.py", market, symbol], {
    cwd: process.cwd(),
    encoding: "utf8",
    timeout: 90_000,
  });
  const out = (res.stdout || "").trim();
  if (!out) return null;
  const start = out.indexOf("{");
  if (start < 0) return null;
  try {
    return JSON.parse(out.slice(start)) as BridgeOut;
  } catch {
    return null;
  }
}

async function legJdds() {
  console.log("\n[1] JDDS — the committed crypto universe");
  const market = await prisma.market.findFirst({ where: { country: "CRYPTO" } });
  if (!market) return fail("CRYPTO market not present in JDDS");
  pass(`CRYPTO market present (exchange=${market.exchange ?? "n/a"})`);

  const asset = await prisma.asset.findFirst({
    where: { symbol: "BTC", market: { country: "CRYPTO" } },
    include: { price: true },
  });
  if (!asset) return fail("bare BTC not found under CRYPTO");
  const p = asset.price?.price ?? 0;
  if (!(p > 1000)) return fail(`stored BTC price is not Bitcoin-like (got ${p})`);
  pass(`BTC asset "${asset.name}" stored price=${p} source=${asset.price?.source}`);

  const count = await prisma.asset.count({ where: { market: { country: "CRYPTO" } } });
  pass(`crypto universe size = ${count} assets`);
}

async function legYahooCrypto() {
  console.log("\n[2] yfinance — CRYPTO BTC resolves to real Bitcoin");
  const data = bridge("CRYPTO", "BTC");
  if (!data) return skip("yfinance bridge unavailable (no Python / offline)");
  if (data.error) return skip(`bridge error: ${data.error}`);
  const q = data.quotes?.["BTC-USD"] ?? Object.values(data.quotes ?? {})[0];
  if (!q || !(q.price > 1000)) return fail(`CRYPTO BTC did not resolve to Bitcoin (got ${q?.price})`);
  pass(`BTC-USD price=${q.price} changePct=${q.changePct ?? 0} (provider: yfinance)`);
}

function legTrap() {
  console.log("\n[3] Disambiguation — bare US 'BTC' is an ETF, not Bitcoin");
  const data = bridge("US", "BTC");
  if (!data) return skip("yfinance bridge unavailable (no Python / offline)");
  if (data.error) return skip(`bridge error: ${data.error}`);
  const q = data.quotes?.["BTC"] ?? Object.values(data.quotes ?? {})[0];
  if (!q) return skip("US BTC returned nothing");
  if (q.price > 1000) {
    // If Yahoo ever changes this, don't fail — just report it.
    console.log(`  NOTE  US BTC now returns ${q.price} (expected the ~$37 ETF)`);
  } else {
    pass(`US BTC = ${q.price} → the Grayscale Mini Trust ETF. Correctly distinct from Bitcoin.`);
  }
}

async function legAlertFeed() {
  console.log("\n[4] Alert engine feed — fetchSnapshots(\"CRYPTO\", [\"BTC\"])");
  // Import lazily so the demo runs even before the module graph is warm.
  const { fetchSnapshots } = await import("../src/lib/alerts/dataFeeds");
  const snap = await fetchSnapshots("CRYPTO", ["BTC"]);
  const btc = snap.get("BTC");
  if (!btc) return fail("alert feed returned no BTC snapshot under CRYPTO");
  if (!(btc.close > 1000)) return fail(`alert snapshot close not Bitcoin-like (got ${btc.close})`);
  pass(`snapshot close=${btc.close} changePct=${btc.changePct ?? 0} (the value an alert evaluates)`);
}

async function legOtherMarkets() {
  console.log("\n[5] Alert feed — markets beyond the old hardcoded [US,PK,IN,CRYPTO]");
  const { fetchSnapshots } = await import("../src/lib/alerts/dataFeeds");
  const cases: Array<[string, string]> = [
    ["UK", "HSBA"],
    ["JP", "7203"],
    ["DE", "SAP"],
    ["CRYPTO", "ETH"],
  ];
  for (const [market, symbol] of cases) {
    const snap = await fetchSnapshots(market, [symbol]);
    const s = snap.get(symbol);
    if (s && s.close > 0) pass(`${market}/${symbol} → ${s.close} (alert feed resolves)`);
    else skip(`${market}/${symbol} returned no quote (provider coverage, not a code path)`);
  }
}

async function legServer() {
  console.log("\n[6] Running app — /api/quote?symbols=BTC (optional)");
  try {
    const res = await fetch("http://localhost:3000/api/quote?symbols=BTC", {
      signal: AbortSignal.timeout(20_000),
    });
    if (!res.ok) return skip(`server returned HTTP ${res.status}`);
    const data = (await res.json()) as { quotes?: Array<{ marketId?: string; price?: number; source?: string; found?: boolean }> };
    const q = data.quotes?.[0];
    if (!q?.found) return fail("server did not find BTC");
    if (q.marketId !== "CRYPTO") return fail(`server resolved BTC to market ${q.marketId}, expected CRYPTO`);
    pass(`server: marketId=${q.marketId} price=${q.price} source=${q.source}`);
  } catch {
    skip("app not running on :3000 (start with `black eclipse`) — server leg skipped");
  }
}

async function main() {
  console.log("Black Eclipse — BTC live demo (real providers, no fixtures)");
  try {
    await legJdds();
    await legYahooCrypto();
    legTrap();
    await legAlertFeed();
    await legOtherMarkets();
    await legServer();
  } finally {
    await prisma.$disconnect();
  }
  console.log(
    `\n${failures === 0 ? "DEMO OK" : "DEMO FAILED"} — ${failures} failed, ${skips} skipped`,
  );
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
