import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { requireOperatorApiAuth } from "@/lib/auth/server";
import { getOrCreateProfile } from "@/lib/journal/data";
import {
  BrokerLinkInputError,
  deleteBrokerLink,
  updateBrokerLink,
} from "@/lib/journal/broker/links";

export const dynamic = "force-dynamic";

// PATCH /api/journal/broker/links/{id} — update account/enablement/mapping.
export async function PATCH(
  request: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
  const blocked = guardMutation(request, "journal-broker-link");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await ctx.params;
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const link = await updateBrokerLink(profileId, id, {
      ...(body.accountId !== undefined
        ? { accountId: typeof body.accountId === "string" ? body.accountId : null }
        : {}),
      ...(body.enabled !== undefined ? { enabled: body.enabled === true } : {}),
      ...(body.autoSync !== undefined ? { autoSync: body.autoSync === true } : {}),
      ...(body.backfillDays !== undefined ? { backfillDays: Number(body.backfillDays) } : {}),
      ...(body.symbolMap !== undefined
        ? {
            symbolMap:
              body.symbolMap && typeof body.symbolMap === "object" && !Array.isArray(body.symbolMap)
                ? (body.symbolMap as Record<string, string>)
                : null,
          }
        : {}),
    });
    if (!link) return NextResponse.json({ error: "Broker link not found" }, { status: 404 });
    return NextResponse.json({ success: true, link });
  } catch (err) {
    console.error("[api/journal/broker/links/[id]] PATCH error:", err);
    if (err instanceof BrokerLinkInputError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    return NextResponse.json({ error: "Failed to update broker link" }, { status: 500 });
  }
}

// DELETE /api/journal/broker/links/{id} — unlink. Imported trades are kept.
export async function DELETE(
  request: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const denied = await requireOperatorApiAuth(request);
  if (denied) return denied;
  const blocked = guardMutation(request, "journal-broker-link");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await ctx.params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteBrokerLink(profileId, id);
    if (!deleted) return NextResponse.json({ error: "Broker link not found" }, { status: 404 });
    return NextResponse.json({ success: true, deleted: true });
  } catch (err) {
    console.error("[api/journal/broker/links/[id]] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete broker link" }, { status: 500 });
  }
}
