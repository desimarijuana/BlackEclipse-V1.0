import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST() {
  try {
    await prisma.systemConfig.upsert({
      where: { key: "run_now_universe" },
      update: { value: "pending" },
      create: { key: "run_now_universe", value: "pending" }
    });

    return NextResponse.json({
      success: true,
      message: "Universe sync queued. The daemon will execute on its next cycle (~1 second)."
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to trigger universe sync." },
      { status: 500 }
    );
  }
}
