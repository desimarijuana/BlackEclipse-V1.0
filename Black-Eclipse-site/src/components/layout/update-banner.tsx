"use client";

// ── In-app update notice ────────────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx), mirroring the other
// watchers. It asks the LOCAL server (/api/updates) whether a newer SIGNED
// release exists and shows a single glass notice when there is one.
//
// Deliberate choices:
//   * Notify only. The browser cannot rebuild a self-hosted install, and
//     auto-applying code against a local financial DB without consent is not a
//     trade worth making. The notice explains the one command that updates.
//   * Dismiss / skip are per-version and local-only.
//   * A failed check is silent here. "Couldn't check" belongs in Settings,
//     where the user asked; a banner that cries wolf on every offline launch
//     gets ignored.
//   * It renders through a portal so the frosted glass samples the real page.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, RefreshCw, ShieldCheck, X } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import {
  DEFAULT_UPDATE_PREFS,
  loadUpdatePrefs,
  saveUpdatePrefs,
  subscribeUpdatePrefs,
  type UpdatePrefs,
} from "@/lib/updates/prefs";
import type { UpdateStatus } from "@/lib/updates/types";

const FIRST_CHECK_MS = 6_000;
const RECHECK_MS = 6 * 60 * 60 * 1000;

export function UpdateBanner() {
  const [mounted, setMounted] = useState(false);
  // Start from the SAME value on the server and the first client render. Reading
  // localStorage in the initializer changes the client tree and triggers a
  // hydration mismatch (#418); load it in the effect instead.
  const [prefs, setPrefs] = useState<UpdatePrefs>(DEFAULT_UPDATE_PREFS);
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [showCommand, setShowCommand] = useState(false);
  const [copied, setCopied] = useState(false);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  useEffect(() => {
    setMounted(true);
    const sync = () => setPrefs(loadUpdatePrefs());
    sync();
    return subscribeUpdatePrefs(sync);
  }, []);

  useEffect(() => {
    if (!prefs.enabled) {
      setStatus(null);
      return;
    }

    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch("/api/updates", { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as UpdateStatus;
        if (cancelled) return;
        if (!data?.ok || !data.available || !data.latestVersion) return;
        const current = prefsRef.current;
        if (
          data.latestVersion === current.skippedVersion ||
          data.latestVersion === current.dismissedVersion
        ) {
          return;
        }
        setStatus(data);
      } catch {
        /* offline / server restarting — stay quiet, try again next tick */
      }
    };

    const first = window.setTimeout(check, FIRST_CHECK_MS);
    const timer = window.setInterval(check, RECHECK_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [prefs.enabled]);

  if (!mounted || !status?.available || !status.latestVersion) return null;

  const dismiss = () => {
    const next = { ...prefs, dismissedVersion: status.latestVersion };
    setPrefs(next);
    saveUpdatePrefs(next);
    setStatus(null);
  };

  const skip = () => {
    const next = { ...prefs, skippedVersion: status.latestVersion };
    setPrefs(next);
    saveUpdatePrefs(next);
    setStatus(null);
  };

  const copyCommand = async () => {
    try {
      await navigator.clipboard.writeText("black update");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setShowCommand(true);
    }
  };

  return createPortal(
    <div
      className="fixed bottom-4 right-4 z-[70] w-[calc(100vw-2rem)] max-w-sm"
      role="status"
      aria-live="polite"
    >
      <div className="glass-card-strong rounded-2xl border border-primary/25 p-4 shadow-2xl space-y-3">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Download size={16} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold tracking-tight">
              Eclipse v{status.latestVersion} is available
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              You&apos;re on v{status.currentVersion}. The release manifest is
              signature-checked before this notice appears.
            </p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss update notice"
            className="shrink-0 rounded-lg p-1 text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>

        {status.mandatory && (
          <p className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-1.5 text-[10px] text-amber-200/90">
            This release is required to keep receiving data updates.
          </p>
        )}

        {showCommand ? (
          <div className="space-y-2">
            <p className="text-[11px] text-muted-foreground">
              Stop Eclipse, then run this in the project folder:
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 font-mono text-[11px]">
                black update
              </code>
              <Button
                size="sm"
                variant="outline"
                className="cursor-pointer rounded-lg"
                onClick={() => void copyCommand()}
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground/80">
              <ShieldCheck size={11} className="shrink-0" />
              It backs up your database, verifies the release tag, and rolls
              back if the build fails.
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              className="cursor-pointer rounded-xl"
              onClick={() => {
                setShowCommand(true);
                void copyCommand();
              }}
            >
              <RefreshCw size={13} className="mr-1" />
              How to update
            </Button>
            {status.notesUrl && (
              <a
                href={status.notesUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-xl border border-white/10 px-2.5 py-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              >
                What&apos;s new
                <ExternalLink size={11} />
              </a>
            )}
            <button
              type="button"
              onClick={skip}
              className="ml-auto text-[10px] text-muted-foreground/70 underline-offset-2 hover:text-muted-foreground hover:underline cursor-pointer"
            >
              Skip this version
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
