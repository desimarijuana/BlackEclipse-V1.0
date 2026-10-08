// Authentication / multi-user mode — the ONE authority for whether this
// deployment requires a signed-in user.
//
// BlackEclipse is a zero-config, single-user local app. Authentication is
// therefore OPT-IN and FAIL-OPEN-ONLY-ON-LOOPBACK, never on by surprise:
//
//   * `HARNESS_AUTH=required`  -> authentication is enforced everywhere.
//   * `HARNESS_AUTH=off`       -> authentication is explicitly disabled.
//   * unset (default)          -> authentication engages AUTOMATICALLY only when
//                                 the server is NOT reachable on loopback (or it
//                                 is a production build): i.e. the moment this
//                                 app could be reached by another machine, it
//                                 starts requiring a login instead of silently
//                                 being open.
//
// That last rule is the whole point: the old code only *warned* on a public bind.
// Here the guard becomes real. `npm run dev` on localhost is unaffected, so
// zero-config still works.
//
// The mode is resolved from the same signals the front-door API guard already
// uses (`HOST`, `NODE_ENV`, `CRON_SECRET`) so there is exactly one story.

export type AuthMode = "off" | "required";

export interface AuthConfig {
  /** Whether a signed-in user is required for this deployment. */
  required: boolean;
  /** Where the decision came from, for `/health` and logs (never a secret). */
  source: "explicit-on" | "explicit-off" | "auto-public" | "auto-local";
  /** Whether a real session signing secret is configured. */
  secretConfigured: boolean;
  /** Whether the operator secret (CRON_SECRET) is configured. */
  operatorSecretConfigured: boolean;
}

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const SECRET_PLACEHOLDER = "change-me-to-a-random-secret";
const COOKIE_NAME = "eclipse_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

function truthy(value: string | undefined): boolean | undefined {
  if (value === undefined) return undefined;
  const v = value.trim().toLowerCase();
  if (["1", "true", "yes", "on", "required", "enable", "enabled"].includes(v)) return true;
  if (["0", "false", "no", "off", "none", "disabled"].includes(v)) return false;
  return undefined;
}

/**
 * Resolve the auth configuration from the environment. Pure and testable: every
 * input is a parameter, so a test never mutates real `process.env`.
 */
export function resolveAuthConfig(
  env: Record<string, string | undefined> = process.env
): AuthConfig {
  const explicit = truthy(env.HARNESS_AUTH);
  const bindHost = (env.HOST ?? "").trim().toLowerCase();
  const publicBind = Boolean(bindHost) && !LOOPBACK_HOSTS.has(bindHost);
  const production = env.NODE_ENV === "production";
  const secretConfigured = Boolean(env.HARNESS_AUTH_SECRET) && env.HARNESS_AUTH_SECRET !== SECRET_PLACEHOLDER;
  const operatorSecretConfigured = Boolean(env.CRON_SECRET) && env.CRON_SECRET !== SECRET_PLACEHOLDER;

  if (explicit === true) {
    return { required: true, source: "explicit-on", secretConfigured, operatorSecretConfigured };
  }
  if (explicit === false) {
    return { required: false, source: "explicit-off", secretConfigured, operatorSecretConfigured };
  }
  // Auto: require auth exactly when the app is not obviously local-only.
  if (publicBind) {
    return { required: true, source: "auto-public", secretConfigured, operatorSecretConfigured };
  }
  // A production build defaults to required UNLESS explicitly opted out, because
  // `next start` often sits behind a proxy whose Host the app cannot see.
  if (production) {
    return { required: true, source: "auto-public", secretConfigured, operatorSecretConfigured };
  }
  return { required: false, source: "auto-local", secretConfigured, operatorSecretConfigured };
}

/** The resolved config for this process (memoized; env is read once at boot). */
let cached: AuthConfig | null = null;
export function authConfig(env: Record<string, string | undefined> = process.env): AuthConfig {
  if (!cached) cached = resolveAuthConfig(env);
  return cached;
}
/** Test seam: clear the memoized config. */
export function resetAuthConfig(): void {
  cached = null;
}

export function authRequired(env: Record<string, string | undefined> = process.env): boolean {
  return authConfig(env).required;
}

/**
 * True when authentication is required but cannot work (no usable signing
 * secret). In that state every request is refused with a clear, actionable
 * reason rather than silently allowing access.
 *
 * Kept here (not in the Edge-safe token module) so both the middleware and the
 * Node handlers share ONE definition.
 */
export function authMisconfigured(env: Record<string, string | undefined> = process.env): boolean {
  if (!resolveAuthConfig(env).required) return false;
  const secret = env.HARNESS_AUTH_SECRET;
  return !secret || secret === SECRET_PLACEHOLDER || secret.length < 16;
}

export const AUTH_COOKIE = COOKIE_NAME;
export const AUTH_SESSION_TTL_SECONDS = SESSION_TTL_SECONDS;
