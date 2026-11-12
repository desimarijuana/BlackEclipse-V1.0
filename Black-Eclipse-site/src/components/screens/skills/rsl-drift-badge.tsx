"use client";

// A compact, read-only drift presence badge for the learning-journey header.
// It reads the same per-scope overview as the drift card and refreshes on the
// verify event and window focus; it never triggers a candidate or a change.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import { getEvolutionDriftScopesBrowser } from "@/lib/harness/clients/evolution-browser";
import type { EvolutionDriftScopes } from "@/lib/harness/clients/evolution-client";
import { EVOLUTION_VERIFIED_EVENT } from "@/lib/harness/evolution-events";
import { ALERT_NOTIFY_EVENT } from "@/lib/alerts/browser-notifier";
import type { NotificationRequest } from "@/lib/notifications/store";

const NOTIFIED_KEY = "eclipse.rsl.driftNotified";

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function unseenScopes(scopes: string[]): string[] {
  if (scopes.length === 0) return [];
  try {
    const raw = window.localStorage.getItem(NOTIFIED_KEY);
    const parsed = raw ? JSON.parse(raw) as { date?: string; scopes?: string[] } : {};
    if (parsed.date !== todayUtc()) return scopes;
    const seen = new Set(Array.isArray(parsed.scopes) ? parsed.scopes : []);
    return scopes.filter((scope) => !seen.has(scope));
  } catch {
    return scopes;
  }
}

function rememberScopes(scopes: string[]): void {
  try {
    const raw = window.localStorage.getItem(NOTIFIED_KEY);
    const parsed = raw ? JSON.parse(raw) as { date?: string; scopes?: string[] } : {};
    const seen = parsed.date === todayUtc() && Array.isArray(parsed.scopes)
      ? parsed.scopes
      : [];
    window.localStorage.setItem(NOTIFIED_KEY, JSON.stringify({
      date: todayUtc(),
      scopes: Array.from(new Set([...seen, ...scopes])),
    }));
  } catch {
    // A blocked storage API only means the alert can repeat.
  }
}

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
      const next = driftingScopes(await getEvolutionDriftScopesBrowser({
        includeGlobal: false,
      }));
      setScopes(next);
      const fresh = unseenScopes(next);
      if (fresh.length > 0) {
        const detail: NotificationRequest = {
          id: `drift:${todayUtc()}:${fresh.join(",")}`,
          title: t("evolution.drift.notifyTitle"),
          body: t("evolution.drift.notifyBody", { scopes: fresh.join(", ") }),
          tab: "skills",
          kind: "agent",
          sound: "notification",
        };
        window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
        rememberScopes(fresh);
      }
    } catch {
      setScopes([]);
    }
  }, [t]);

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
