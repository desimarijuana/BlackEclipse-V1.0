import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// GET /api/dev/cache-reset — drop the browser's HTTP cache for this origin.
//
// Why this exists: before Next stopped serving dev chunks as `immutable`, a
// browser could keep the OLD bytes of a Turbopack chunk whose URL stayed the
// same while the module behind it was edited, renamed or deleted. The runtime
// then asked for a module factory the server no longer had and the page died
// with "the module factory is not available" behind an error overlay.
//
// Dev chunks now revalidate (`must-revalidate`), so this is a one-time repair
// for a browser that already cached the old immutable copies. It clears ONLY
// the HTTP cache: cookies, localStorage and the login stay untouched.
//
// Dev only — in production there is nothing to repair and the route is absent.

export async function GET() {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return new NextResponse(
    JSON.stringify({
      ok: true,
      message: "Browser cache cleared. Reload the app.",
    }),
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        // "cache" only — never "cookies"/"storage", which would sign the
        // operator out.
        "Clear-Site-Data": '"cache"',
      },
    }
  );
}
