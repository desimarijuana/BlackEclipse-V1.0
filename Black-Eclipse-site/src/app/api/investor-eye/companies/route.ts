import { NextResponse } from "next/server";
import { buildCompanies } from "@/lib/investor-eye/phase2";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/companies — companies geographically positioned via
// their HQ country, drawn from the EXISTING JDDS Asset universe + prices.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limitRaw = Number(searchParams.get("limit") ?? "200");
  const limit = Number.isFinite(limitRaw) ? Math.max(1, Math.min(limitRaw, 500)) : 200;
  try {
    const companies = await buildCompanies(limit);
    return NextResponse.json({ companies, total: companies.length });
  } catch (err) {
    console.error("[api/investor-eye/companies] error:", err);
    return NextResponse.json({ companies: [], total: 0 });
  }
}
