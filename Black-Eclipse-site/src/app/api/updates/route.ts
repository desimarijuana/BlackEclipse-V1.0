import { NextRequest, NextResponse } from "next/server";
import packageJson from "../../../../package.json";
import { getUpdateStatus } from "@/lib/updates/core";
import { isUpdateChannel, type UpdateChannel } from "@/lib/updates/types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Anonymous, read-only status: the server fetches a PUBLIC, SIGNED manifest and
// tells the client whether a newer version exists. Nothing about the user or
// this install is sent upstream — see docs/UPDATES.md.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const requested = params.get("channel") || process.env.ECLIPSE_UPDATE_CHANNEL || "stable";
  const channel: UpdateChannel = isUpdateChannel(requested) ? requested : "stable";

  const status = await getUpdateStatus({
    currentVersion: packageJson.version,
    channel,
    refresh: params.get("refresh") === "1",
  });

  return NextResponse.json(status, {
    headers: {
      // The value depends on ??refresh and on the manifest, never on the
      // caller; a shared cache must not leak one channel's answer to another.
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
