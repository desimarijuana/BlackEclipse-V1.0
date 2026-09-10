import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/agent/activity — real agent state from JDDS (ResearchReport, AgentRun,
// ResearchFinding). Never fabricates execution — only shows what actually ran.

export async function GET() {
  try {
    const [reports, runs, findings] = await Promise.all([
      prisma.researchReport.findMany({
        select: { id: true, query: true, ticker: true, market: true, status: true, verdict: true, confidence: true, createdAt: true },
        orderBy: { createdAt: "desc" },
        take: 20,
      }),
      prisma.agentRun.findMany({
        select: { id: true, agent: true, status: true, toolCalls: true, toolErrors: true, startedAt: true, finishedAt: true },
        orderBy: { startedAt: "desc" },
        take: 20,
      }),
      prisma.researchFinding.findMany({
        select: { id: true, agent: true, kind: true, ticker: true, title: true, createdAt: true },
        orderBy: { createdAt: "desc" },
        take: 20,
      }),
    ]);

    const activeRuns = runs.filter(r => r.status === "running").length;
    const runningReports = reports.filter(r => r.status === "running").length;

    return NextResponse.json({
      reports,
      runs,
      findings,
      activeRuns,
      runningReports,
      totalReports: reports.length,
    });
  } catch (err) {
    console.error("[api/agent/activity] GET error:", err);
    return NextResponse.json({ reports: [], runs: [], findings: [], activeRuns: 0, runningReports: 0, totalReports: 0 }, { status: 500 });
  }
}
