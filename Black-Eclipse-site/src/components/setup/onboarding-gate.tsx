"use client";

import { useEffect, useState } from "react";
import type { SetupState } from "./types";
import { OnboardingShell } from "./onboarding-shell";

/**
 * Mounted in the root layout. It renders the full-screen setup experience when
 * the server says this is a genuinely new install, or when the user asks for it
 * with `?setup=1` (Settings → Run setup again). A failed state read never blocks
 * the app: the gate simply renders nothing.
 */
export function OnboardingGate({ setupPending = false }: { setupPending?: boolean }) {
  const [state, setState] = useState<SetupState | null>(null);
  // Capture the force flags during the FIRST render. The app shell rewrites the
  // URL (e.g. to ?tab=chat) as soon as it mounts, so reading it in an effect can
  // race and lose the request. `setupPending` is the server's decision for THIS
  // response: when the app shell was withheld, the wizard must show even if the
  // follow-up `/api/setup` read reports a completed install (another writer,
  // e.g. a theme save, can make the install probe flip).
  const [forced] = useState(() => {
    if (typeof window === "undefined") return setupPending;
    if (setupPending) return true;
    try {
      if (sessionStorage.getItem("be_setup_force") === "1") return true;
    } catch {
      /* private mode */
    }
    return new URLSearchParams(window.location.search).get("setup") === "1";
  });
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/setup", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`setup state answered HTTP ${res.status}`);
        return (await res.json()) as SetupState;
      })
      .then((data) => {
        if (!cancelled) setState(data);
      })
      .catch(() => {
        if (!cancelled) {
          setState(null);
        }
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const done = () => {
    // Drop the forced setup flag/query, but keep an existing tab deep link.
    try {
      sessionStorage.removeItem("be_setup_force");
    } catch {
      /* private mode */
    }
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    window.location.assign(tab ? `/?tab=${encodeURIComponent(tab)}` : "/");
  };

  if (!checked) return null;
  // A reply with the wrong shape is a failed state read, not a new install:
  // `OnboardingShell` builds its draft from `state.sources`, so rendering it
  // with a missing list white-screens the whole app.
  const unreadable = !state || !Array.isArray(state.sources);
  if (unreadable) {
    // The app shell was withheld for this response, so a failed read would
    // otherwise leave a bare "Starting Eclipse…" forever. Offer the one action
    // that can help, honestly labelled. When the shell IS mounted, keep the
    // gate's contract: render nothing and let the app work.
    if (!forced) return null;
    return (
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-background p-6">
        <div className="glass-card-strong w-full max-w-[420px] rounded-2xl border border-white/12 p-6">
          <h1 className="font-serif text-[18px] font-semibold text-foreground">
            Setup state unavailable
          </h1>
          <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
            Eclipse could not read the first-run state from its local database.
            Your data is untouched. Reload to try again, and check the app log
            if this repeats.
          </p>
          <button
            type="button"
            className="mt-4 inline-flex cursor-pointer items-center rounded-lg bg-primary px-4 py-2 text-[12.5px] font-semibold text-primary-foreground"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
  if (state.completed && !forced) return null;

  return <OnboardingShell state={state} onDone={done} />;
}
