import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { resolveProviderKey } from "@/lib/provider-keys";

export const dynamic = "force-dynamic";

// GET /api/harness/financial/providers — the Financial Data Gateway provider
// registry, with credential PRESENCE (never the value) merged from the vault.
//
// The Python registry holds only credential REFERENCES (env var names). This
// route — the side that owns the encrypted vault — fills in `configured` for
// credentialed providers. No secret ever crosses into the runtime response.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const capability = searchParams.get("capability");
  try {
    await ensurePythonRuntime();
    const url = new URL(`${HARNESS_PY_URL}/financial/providers`);
    if (capability) url.searchParams.set("capability", capability);
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(url, {
      headers: {
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `runtime returned ${res.status}` },
        { status: 502 },
      );
    }
    const payload = (await res.json()) as {
      providers?: Array<Record<string, unknown>>;
    };
    const providers = await Promise.all(
      (payload.providers ?? []).map(async (p) => {
        const ref = typeof p.credentialRef === "string" ? p.credentialRef : null;
        if (!ref) return p;
        const value = await resolveProviderKey(ref).catch(() => null);
        return { ...p, configured: Boolean(value && value.trim()) };
      }),
    );
    return NextResponse.json({ ...payload, providers });
  } catch (err) {
    console.error("[api/harness/financial/providers] GET error:", err);
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "financial provider registry unavailable" },
      { status: 503 },
    );
  }
}
