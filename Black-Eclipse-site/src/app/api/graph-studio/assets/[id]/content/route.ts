import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { getGraphAssetContent } from "@/lib/graph-studio/asset-client";

export const dynamic = "force-dynamic";

// GET /api/graph-studio/assets/:id/content — stream/download the stored bytes.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const file = await getGraphAssetContent(request, id);
    return new Response(new Blob([file.bytes], { type: file.mime }), {
      headers: {
        "Content-Type": file.mime,
        "Content-Disposition": `inline; filename="${file.name.replace(/"/g, "")}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "file not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}
