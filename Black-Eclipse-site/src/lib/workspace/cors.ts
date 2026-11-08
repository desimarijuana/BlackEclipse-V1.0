// ── Loopback CORS for the folder picker ─────────────────────────────────────
//
// In dev the app is served from `localhost:3000`, but the dev server can wedge
// a keep-alive connection after one request. The picker therefore talks to the
// SAME server on `127.0.0.1:3000` — a separate browser connection pool — so a
// dead `localhost` socket cannot freeze folder browsing. Both names are
// loopback, and the routes are already operator-gated, so allowing exactly the
// loopback origins is the narrowest possible CORS grant.

const LOOPBACK_ORIGIN = /^https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/;

export function localCors(request: Request): Record<string, string> {
  const origin = request.headers.get("origin") ?? "";
  if (!LOOPBACK_ORIGIN.test(origin)) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Private-Network": "true",
    "Vary": "Origin",
  };
}

export function corsPreflight(request: Request): Response {
  return new Response(null, { status: 204, headers: localCors(request) });
}
