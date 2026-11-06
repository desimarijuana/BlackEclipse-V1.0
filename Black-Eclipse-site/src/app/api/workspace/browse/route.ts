import { NextResponse } from "next/server";
import { browseDirectory } from "@/lib/workspace/browse-server";
import { corsPreflight, localCors } from "@/lib/workspace/cors";

export const dynamic = "force-dynamic";

// GET /api/workspace/browse?path= — list direct children of a folder for the
// picker. Node-native and read-only: it must not wait for the Python runtime,
// which can be restarting. Approval of a root stays on the runtime's store.
export async function GET(request: Request) {
  try {
    const target = new URL(request.url).searchParams.get("path") ?? undefined;
    return NextResponse.json(
      { success: true, ...browseDirectory(target) },
      { headers: { Connection: "close", ...localCors(request) } },
    );
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "browse failed" },
      { status: 500, headers: localCors(request) },
    );
  }
}

export async function OPTIONS(request: Request) {
  return corsPreflight(request);
}
