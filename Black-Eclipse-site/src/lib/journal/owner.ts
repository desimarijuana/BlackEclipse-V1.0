// ── Journal ownership resolution (server-only) ───────────────────────────────
// The journal is per-user when authentication is active, and the single guest
// profile when it is off. This is the ONE place that decision is made: every
// journal query already receives the id returned by `getOrCreateProfile`, so
// scoping the profile is enough to scope trades, links, reviews and analytics.
//
// Fail closed: if the deployment requires auth and a request somehow reaches a
// journal route without a live session, we do not fall back to the shared guest
// profile.

import { cookies } from "next/headers";
import { authConfig } from "@/lib/auth/config";
import { getAuthStore } from "@/lib/auth/store";
import { AUTH_COOKIE, verifySessionToken } from "@/lib/auth/token";
import { prisma } from "@/lib/db";

export class JournalAuthRequired extends Error {
  readonly status = 401;
  constructor() {
    super("Sign in required");
    this.name = "JournalAuthRequired";
  }
}

/** The authenticated user id for this request, or null when auth is off. */
export async function currentJournalUserId(): Promise<string | null> {
  try {
    const jar = await cookies();
    const token = jar.get(AUTH_COOKIE)?.value;
    if (!token) return null;
    const sessionId = await verifySessionToken(token);
    if (!sessionId) return null;
    const store = getAuthStore();
    const session = store.resolveSession(sessionId);
    if (!session) return null;
    const user = store.getUserById(session.userId);
    return user && !user.disabled ? user.id : null;
  } catch {
    // No request context (CLI seeds, tests) or a bad cookie: anonymous.
    return null;
  }
}

/**
 * Whether this request may use the shared guest profile. Only true when auth is
 * explicitly/auto resolved off, or when there is no request context at all.
 */
export function mayUseGuestProfile(): boolean {
  return !authConfig().required;
}

/**
 * One-time upgrade path: the FIRST authenticated user adopts the pre-auth guest
 * journal instead of starting empty. Safe by construction:
 *  - it never runs once any user-owned profile exists;
 *  - it only touches `userId IS NULL` rows;
 *  - it is best-effort and must never block login.
 *
 * A second user never inherits anything.
 */
export async function claimGuestJournalForUser(userId: string): Promise<void> {
  const mine = await prisma.journalProfile.findFirst({
    where: { userId },
    select: { id: true },
  });
  if (mine) return;
  const anyUserProfile = await prisma.journalProfile.findFirst({
    where: { userId: { not: null } },
    select: { id: true },
  });
  if (anyUserProfile) return;
  const guest = await prisma.journalProfile.findFirst({
    where: { userId: null },
    orderBy: { createdAt: "asc" },
    select: { id: true },
  });
  if (!guest) return;
  // Conditional write: two concurrent first sessions cannot both claim it.
  await prisma.journalProfile.updateMany({
    where: { id: guest.id, userId: null },
    data: { userId },
  });
}
