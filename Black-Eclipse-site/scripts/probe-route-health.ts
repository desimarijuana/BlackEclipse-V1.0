// Manual one-shot cross-market route-health probe (Harness closeout Phase 2.5).
//
// Records one attempt per (market × implemented capability) into the SAME
// SourceHealth ledger production traffic uses, under the SAME canonical key.
// The recurring schedule is separately gated behind HARNESS_ROUTE_PROBE_ENABLED
// and is OFF by default; this CLI always works on demand.
//
// Usage:
//   npx tsx scripts/probe-route-health.ts               # live probe, all markets
//   npx tsx scripts/probe-route-health.ts --fixture     # offline fixture probe
//   npx tsx scripts/probe-route-health.ts --markets US,UK
import { runRouteHealthProbe } from "../src/lib/harness/route-probe";

async function main() {
  const fixture = process.argv.includes("--fixture");
  const marketsArg = process.argv.find((a) => a.startsWith("--markets"));
  const markets = marketsArg
    ? (marketsArg.includes("=") ? marketsArg.split("=")[1] : process.argv[process.argv.indexOf(marketsArg) + 1])
        ?.split(",").map((s) => s.trim()).filter(Boolean)
    : undefined;

  const result = await runRouteHealthProbe({ kind: fixture ? "fixture" : "live", markets });
  console.log(
    `[probe-route-health] kind=${result.kind} probed=${result.probed} ok=${result.ok} ` +
    `failed=${result.failed} skipped=${result.skipped} markets=${result.markets.join(",")}`,
  );
}

main().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
