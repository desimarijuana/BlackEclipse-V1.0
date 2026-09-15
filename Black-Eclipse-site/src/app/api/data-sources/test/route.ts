import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { registerBuiltinConnectors } from "@/lib/connectors";
import { getConnector } from "@/lib/connectors/registry";
import { registerFromConfig } from "@/lib/connectors/runtime";
import { loadConnectorsIntoRegistry, recordHealth } from "@/lib/connectors/store";
import { snapshotFromTest } from "@/lib/connectors/health";
import { configFromDraft, type TestInput } from "@/lib/connectors/draft";
import { validateOutboundUrl } from "@/lib/connectors/security";

export const dynamic = "force-dynamic";

// POST /api/data-sources/test
// Runs a controlled, guarded outbound request for a connector — either a saved
// connector (`{ connectorId, params }`) or an unsaved draft (`{ config, params }`).
// A draft is validated and tested but NEVER persisted.
//
// Guarded by `guardExpensiveMutation` because it performs outbound network I/O.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "data-sources-test", { limit: 30, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }

  try {
    const body = (await request.json()) as Record<string, unknown>;
    const connectorId = typeof body.connectorId === "string" ? body.connectorId : undefined;
    // Test values live under `testParams`. For a saved connector we also accept
    // `params` (there, `params` is unambiguous — the stored definitions are in
    // the database, not the request body).
    const rawParams = body.testParams ?? (connectorId ? body.params : undefined);
    const params = (rawParams && typeof rawParams === "object" ? rawParams : {}) as Record<string, string>;

    registerBuiltinConnectors();
    await loadConnectorsIntoRegistry();

    let effectiveId = connectorId;

    if (!effectiveId) {
      const parsed = configFromDraft(body as TestInput);
      if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });
      const draft = parsed.config;
      const urlCheck = validateOutboundUrl(new URL(draft.path.replace(/^\/?/, "/"), draft.baseUrl).toString());
      if (!urlCheck.safe) {
        return NextResponse.json(
          { ok: false, state: "ERROR", message: urlCheck.reason, diagnostics: { code: urlCheck.code } },
          { status: 200 }
        );
      }
      effectiveId = registerFromConfig(draft);
    }

    const connector = getConnector(effectiveId);
    if (!connector) {
      return NextResponse.json({ error: `Unknown connector: ${effectiveId}` }, { status: 404 });
    }

    const result = await connector.test(params);

    // Persist health only for saved connectors.
    if (connectorId) {
      await recordHealth(connectorId, snapshotFromTest(result));
    }

    return NextResponse.json({
      ok: result.ok,
      state: result.state,
      httpStatus: result.httpStatus,
      latencyMs: result.latencyMs,
      message: result.message,
      sample: result.sample ?? null,
    });
  } catch (err) {
    console.error("[api/data-sources/test] error:", err);
    return NextResponse.json({ error: "Test failed" }, { status: 500 });
  }
}

// GET is intentionally not implemented — tests are mutations (outbound I/O).
export async function GET() {
  return NextResponse.json({ error: "Use POST to test a data source" }, { status: 405 });
}
