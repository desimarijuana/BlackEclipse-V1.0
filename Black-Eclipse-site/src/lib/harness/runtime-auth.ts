// Shared secret + callback base URL used between the Next.js front door and the
// Python runtime's JDdS data bridge. Reuses CRON_SECRET, which the API guard
// already trusts as `Authorization: Bearer <secret>`.

export function runtimeCallbackToken(): string | undefined {
  const secret = process.env.CRON_SECRET;
  return secret && secret !== "change-me-to-a-random-secret" ? secret : undefined;
}

/**
 * Base URL the Python runtime uses to call back into Next.js for JDdS data.
 * Inside this process that is always loopback.
 */
export function runtimeBaseUrl(): string {
  const port = process.env.PORT ?? "3000";
  return process.env.HARNESS_CALLBACK_URL ?? `http://127.0.0.1:${port}`;
}
