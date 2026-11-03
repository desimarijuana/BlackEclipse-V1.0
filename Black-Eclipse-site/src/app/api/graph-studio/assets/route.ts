import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { listGraphAssets, uploadGraphAsset } from "@/lib/graph-studio/asset-client";

export const dynamic = "force-dynamic";

const MAX_BYTES = 25_000_000;
const UNSAFE_NAME_CHARS_RE = /[\/\\\x00-\x1f<>:"|?*]/;
const WINDOWS_RESERVED_RE = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;

function safeName(raw: string): string {
  const base = raw.split(/[\\/]/).pop()?.trim() ?? "";
  const cleaned = base.replace(/[\x00-\x1f]/g, "").trim();
  if (!cleaned || cleaned.length > 180 || UNSAFE_NAME_CHARS_RE.test(cleaned)) return "upload.dat";
  if (WINDOWS_RESERVED_RE.test(cleaned) || /^[.\s]+$/.test(cleaned)) return "upload.dat";
  return cleaned;
}

export async function GET(request: Request) {
  try {
    return NextResponse.json({ success: true, assets: await listGraphAssets(request) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "list failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

// POST /api/graph-studio/assets — multipart upload from the inspector.
export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const entry = form.get("file");
    if (!(entry instanceof File)) {
      return NextResponse.json({ error: "file is required" }, { status: 400 });
    }
    if (entry.size <= 0) {
      return NextResponse.json({ error: "file is empty" }, { status: 400 });
    }
    if (entry.size > MAX_BYTES) {
      return NextResponse.json(
        { error: `file is ${entry.size} bytes; the limit is ${MAX_BYTES}` },
        { status: 413 },
      );
    }
    const name = safeName(entry.name || "upload.dat");
    const mime = (entry.type || "application/octet-stream").slice(0, 120);
    const bytes = await entry.arrayBuffer();
    const asset = await uploadGraphAsset(request, name, mime, bytes);
    return NextResponse.json({ success: true, asset });
  } catch (err) {
    if (err instanceof HarnessRuntimeUnavailable) {
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "upload failed" },
      { status: 400 },
    );
  }
}
