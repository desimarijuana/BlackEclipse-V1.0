// ── First-run gate decision (server-only) ───────────────────────────────────
// The app shell must NOT be mounted behind a first-run wizard.
//
// WHY: the shell opens long-lived SSE streams (`/api/ui/stream`,
// `/api/sdk/app/stream`) and a burst of boot requests. Browsers allow only six
// concurrent HTTP/1.1 connections per origin, and those streams hold their
// slots for the life of the page — so the wizard's own `POST /api/setup` could
// be queued behind them and never sent. That is the reported "stuck on
// Saving…" on a brand-new install (a warm install has less boot traffic, which
// is why it only reproduces for new users).
//
// The decision is deliberately conservative: anything other than a positive
// "this is a new install" renders the app. A failed or unreadable state read
// must never hide the product behind a wizard.

import { prisma } from "@/lib/db";
import { cache } from "react";
import { probeInstall } from "./existing-install";
import { ONBOARDING_CONFIG_KEY } from "./state";

export type OnboardingGate = "incomplete" | "complete" | "unknown";

/**
 * `incomplete` = a genuinely new install that should see the wizard alone.
 * `complete`   = an install that has finished (or predates) setup.
 * `unknown`    = the read failed; render the app rather than block it.
 *
 * Memoized per request (`cache`): the page and the layout both ask, and one
 * indexed read is enough. Outside a React request scope the wrapper degrades to
 * a plain call.
 */
export const onboardingGateState = cache(async (): Promise<OnboardingGate> => {
  // `next build` prerenders the static routes on a machine with no user data
  // and no request. Never open (or create) a database there: the layout would
  // otherwise run this read during the build.
  if (process.env.NEXT_PHASE === "phase-production-build") return "unknown";
  try {
    const row = await prisma.systemConfig.findUnique({
      where: { key: ONBOARDING_CONFIG_KEY },
      select: { value: true },
    });

    if (row?.value) {
      try {
        const parsed = JSON.parse(row.value) as { completed?: unknown };
        return parsed.completed === true ? "complete" : "incomplete";
      } catch {
        // A malformed flag is still a recorded setup: never re-show the wizard
        // for an install that has data because of a corrupt value.
        return "complete";
      }
    }

    const probe = await probeInstall();
    return probe.isNew ? "incomplete" : "complete";
  } catch {
    return "unknown";
  }
});
