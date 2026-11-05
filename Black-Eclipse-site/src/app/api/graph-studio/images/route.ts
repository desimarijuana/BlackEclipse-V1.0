import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { uploadGraphImage } from "@/lib/graph-studio/asset-client";

export const dynamic = "force-dynamic";

const MAX_BYTES = 20_000_000;
const IMAGE_TYPES = new Set([
  "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/tiff",
]);

function safeName(raw: string): string {
  const base = raw.split(/[\\/]/).pop()?.trim() ?? "";
  const cleaned = base.replace(/[\x00-\x1f]/g, "").trim();
  return cleaned && cleaned.length <= 180 ? cleaned : "image.png";
}

// POST /api/graph-studio/images — multipart image upload from the inspector.
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
        { error: `image is ${entry.size} bytes; the limit is ${MAX_BYTES}` },
        { status: 413 },
      );
    }
    const mime = (entry.type || "image/png").toLowerCase();
    if (!IMAGE_TYPES.has(mime)) {
      return NextResponse.json({ error: `unsupported image type ${mime}` }, { status: 415 });
    }
    const asset = await uploadGraphImage(
      request,
      safeName(entry.name || "image.png"),
      mime,
      await entry.arrayBuffer(),
    );
    return NextResponse.json({ success: true, image: asset });
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
