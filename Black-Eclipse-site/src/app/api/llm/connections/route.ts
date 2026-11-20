import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  deleteCustomConnection,
  getCustomConnection,
  listCustomConnectionsPublic,
  saveCustomConnection,
  type CustomAuthStyle,
} from "@/lib/agent/custom-connections";
import { customConnectionKeyEnvVar } from "@/lib/agent/custom-key";
import { deleteProviderKey, saveProviderKey } from "@/lib/provider-keys";
import { getLLMConfig, setLLMConfig } from "@/lib/settings";
import { normalizeBaseUrl } from "@/lib/providers/registry";
import { invalidateSettingsCache } from "@/lib/settings-route-cache";

export const dynamic = "force-dynamic";

function asAuthStyle(value: unknown): CustomAuthStyle | undefined {
  return value === "bearer" || value === "x-api-key" || value === "api-key" || value === "header"
    ? value
    : undefined;
}

/** GET /api/llm/connections — named custom connections (never their keys). */
export async function GET() {
  try {
    return NextResponse.json({ connections: await listCustomConnectionsPublic() });
  } catch (err) {
    console.error("[api/llm/connections] GET error:", err);
    return NextResponse.json({ connections: [], error: "Failed to read connections" }, { status: 500 });
  }
}

/**
 * POST /api/llm/connections — create or edit a named custom connection.
 * The key (when supplied) goes to its own encrypted vault entry.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "llm-connections");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const baseUrl = normalizeBaseUrl(typeof body.baseUrl === "string" ? body.baseUrl : "");
  if (!baseUrl) {
    return NextResponse.json({ error: "A valid base URL is required." }, { status: 400 });
  }
  const model = typeof body.model === "string" ? body.model.trim() : "";
  if (!model) {
    return NextResponse.json({ error: "A model id is required." }, { status: 400 });
  }

  const id = typeof body.id === "string" && body.id ? body.id : undefined;
  const existing = id ? await getCustomConnection(id) : null;
  if (id && !existing) {
    return NextResponse.json({ error: "Unknown connection." }, { status: 404 });
  }

  try {
    const saved = await saveCustomConnection({
      id,
      name: typeof body.name === "string" ? body.name : undefined,
      baseUrl,
      model,
      authStyle: asAuthStyle(body.authStyle),
      apiKeyHeader: typeof body.apiKeyHeader === "string" ? body.apiKeyHeader : undefined,
      apiKeyPrefix: typeof body.apiKeyPrefix === "string" ? body.apiKeyPrefix : undefined,
    });

    const apiKey = typeof body.apiKey === "string" ? body.apiKey.trim() : "";
    if (apiKey) {
      await saveProviderKey(customConnectionKeyEnvVar(saved.id), apiKey);
    }

    // If this connection is the active one, keep llm_config in step.
    const current = await getLLMConfig();
    if (current.provider === "custom" && current.connectionId === saved.id) {
      await setLLMConfig({
        provider: "custom",
        connectionId: saved.id,
        baseUrl: saved.baseUrl,
        model: saved.model,
        apiKey: "",
      });
      invalidateSettingsCache();
    }

    const [publicRow] = (await listCustomConnectionsPublic()).filter((c) => c.id === saved.id);
    return NextResponse.json({ ok: true, connection: publicRow });
  } catch (err) {
    console.error("[api/llm/connections] POST error:", err);
    return NextResponse.json({ error: "Failed to save the connection." }, { status: 500 });
  }
}

/** DELETE /api/llm/connections?id=… — remove the record and its vault key. */
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "llm-connections-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });

  try {
    const removed = await deleteCustomConnection(id);
    if (!removed) return NextResponse.json({ error: "Unknown connection." }, { status: 404 });

    await deleteProviderKey(customConnectionKeyEnvVar(id));
    const current = await getLLMConfig();
    if (current.provider === "custom" && current.connectionId === id) {
      await setLLMConfig({ provider: "mock", apiKey: "" });
    }
    invalidateSettingsCache();
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/llm/connections] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete the connection." }, { status: 500 });
  }
}
