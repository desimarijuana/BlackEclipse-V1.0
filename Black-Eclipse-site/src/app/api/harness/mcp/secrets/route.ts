import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  listMcpSecretStatus,
  saveMcpSecret,
  deleteMcpSecret,
  isValidSecretName,
} from "@/lib/harness/mcp-secrets";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/secrets — names + masked hints only, never values.
// The vault is encrypted at rest in JDDS (TS/Prisma), so this route touches the
// vault directly; the Python runtime only ever receives a value over the
// authenticated read-only bridge (`mcp_secret_resolve`).
export async function GET() {
  try {
    const secrets = await listMcpSecretStatus();
    return NextResponse.json({ success: true, secrets });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP secret list failed" },
      { status: 500 }
    );
  }
}

// POST /api/harness/mcp/secrets — store/update an encrypted named secret.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "mcp-secrets");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { name?: unknown; value?: unknown };
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const value = typeof body.value === "string" ? body.value : "";
    if (!isValidSecretName(name)) {
      return NextResponse.json({ error: "invalid secret name" }, { status: 400 });
    }
    if (!value.trim()) return NextResponse.json({ error: "value is required" }, { status: 400 });
    await saveMcpSecret(name, value);
    // Echo only the name — never the value.
    return NextResponse.json({ success: true, name });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP secret save failed" },
      { status: 400 }
    );
  }
}

// DELETE /api/harness/mcp/secrets?name=… — remove a named secret.
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "mcp-secrets-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const name = new URL(request.url).searchParams.get("name") || "";
    if (!isValidSecretName(name)) {
      return NextResponse.json({ error: "invalid secret name" }, { status: 400 });
    }
    const removed = await deleteMcpSecret(name);
    return NextResponse.json({ success: true, name, removed });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP secret delete failed" },
      { status: 400 }
    );
  }
}
