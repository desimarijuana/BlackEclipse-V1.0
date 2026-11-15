// The one authentication gate for the whole app (Next.js middleware, Edge
// runtime).
//
// It runs BEFORE any route handler or page render and does the COARSE check: a
// request must present a validly signed session cookie. The AUTHORITATIVE check
// (does the session row still exist, is the user active?) runs in Node route
// handlers via `requireApiAuth`, because the Edge runtime cannot open SQLite.
//
// It also enforces ONE canonical origin: when `BE_CANONICAL_HOST` is set, a
// request on any other host (localhost:3000, 127.0.0.1:3000) is redirected to
// the canonical host so all URLs are the same app with the same origin-scoped
// storage. Unset by default (zero-config localhost unchanged).
//
//   * `/api/**`  -> 401 JSON when authentication is required and missing.
//   * pages      -> redirect to `/login` (with a `next` return path).
//   * `/login` and `/api/auth/**` are always allowed, so a user can authenticate.
//
// When `HARNESS_AUTH` resolves off (the zero-config local case) this is a no-op,
// so the desktop app on loopback is unchanged.

import { NextResponse, type NextRequest } from "next/server";
import { authConfig, authMisconfigured } from "@/lib/auth/config";
import { readCookie, verifySessionToken, AUTH_COOKIE } from "@/lib/auth/token";
import { checkMutationAllowed } from "@/lib/api-guard";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|fonts/|sounds/|backgrounds/).*)"],
};

// `/api/channels/webhook/` is a PUBLIC inbound endpoint: an external provider
// (Slack/WhatsApp/generic) cannot present a session cookie. Authenticity is
// proven inside the handler by an HMAC over the raw body, so the middleware gate
// is bypassed for it — the signature is the gate.
// `/api/webhooks/` is the same shape for workflow webhooks: the handler proves
// authenticity with an HMAC over the raw body (or a token header), so the
// session gate is bypassed there and nowhere else.
// `/offline` is the page the service worker shows when the local app is not
// running. It must render for a signed-out visitor: the whole point is that the
// server may have stopped mid-session and the browser is asking for a page.
const PUBLIC_PREFIXES = ["/login", "/api/auth/", "/api/channels/webhook/", "/api/webhooks/", "/figure", "/offline"];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(p));
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Largest legitimate upload is 30 MB (backgrounds); 40 MB leaves headroom and
// stops the App Router from buffering an unbounded JSON/text body into memory.
const MAX_API_BODY_BYTES = 40_000_000;

/**
 * Central cross-site request guard for the API surface.
 *
 * Route handlers already rely on `guardMutation`, but coverage is not uniform:
 * several agent front-door routes (command execution, workspace writes, artifact
 * proxies) historically forwarded straight to the Python runtime. A missing
 * guard there is a drive-by CSRF to a privileged local action, because the
 * default desktop deployment runs with `HARNESS_AUTH=off` and the Python runtime
 * trusts a loopback peer.
 *
 * Enforcing the same policy once, before every API handler, makes a forgotten
 * per-route guard a defence-in-depth gap instead of an exploitable one:
 *   * a browser-declared `Sec-Fetch-Site: cross-site` request is refused;
 *   * a mutating request must pass the shared same-origin/loopback/secret rule.
 *
 * Public webhook prefixes are exempt (their handlers prove an HMAC over the raw
 * body); `/api/auth/*` is handled by its own guard so the login surface stays
 * reachable.
 */
