import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  recordRiskAcknowledgement,
  riskAcknowledgementStatus,
} from "@/lib/legal/acceptance";
import { RISK_DISCLOSURE_VERSION } from "@/lib/legal/disclosure";
import type { SetupMode } from "@/lib/setup/types";

export const dynamic = "force-dynamic";

/**
 * Read/record the risk-notice acceptance OUTSIDE the setup wizard.
 *
 * The wizard covers a new install. An install that was migrated before this
 * notice existed still needs to accept the current version, so the in-app gate
 * posts here without re-running setup. A bare "accepted: true" is never
 * trusted — the caller must name the version it displayed.
 */
export async function GET() {
  try {
    return NextResponse.json(await riskAcknowledgementStatus());
  } catch (err) {
    console.error("[api/legal/risk-ack] GET error:", err);
    return NextResponse.json({ error: "Failed to read risk acknowledgement" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "risk-ack");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (body.version !== RISK_DISCLOSURE_VERSION) {
    return NextResponse.json(
      { error: "Please acknowledge the current risk notice." },
      { status: 400 },
    );
  }

  const mode: SetupMode | undefined =
    body.mode === "commercial" ? "commercial" : body.mode === "personal" ? "personal" : undefined;

  try {
    const ack = await recordRiskAcknowledgement(mode);
    return NextResponse.json({ ok: true, ...ack });
  } catch (err) {
    console.error("[api/legal/risk-ack] POST error:", err);
    return NextResponse.json({ error: "Failed to record risk acknowledgement" }, { status: 500 });
  }
}
