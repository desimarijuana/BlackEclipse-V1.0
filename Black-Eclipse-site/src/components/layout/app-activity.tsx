import type { ReactNode } from "react";

/**
 * App-wide background activity: the boot loader's warm-ups, notification
 * pollers, the desktop session heartbeat, update checks and the shell guards.
 *
 * On a first run there is nothing to show behind the wizard and nothing worth
 * fetching: the user has not chosen sources or a model yet, and every one of
 * these requests competes for the browser's six HTTP/1.1 connections per origin
 * with the wizard's own `POST /api/setup`.
 *
 * `pending` comes from the server layout (`onboardingGateState`), not from a
 * client-side flag, so the server-rendered tree and the hydrated tree agree —
 * no hydration mismatch, and the loader's markup is never sent at all.
 */
export function AppActivity({
  pending,
  children,
}: {
  pending: boolean;
  children: ReactNode;
}) {
  if (pending) return null;
  return <>{children}</>;
}
