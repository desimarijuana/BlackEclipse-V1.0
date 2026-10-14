// Client-side fetch resilience for transient transport failures.
//
// `TypeError: Failed to fetch` means the request never got a response — the
// server restarted (common in dev when the Next child process is recycled),
// the connection dropped, or the machine was briefly unreachable. Retrying
// once or twice with a short backoff lets those blips self-heal instead of
// forcing a screen into its demo/UNAVAILABLE fallback.
//
// HTTP error statuses (4xx/5xx) are NOT retried: the server answered, and the
// request itself is what failed.

const NETWORK_ERROR_RE = /failed to fetch|networkerror|load failed|network request failed/i;

/** True for transport-level failures that a bounded retry could recover from. */
export function isTransientFetchError(err: unknown): boolean {
  if (!(err instanceof Error) || err.name === 'AbortError') return false;
  if (err.name === 'TimeoutError') return true;
  return err instanceof TypeError && NETWORK_ERROR_RE.test(err.message);
}

export interface FetchRetryOptions {
  /** Extra attempts after the first one (default 2 → 3 attempts total). */
  retries?: number;
  /** First backoff in ms; doubles each attempt (default 400ms → 400, 800). */
  backoffMs?: number;
}

/**
 * `fetch` with bounded retries on transport-level failures only. Aborting the
 * caller's signal stops retries immediately (the abort is rethrown as-is).
 */
export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  opts: FetchRetryOptions = {},
): Promise<Response> {
  const retries = Math.max(0, opts.retries ?? 2);
  const backoffMs = Math.max(0, opts.backoffMs ?? 400);
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetch(input, init);
    } catch (err) {
      if (init?.signal?.aborted || !isTransientFetchError(err) || attempt >= retries) throw err;
      await new Promise((resolve) => setTimeout(resolve, backoffMs * 2 ** attempt));
    }
  }
}

/**
 * Log a fetch failure the caller already handled (retried, or degraded to an
 * explicit demo/UNAVAILABLE state). Transport failures are warnings — the
 * backend was briefly unreachable, not a client bug — while anything else
 * stays a hard error. A `console.error` for a handled outage would raise the
 * Next.js dev error overlay for an error the app already recovered from.
 */
export function logHandledFetchFailure(label: string, err: unknown): void {
  if (isTransientFetchError(err)) console.warn(label, err);
  else console.error(label, err);
}
