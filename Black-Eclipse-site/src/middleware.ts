// The one authentication gate for the whole app (Next.js middleware, Edge
// runtime).
//
// It runs BEFORE any route handler or page render and does the COARSE check: a
// request must present a validly signed session cookie. The AUTHORITATIVE check
// (does the session row still exist, is the user active?) runs in Node route
// handlers via `requireApiAuth`, because the Edge runtime cannot open SQLite.
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

const PUBLIC_PREFIXES = ["/login", "/api/auth/"];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(p));
}

export async function middleware(request: NextRequest) {
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
