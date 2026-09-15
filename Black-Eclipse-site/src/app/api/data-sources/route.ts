import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  createConnector,
  deleteConnector,
  listConnectorRows,
  toPublicConnector,
  updateConnector,
  loadConnectorsIntoRegistry,
  type ConnectorInput,
} from "@/lib/connectors/store";
import type { Capability } from "@/lib/connectors/types";
import { registerBuiltinConnectors } from "@/lib/connectors";

export const dynamic = "force-dynamic";

const CAPABILITIES: Capability[] = [
  "PRICE",
  "OHLCV",
  "QUOTE",
  "FUNDAMENTALS",
  "NEWS",
  "MACRO",
  "CUSTOM_DATASET",
];

// GET /api/data-sources — list operator-configured connectors (secrets masked).
export async function GET() {
  try {
    registerBuiltinConnectors();
    await loadConnectorsIntoRegistry();
    const rows = await listConnectorRows();
    return NextResponse.json({ connectors: rows.map(toPublicConnector) });
  } catch (err) {
    console.error("[api/data-sources] GET error:", err);
    return NextResponse.json({ error: "Failed to load data sources" }, { status: 500 });
  }
}

function validate(body: unknown): { ok: true; input: ConnectorInput } | { ok: false; error: string } {
  if (!body || typeof body !== "object") return { ok: false, error: "Body must be an object" };
  const b = body as Record<string, unknown>;
  if (typeof b.name !== "string" || b.name.trim() === "") return { ok: false, error: "Name is required" };
  if (typeof b.baseUrl !== "string") return { ok: false, error: "Base URL is required" };
  let parsed: URL;
  try {
    parsed = new URL(b.baseUrl);
  } catch {
    return { ok: false, error: "Base URL is not a valid URL" };
  }
  if (parsed.protocol !== "https:") return { ok: false, error: "Base URL must use https" };
  const capabilities = Array.isArray(b.capabilities)
    ? (b.capabilities as unknown[]).filter((c): c is Capability => CAPABILITIES.includes(c as Capability))
    : [];
  if (capabilities.length === 0) return { ok: false, error: "At least one capability is required" };
  const authShape = (b.auth ?? {}) as Record<string, unknown>;
  const scheme = ["none", "api_key", "bearer", "basic"].includes(String(authShape.scheme))
    ? (authShape.scheme as "none" | "api_key" | "bearer" | "basic")
    : "none";

  return {
    ok: true,
    input: {
      name: b.name.trim(),
      description: typeof b.description === "string" ? b.description : undefined,
      baseUrl: b.baseUrl,
      path: typeof b.path === "string" && b.path !== "" ? b.path : "/",
      capabilities,
      params: Array.isArray(b.params) ? (b.params as ConnectorInput["params"]) : [],
      headers: (b.headers && typeof b.headers === "object" ? b.headers : {}) as Record<string, string>,
      auth: {
        scheme,
        header: typeof authShape.header === "string" ? authShape.header : undefined,
        username: typeof authShape.username === "string" ? authShape.username : undefined,
      },
      secret: typeof b.secret === "string" ? b.secret : undefined,
      enabled: typeof b.enabled === "boolean" ? b.enabled : true,
    },
  };
}

// POST /api/data-sources — create a connector.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "data-sources-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json();
    const result = validate(body);
    if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 });
    const row = await createConnector(result.input);
    return NextResponse.json({ connector: toPublicConnector(row) }, { status: 201 });
  } catch (err) {
    console.error("[api/data-sources] POST error:", err);
    return NextResponse.json({ error: "Failed to create data source" }, { status: 500 });
  }
}

// PATCH /api/data-sources — update by id in the body.
export async function PATCH(request: Request) {
  const blocked = guardMutation(request, "data-sources-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const id = typeof body.id === "string" ? body.id : "";
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
    const partial: Partial<ConnectorInput> = {};
    if (typeof body.name === "string") partial.name = body.name;
    if (typeof body.description === "string") partial.description = body.description;
    if (typeof body.baseUrl === "string") partial.baseUrl = body.baseUrl;
    if (typeof body.path === "string") partial.path = body.path;
    if (Array.isArray(body.capabilities)) {
      partial.capabilities = (body.capabilities as unknown[]).filter((c): c is Capability =>
        CAPABILITIES.includes(c as Capability)
      );
    }
    if (Array.isArray(body.params)) partial.params = body.params as ConnectorInput["params"];
    if (body.headers && typeof body.headers === "object") {
      partial.headers = body.headers as Record<string, string>;
    }
    if (body.auth && typeof body.auth === "object") {
      const authShape = body.auth as Record<string, unknown>;
      partial.auth = {
        scheme: ["none", "api_key", "bearer", "basic"].includes(String(authShape.scheme))
          ? (authShape.scheme as "none" | "api_key" | "bearer" | "basic")
          : "none",
        header: typeof authShape.header === "string" ? authShape.header : undefined,
        username: typeof authShape.username === "string" ? authShape.username : undefined,
      };
    }
    if (typeof body.secret === "string") partial.secret = body.secret;
    if (typeof body.enabled === "boolean") partial.enabled = body.enabled;

    const row = await updateConnector(id, partial);
    return NextResponse.json({ connector: toPublicConnector(row) });
  } catch (err) {
    console.error("[api/data-sources] PATCH error:", err);
    return NextResponse.json({ error: "Failed to update data source" }, { status: 500 });
  }
}

// DELETE /api/data-sources?id=... — remove a connector.
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "data-sources-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const id = new URL(request.url).searchParams.get("id");
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
    await deleteConnector(id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[api/data-sources] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete data source" }, { status: 500 });
  }
}
