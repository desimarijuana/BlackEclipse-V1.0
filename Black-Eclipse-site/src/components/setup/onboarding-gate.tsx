"use client";

import { useEffect, useState } from "react";
import type { SetupState } from "./types";
import { OnboardingShell } from "./onboarding-shell";

/**
 * Mounted in the root layout. It renders the full-screen setup experience only
 * when the server says this is a genuinely new install, or when the user asks
 * for it with `?setup=1` (Settings → Run setup again). A failed state read never
 * blocks the app: the gate simply renders nothing.
 */
export function OnboardingGate() {
  const [state, setState] = useState<SetupState | null>(null);
  // Capture the force flag during the FIRST render. The app shell rewrites the
  // URL (e.g. to ?tab=chat) as soon as it mounts, so reading it in an effect can
  // race and lose the request.
  const [forced] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("setup") === "1";
  });
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/setup", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) return null;
        return (await res.json()) as SetupState;
      })
      .then((data) => {
        if (!cancelled) setState(data);
      })
      .catch(() => {
        if (!cancelled) setState(null);
      })
      .finally(() => {
        if (!cancelled) setChecked(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const done = () => {
    // Drop the forced query so a refresh does not reopen a completed setup.
    window.location.assign("/");
  };

  if (!checked) return null;
  if (!state) return null;
  if (state.completed && !forced) return null;

  return <OnboardingShell state={state} onDone={done} />;
}
