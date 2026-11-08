import { NextResponse } from "next/server";
import { pickNativeFolder } from "@/lib/workspace/native-picker";
import { corsPreflight, localCors } from "@/lib/workspace/cors";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// POST /api/workspace/pick-folder — open the Windows "Select Folder" dialog on
// the machine running the app. Blocks until the person picks or cancels.
export async function POST(request: Request) {
  if (process.platform !== "win32") {
    return NextResponse.json(
      { error: "The native folder dialog is only available on Windows." },
      { status: 501, headers: localCors(request) },
    );
  }
  try {
    const path = await pickNativeFolder();
    return NextResponse.json(
      { success: true, path, cancelled: !path },
      { headers: { Connection: "close", ...localCors(request) } },
    );
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not open the folder dialog" },
      { status: 500, headers: localCors(request) },
    );
  }
}

export async function OPTIONS(request: Request) {
  return corsPreflight(request);
}
