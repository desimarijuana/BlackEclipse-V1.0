import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { action } = body;

    if (!["run_universe", "run_prices", "run_news"].includes(action)) {
      return NextResponse.json({ error: "Invalid action. Must be 'run_universe', 'run_prices', or 'run_news'." }, { status: 400 });
    }

    if (action === "run_universe") {
      await prisma.systemConfig.upsert({
        where: { key: "run_now_universe" },
        update: { value: "pending" },
        create: { key: "run_now_universe", value: "pending" }
      });
      return NextResponse.json({
        success: true,
        message: "Universe sync queued. The daemon will execute on its next cycle (~1 second)."
      });
    }

    if (action === "run_prices") {
      await prisma.systemConfig.upsert({
        where: { key: "run_now_prices" },
        update: { value: "pending" },
        create: { key: "run_now_prices", value: "pending" }
      });
      return NextResponse.json({
        success: true,
        message: "Price poll queued. The daemon will execute on its next cycle (~1 second)."
      });
    }

    if (action === "run_news") {
      await prisma.systemConfig.upsert({
        where: { key: "run_now_news" },
        update: { value: "pending" },
        create: { key: "run_now_news", value: "pending" }
      });
      return NextResponse.json({
        success: true,
        message: "News poll queued. The daemon will execute on its next cycle (~1 second)."
      });
    }

    return NextResponse.json({ error: "Action processing failed" }, { status: 500 });
  } catch (err) {
    console.error("[api/admin/trigger] Error:", err);
    return NextResponse.json({ error: "Failed to queue action" }, { status: 500 });
  }
}
