import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, clearDemoData, countDemoTrades } from "@/lib/journal/data";
import { seedJournalDemo, DEMO_SEEDED_KEY } from "@/lib/journal/demo";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/journal/demo — is the current journal demo-seeded?
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const [demoTrades, total] = await Promise.all([
      countDemoTrades(profileId),
      prisma.trade.count({ where: { profileId } }),
    ]);
    return NextResponse.json({
      demoTrades,
      totalTrades: total,
      hasDemo: demoTrades > 0,
      // Only demo data present = the user hasn't added anything of their own.
      onlyDemo: demoTrades > 0 && demoTrades === total,
    });
  } catch (err) {
    console.error("[api/journal/demo] GET error:", err);
    return NextResponse.json({ error: "Failed to read demo state" }, { status: 500 });
  }
}

// POST /api/journal/demo { action: 'seed' | 'clear' }
//   seed  — add the demo set (only when the journal is empty)
//   clear — remove every demo row and set the marker so it doesn't come back
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-demo");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const action = body?.action === "clear" ? "clear" : "seed";
    const profileId = await getOrCreateProfile();

    if (action === "clear") {
      const { trades } = await clearDemoData(profileId);
      // Mark it so the boot seeder doesn't re-add what was just removed.
      await prisma.systemConfig.upsert({
        where: { key: DEMO_SEEDED_KEY },
        update: { value: new Date().toISOString() },
        create: { key: DEMO_SEEDED_KEY, value: new Date().toISOString() },
      });
      return NextResponse.json({ success: true, action, removed: trades });
    }

    const result = await seedJournalDemo();
    return NextResponse.json({ success: true, action, ...result });
  } catch (err) {
    console.error("[api/journal/demo] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to update demo data" },
      { status: 500 },
    );
  }
}
