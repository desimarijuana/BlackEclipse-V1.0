"use client";

// A compact, read-only drift presence badge for the learning-journey header.
// It reads the same per-scope overview as the drift card and refreshes on the
// verify event and window focus; it never triggers a candidate or a change.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import { getEvolutionDriftScopesBrowser } from "@/lib/harness/evolution-browser";
import type { EvolutionDriftScopes } from "@/lib/harness/evolution-client";
import { EVOLUTION_VERIFIED_EVENT } from "@/lib/harness/evolution-events";

export function driftingScopes(overview: EvolutionDriftScopes | null): string[] {
  return (overview?.signals ?? [])
    .filter((row) => row.signal.status === "drift")
    .map((row) => row.scope);
}

export function RslDriftBadge() {
  const t = useT();
  const [scopes, setScopes] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      setScopes(driftingScopes(await getEvolutionDriftScopesBrowser({
        includeGlobal: false,
      })));
    } catch {
      setScopes([]);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const handler = () => { void load(); };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    window.addEventListener("focus", handler);
    return () => {
      window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
      window.removeEventListener("focus", handler);
    };
  }, [load]);

  if (scopes.length === 0) return null;

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[9px] text-rose-300"
      title={scopes.join(", ")}
    >
      {t("evolution.drift.badge", { count: scopes.length })}
    </span>
  );
}
