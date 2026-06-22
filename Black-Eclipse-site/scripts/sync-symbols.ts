import "dotenv/config";
import { syncBinanceSymbols } from "../src/data-layer/pipelines/binance";

async function main() {
  console.log("╔══════════════════════════════════════════════════════════╗");
  console.log("║         JDdS ENGINE — Binance Symbol Universe Sync       ║");
  console.log("╚══════════════════════════════════════════════════════════╝\n");

  try {
    const count = await syncBinanceSymbols();
    console.log(`\n[sync-symbols] Universe sync completed successfully. Synced ${count} symbols.`);
    process.exit(0);
  } catch (err) {
    console.error("\n[sync-symbols] Universe sync failed:", err);
    process.exit(1);
  }
}

main();
