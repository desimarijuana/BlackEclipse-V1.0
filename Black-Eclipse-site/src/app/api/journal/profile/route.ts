import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, getProfile, updateProfile, type UpdateProfileInput } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/profile — the trader's settings (currency, risk, account size).
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const profile = await getProfile(profileId);
    return NextResponse.json({ profile });
  } catch (err) {
    console.error("[api/journal/profile] GET error:", err);
    return NextResponse.json({ error: "Failed to load profile" }, { status: 500 });
  }
}

// PATCH /api/journal/profile — update trader settings.
export async function PATCH(request: Request) {
  const blocked = guardMutation(request, "journal-profile");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const data: UpdateProfileInput = {};
    if (typeof body.name === "string" && body.name.trim()) data.name = body.name.trim();
    if (typeof body.currency === "string") data.currency = body.currency;
    if (body.riskPerTrade !== undefined) data.riskPerTrade = Number(body.riskPerTrade) || 0;
    if (body.accountSize !== undefined) data.accountSize = Number(body.accountSize) || 0;
    const profileId = await getOrCreateProfile();
    const profile = await updateProfile(profileId, data);
    return NextResponse.json({ success: true, profile });
  } catch (err) {
    console.error("[api/journal/profile] PATCH error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to update profile" },
      { status: 500 },
    );
  }
}
