import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST() {
  try {
    const updated = await prisma.jDDSJob.updateMany({
      where: { status: "failed" },
      data: {
        status: "pending",
        progress: 0,
        error: null
      }
    });

    return NextResponse.json({
      success: true,
      count: updated.count,
      message: `Successfully reset ${updated.count} failed jobs back to pending.`
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to retry failed jobs." },
      { status: 500 }
    );
  }
}
