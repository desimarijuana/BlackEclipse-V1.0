import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const jobId = searchParams.get("jobId");
    const symbolId = searchParams.get("symbolId");
    const timeframe = searchParams.get("timeframe") || "1d";

    if (jobId) {
      const job = await prisma.jDDSJob.findUnique({
        where: { id: jobId }
      });
      if (!job) {
        return NextResponse.json({ error: "Job not found." }, { status: 404 });
      }
      return NextResponse.json({ job });
    }

    if (symbolId) {
      const job = await prisma.jDDSJob.findFirst({
        where: { symbolId, timeframe },
        orderBy: { createdAt: "desc" }
      });
      const symbol = await prisma.assetSymbol.findUnique({
        where: { id: symbolId }
      });

      return NextResponse.json({
        job,
        dataStatus: symbol?.dataStatus || "needs_download",
        lastSyncedAt: symbol?.lastSyncedAt
      });
    }

    return NextResponse.json({ error: "Missing jobId or symbolId parameter." }, { status: 400 });

  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to fetch job status." },
      { status: 500 }
    );
  }
}
