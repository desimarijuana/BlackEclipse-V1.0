import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { safeGet, OutboundError } from "@/lib/connectors/security";
import {
  applyStoredKeysToEnv,
  deleteProviderKey,
  listProviderKeyStatus,
  providerKeyDef,
  resolveProviderKey,
  saveProviderKey,
} from "@/lib/provider-keys";

export const dynamic = "force-dynamic";

// GET /api/provider-keys — non-secret status for every credential.
//
// The key VALUE never crosses this boundary: the browser only ever learns
// whether one is configured, where it came from, and a masked hint.
export async function GET() {
  try {
    return NextResponse.json({ keys: await listProviderKeyStatus() });
  } catch (err) {
    console.error("[api/provider-keys] GET error:", err);
    return NextResponse.json({ keys: [], error: "Failed to read provider keys" }, { status: 500 });
  }
}

// POST /api/provider-keys — save (or clear) one key, encrypted at rest.
// Body: { envVar, value }        → store (empty value deletes)
//       { envVar, action: "test" } → make a real request with the stored key
export async function POST(request: Request) {
  const blocked = guardMutation(request, "provider-keys");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  let body: { envVar?: string; value?: string; action?: string };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const envVar = typeof body.envVar === "string" ? body.envVar : "";
  const def = providerKeyDef(envVar);
  if (!def) return NextResponse.json({ error: "Unknown provider key" }, { status: 400 });

  // `test` is an outbound request, so it is rate-limited like every other one.
  if (body.action === "test") {
    const limited = rateLimit(`provider-key-test:${envVar}`, { limit: 10, windowMs: 60_000 });
    if (!limited.ok) {
      return NextResponse.json(
        { error: `Too many tests — retry in ${limited.retryAfterSec}s` },
        { status: 429 },
      );
    }
    return NextResponse.json(await testProviderKey(envVar));
  }

  if (typeof body.value !== "string") {
    return NextResponse.json({ error: "value is required" }, { status: 400 });
  }
  // A public value (a base URL) is stored as-is; a secret must be non-trivial.
  const value = body.value.trim();
  if (!def.publicValue && value !== "" && value.length < 8) {
    return NextResponse.json({ error: "That value looks too short to be an API key" }, { status: 400 });
  }

  try {
    await saveProviderKey(envVar, value);
    return NextResponse.json({
      ok: true,
      // Re-list so the UI reflects the true post-save resolution state.
      keys: await listProviderKeyStatus(),
    });
  } catch (err) {
    console.error("[api/provider-keys] save error:", err);
    return NextResponse.json({ error: "Failed to save the key" }, { status: 500 });
  }
}

// DELETE /api/provider-keys?envVar=… — remove a stored key.
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "provider-keys-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const envVar = new URL(request.url).searchParams.get("envVar") ?? "";
  if (!providerKeyDef(envVar)) {
    return NextResponse.json({ error: "Unknown provider key" }, { status: 400 });
  }
  try {
    await deleteProviderKey(envVar);
    return NextResponse.json({ ok: true, keys: await listProviderKeyStatus() });
  } catch (err) {
    console.error("[api/provider-keys] delete error:", err);
    return NextResponse.json({ error: "Failed to remove the key" }, { status: 500 });
  }
}

/**
 * Make a REAL request to the provider with the stored key.
 *
 * This is deliberately honest: it reports what actually happened (HTTP status,
 * latency, the provider's own error text) rather than declaring success because
 * a key exists. A provider with no declared test endpoint reports that instead
 * of pretending.
 */
async function testProviderKey(envVar: string): Promise<{
  ok: boolean;
  message: string;
  httpStatus?: number;
  latencyMs?: number;
}> {
  const def = providerKeyDef(envVar);
  if (!def) return { ok: false, message: "Unknown provider key" };
  if (!def.test) {
    return { ok: false, message: `${def.label} has no safe test endpoint — save and use it directly.` };
  }

  // Ensure a freshly-saved key is visible to this request before resolving.
  await applyStoredKeysToEnv();
  const key = await resolveProviderKey(envVar);
  if (!key) return { ok: false, message: `No key stored for ${def.label}.` };

  let url = def.test.url;
  const headers: Record<string, string> = { 'user-agent': 'BlackEclipse/1.0 (provider-key-test)' };
  if (def.test.auth.kind === 'query') {
    const u = new URL(url);
    u.searchParams.set(def.test.auth.name, key);
    url = u.toString();
  } else {
    headers[def.test.auth.name] = `${def.test.auth.prefix ?? ''}${key}`;
  }

  const started = Date.now();
  try {
    const res = await safeGet({ url, timeoutMs: 10_000, headers });
    const latencyMs = Date.now() - started;
    const ok = res.status >= 200 && res.status < 300;
    return {
      ok,
      message: ok
        ? `${def.label} accepted the key (HTTP ${res.status}).`
        : `${def.label} rejected it (HTTP ${res.status}).`,
      httpStatus: res.status,
      latencyMs,
    };
  } catch (err) {
    const message = err instanceof OutboundError
      ? `${def.label} could not be reached: ${err.message}`
      : `Test failed: ${err instanceof Error ? err.message : String(err)}`;
    return { ok: false, message, latencyMs: Date.now() - started };
  }
}
