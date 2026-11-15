import { NextResponse } from "next/server";
import { requireApiAuth } from "@/lib/auth/server";
import { createDirectory } from "@/lib/workspace/browse-server";
import { corsPreflight, localCors } from "@/lib/workspace/cors";

export const dynamic = "force-dynamic";

// POST /api/workspace/browse/mkdir — create one folder in the directory the
// picker is showing. `name` is a single leaf, never a path. Node-native so the
// picker keeps working while the Python runtime restarts.
export async function POST(request: Request) {
  const denied = await requireApiAuth(request);
  if (denied) return denied;
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const parent = typeof body.path === "string" ? body.path.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!parent || !name) {
      return NextResponse.json(
        { error: "path and name are required" },
        { status: 400, headers: localCors(request) },
      );
    }
    return NextResponse.json(
      { success: true, ...createDirectory(parent, name) },
      { headers: { Connection: "close", ...localCors(request) } },
    );
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not create the folder" },
      { status: 400, headers: localCors(request) },
    );
  }
}

export async function OPTIONS(request: Request) {
  return corsPreflight(request);
}
