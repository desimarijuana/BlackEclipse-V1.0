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
// so `npm run dev` on localhost is unchanged.

import { NextResponse, type NextRequest } from "next/server";
import { authConfig, authMisconfigured } from "@/lib/auth/config";
import { readCookie, verifySessionToken, AUTH_COOKIE } from "@/lib/auth/token";

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|fonts/|sounds/|backgrounds/).*)"],
};

// `/api/channels/webhook/` is a PUBLIC inbound endpoint: an external provider
// (Slack/WhatsApp/generic) cannot present a session cookie. Authenticity is
// proven inside the handler by an HMAC over the raw body, so the middleware gate
// is bypassed for it — the signature is the gate.
const PUBLIC_PREFIXES = ["/login", "/api/auth/", "/api/channels/webhook/"];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(p));
}

// A single canonical origin keeps ONE app: the same URL, the same origin-scoped
// storage (theme, sidebar, chat cache, …) on every visit. When `BE_CANONICAL_HOST`
// is set (the local-host launcher sets it to the `blackeclipse` hostname), a
// request on a different host is redirected there, preserving path + query.
// Unset by default, so `npm run dev:next` / zero-config localhost is unchanged.
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

export async function middleware(request: NextRequest) {
  const canonical = canonicalRedirect(request);
  if (canonical) return canonical;

  const cfg = authConfig();
  if (!cfg.required) return NextResponse.next();

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
  if (sessionId) return NextResponse.next();

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
