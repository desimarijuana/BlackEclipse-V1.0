import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { seedUniverse } from "@/lib/scraper";
import { parseCsv } from "@/lib/scraper/csv";
import { guardExpensiveMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// POST /api/scraper/import — import old/historical prices from a CSV payload.
// Body: { market, csv } — csv is the raw text; market defaults to "US".
const MAX_CSV_BYTES = 5 * 1024 * 1024;

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "scraper-import", { limit: 10, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const market: string = (body.market || "US").toUpperCase();
    const csv: string = typeof body.csv === "string" ? body.csv : "";

    if (!csv.trim()) {
      return NextResponse.json({ error: "Empty CSV payload" }, { status: 400 });
    }
    if (csv.length > MAX_CSV_BYTES) {
      return NextResponse.json({ error: "CSV payload too large (max 5 MB)" }, { status: 413 });
    }

    const rows = parseCsv(csv);
    if (rows.length === 0) {
      return NextResponse.json({ error: "No rows could be parsed from the CSV" }, { status: 400 });
    }

    // Ensure the market + its seed universe exist, then upsert the CSV rows.
    await seedUniverse([market]);

    const marketRow = await prisma.market.findUnique({ where: { id: market } });
    if (!marketRow) {
      return NextResponse.json({ error: `Unknown market: ${market}` }, { status: 400 });
    }

    let imported = 0;
    let skipped = 0;
    for (const row of rows) {
      if (!row.price || row.price <= 0) {
        skipped++;
        continue;
      }
      const asset = await prisma.asset.upsert({
        where: { marketId_symbol: { marketId: market, symbol: row.symbol } },
        update: { name: row.name ?? undefined, isActive: true },
        create: { marketId: market, symbol: row.symbol, name: row.name || row.symbol },
      });
      await prisma.price.upsert({
        where: { assetId: asset.id },
        update: {
          price: row.price,
          changePct: row.changePct ?? 0,
          marketCap: row.marketCap,
          volume: row.volume,
          source: "csv",
        },
        create: {
          assetId: asset.id,
          price: row.price,
          changePct: row.changePct ?? 0,
          marketCap: row.marketCap,
          volume: row.volume,
          source: "csv",
        },
      });
      imported++;
    }

    return NextResponse.json({ success: true, imported, skipped, market });
  } catch (err) {
    console.error("[api/scraper/import] error:", err);
    return NextResponse.json({ error: "Failed to import CSV prices" }, { status: 500 });
  }
}
