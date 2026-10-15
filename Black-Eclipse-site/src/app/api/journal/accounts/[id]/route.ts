import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, updateAccount, deleteAccount, type UpdateAccountInput } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// PATCH /api/journal/accounts/[id] — update a trading account.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-accounts-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const data: UpdateAccountInput = {};
    if (typeof body.name === "string") data.name = body.name.trim();
    if ("broker" in body) data.broker = typeof body.broker === "string" ? body.broker : null;
    if (typeof body.currency === "string") data.currency = body.currency;
    if (body.initialBalance !== undefined) data.initialBalance = Number(body.initialBalance) || 0;
    if (body.archived !== undefined) data.archived = Boolean(body.archived);
    const account = await updateAccount(profileId, id, data);
    if (!account) return NextResponse.json({ error: "Account not found" }, { status: 404 });
    return NextResponse.json({ success: true, account });
  } catch (err) {
    console.error("[api/journal/accounts] PATCH error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to update account" },
      { status: 500 },
    );
  }
}

// DELETE /api/journal/accounts/[id] — delete a trading account.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-accounts-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteAccount(profileId, id);
    if (!deleted) return NextResponse.json({ error: "Account not found" }, { status: 404 });
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/journal/accounts] DELETE error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to delete account" },
      { status: 500 },
    );
  }
}