function crossSiteRejected(request: NextRequest): NextResponse | null {
  const { pathname } = request.nextUrl;
  if (!pathname.startsWith("/api/") || isPublic(pathname)) return null;

  if (request.headers.get("sec-fetch-site") === "cross-site") {
    return NextResponse.json(
      { error: "Cross-site API requests are not allowed", code: "CROSS_SITE_BLOCKED" },
      { status: 403 },
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_API_BODY_BYTES) {
    return NextResponse.json(
      { error: "Request body is too large", code: "PAYLOAD_TOO_LARGE" },
      { status: 413 },
    );
  }

  if (!MUTATING_METHODS.has(request.method)) return null;

  const guard = checkMutationAllowed(request);
  if (guard.allowed) return null;
  return NextResponse.json(
    { error: guard.reason || "Forbidden", code: "MUTATION_FORBIDDEN" },
    { status: 403 },
  );
}

// A single canonical origin keeps ONE app: the same URL, the same origin-scoped
// storage (theme, sidebar, chat cache, …) on every visit. When `BE_CANONICAL_HOST`
// is set, a request on a different host is redirected there, preserving path +
// query. Nothing sets it now that the browser lane is gone (the desktop always
// uses 127.0.0.1), so it is inert by default.
//
// Only PAGE navigations are redirected. `/api/*` is deliberately left alone so
// programmatic callers that address the loopback server directly keep working —
// notably the Python harness, which posts back to HARNESS_CALLBACK_URL
// (`http://127.0.0.1:3000/api/...`) and does not follow redirects. The browser
// never hits that path: once a page is canonical, its API calls are same-origin.
//
// The public host must be read from the forwarding headers: behind the local
// proxy the server's own `nextUrl.host` is the internal 127.0.0.1:3000, which
// would otherwise make the canonical host redirect to itself (an infinite loop).
function hostName(host: string): string {
  return host.toLowerCase().replace(/:(80|443)$/, "");
}

function canonicalRedirect(request: NextRequest): NextResponse | null {
  const canonical = process.env.BE_CANONICAL_HOST?.trim();
  if (!canonical) return null;
  const url = request.nextUrl;
  if (url.pathname.startsWith("/api/")) return null;
  const rawHost = (
    request.headers.get("x-forwarded-host") ||
    request.headers.get("host") ||
    url.host
  ).split(",")[0].trim();
  if (hostName(rawHost) === hostName(canonical)) return null;
  const proto =
    (request.headers.get("x-forwarded-proto") || url.protocol.replace(":", "")).split(",")[0].trim() ||
    "http";
  const target = `${proto}://${canonical}${url.pathname}${url.search}`;
  // 307 preserves method + body, so a redirected request still works.
  return NextResponse.redirect(target, 307);
}

/**
 * Purge the browser's HTTP cache ONCE per dev server start.
 *
 * Why: in dev, Turbopack names a chunk after the MODULE it serves, not after
 * the bytes it holds. Edit, rename or delete a module and the bytes behind the
 * same URL change while the URL stays put. A browser that already cached the
 * old bytes then asks the runtime for a module factory the server no longer
 * has, and the page dies behind "the module factory is not available. It
 * might have been deleted in an HMR update".
 *
 * Dev chunks now revalidate (`must-revalidate`, see `next.config.ts`), but a
 * copy cached under the OLD `immutable` policy is still fresh for a year and
 * would never be revalidated. So the first page load after a dev server start
 * clears the HTTP cache - once, not on every navigation, so the second tab
 * still gets its cheap 304 instead of re-downloading the client graph.
 *
 * "cache" only: never cookies or localStorage, so the operator stays signed
 * in. Production is untouched - the flag and the header are dev-only.
 */
const DEV_PURGE_WINDOW_MS = 600_000;
const DEV_PURGE_MIN_GAP_MS = 15_000;
const DEV_PURGE_STARTED_AT = Date.now();

function purgeDevCacheOnce(request: NextRequest, response: NextResponse): void {
  if (process.env.NODE_ENV === "production") return;
  const path = request.nextUrl.pathname;
  if (path.startsWith("/api/") || path.startsWith("/_next/")) return;
  const now = Date.now();
  // For the first couple of minutes after a dev server start (or a recompile,
  // which re-evaluates this module) every page load still clears the HTTP
  // cache. Whoever loads first - a health check, a script, the operator - must
  // not be able to spend the purge on their own request and leave the
  // operator's browser holding the stale bytes. After the window the steady
  // state applies: chunks revalidate (304) and nothing is cleared.
  if (now - DEV_PURGE_STARTED_AT > DEV_PURGE_WINDOW_MS) return;
  const store = globalThis as typeof globalThis & { __beDevCachePurgedAt?: number };
  if (now - (store.__beDevCachePurgedAt ?? 0) < DEV_PURGE_MIN_GAP_MS) return;
  store.__beDevCachePurgedAt = now;
  response.headers.set("Clear-Site-Data", '"cache"');
}

export async function middleware(request: NextRequest) {
  const canonical = canonicalRedirect(request);
  if (canonical) return canonical;

  // This runs BEFORE the auth mode check on purpose: the zero-config desktop
  // deployment (HARNESS_AUTH=off) is exactly where an unguarded mutation route
  // would otherwise be reachable from any web page the operator visits.
  const crossSite = crossSiteRejected(request);
  if (crossSite) return crossSite;

  const cfg = authConfig();
  if (!cfg.required) {
    const response = NextResponse.next();
    purgeDevCacheOnce(request, response);
    return response;
  }

  const { pathname } = request.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();

  const isApi = pathname.startsWith("/api/");

  // Fail closed when auth is on but unusable.
  if (authMisconfigured()) {
    if (isApi) {
      return NextResponse.json(
        { error: "Authentication is required but HARNESS_AUTH_SECRET is not configured.", code: "AUTH_MISCONFIGURED" },
        { status: 503 }
      );
    }
    return new NextResponse("Authentication is required but not configured.", { status: 503 });
  }

  const token = readCookie(request.headers.get("cookie"), AUTH_COOKIE);
  const sessionId = token ? await verifySessionToken(token) : null;
  if (sessionId) {
    const response = NextResponse.next();
    purgeDevCacheOnce(request, response);
    return response;
  }

  if (isApi) {
    return NextResponse.json({ error: "Sign in required", code: "AUTH_REQUIRED" }, { status: 401 });
  }

  // A page request: send the user to the login page, remembering where they were.
  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.search = "";
  if (pathname !== "/") loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}
