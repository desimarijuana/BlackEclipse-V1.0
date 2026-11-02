import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { deleteGraphAsset, getGraphAsset } from "@/lib/graph-studio/asset-client";

export const dynamic = "force-dynamic";

function failure(err: unknown, fallback: string) {
  const unavailable = err instanceof HarnessRuntimeUnavailable;
  return NextResponse.json(
    { error: err instanceof Error ? err.message : fallback },
    { status: unavailable ? 503 : 400 },
  );
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    return NextResponse.json({ success: true, asset: await getGraphAsset(id) });
  } catch (err) {
    return failure(err, "file not found");
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    await deleteGraphAsset(id);
    return NextResponse.json({ success: true, assetId: id });
  } catch (err) {
    return failure(err, "delete failed");
  }
}
