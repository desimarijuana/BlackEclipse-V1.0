import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, listAccounts, createAccount } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/accounts — list trading accounts.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const accounts = await listAccounts(profileId);
    return NextResponse.json({ accounts });
  } catch (err) {
    console.error("[api/journal/accounts] GET error:", err);
    return NextResponse.json({ error: "Failed to load accounts" }, { status: 500 });
  }
}

// POST /api/journal/accounts — create a trading account.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-accounts");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });
    const profileId = await getOrCreateProfile();
    const account = await createAccount(profileId, {
      name,
      broker: typeof body.broker === "string" ? body.broker : null,
      currency: typeof body.currency === "string" ? body.currency : "USD",
      initialBalance: Number(body.initialBalance) || 0,
    });
    return NextResponse.json({ success: true, account });
  } catch (err) {
    console.error("[api/journal/accounts] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create account" },
      { status: 500 },
    );
  }
}
