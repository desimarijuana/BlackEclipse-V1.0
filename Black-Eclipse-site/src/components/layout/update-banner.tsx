"use client";

// ── In-app update notice ────────────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx), mirroring the other
// watchers. It asks the LOCAL server (/api/updates) whether a newer SIGNED
// release exists and shows a single glass notice when there is one.
//
// Deliberate choices:
//   * This banner only notifies. The acting surface is the title-bar download
//     button (update-button.tsx), which can stage a signed release after an
//     explicit click. Auto-applying code against a local financial DB without
//     consent is still not a trade worth making.
//   * Dismiss / skip are per-version and local-only.
//   * A failed check is silent here. "Couldn't check" belongs in Settings,
//     where the user asked; a banner that cries wolf on every offline launch
//     gets ignored.
//   * It renders through a portal so the frosted glass samples the real page.

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, RefreshCw, ShieldCheck, X } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { copyText } from "@/lib/desktop/clipboard";
import { saveUpdatePrefs } from "@/lib/updates/prefs";
import { useUpdateStatus } from "@/lib/updates/use-update-status";
import type { UpdateStatus } from "@/lib/updates/types";

export function UpdateBanner() {
  const [mounted, setMounted] = useState(false);
  // The title-bar button uses the same hook; the route's 6h manifest cache keeps
  // two consumers at one upstream fetch.
  const { status: checked, prefs } = useUpdateStatus();
  const [showCommand, setShowCommand] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const hidden =
    !checked?.available ||
    !checked.latestVersion ||
    checked.latestVersion === prefs.dismissedVersion ||
    checked.latestVersion === prefs.skippedVersion;

  if (!mounted || hidden || !checked) return null;

  const status: UpdateStatus = checked;

  const dismiss = () => {
    saveUpdatePrefs({ ...prefs, dismissedVersion: status.latestVersion });
  };

  const skip = () => {
    saveUpdatePrefs({ ...prefs, skippedVersion: status.latestVersion });
  };

  const copyCommand = async () => {
    // A refused copy opens the command as selectable text instead.
    if (!(await copyText("black update"))) {
      setShowCommand(true);
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
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
              Click the download icon in the title bar and choose Update now, or
              stop Eclipse and run this in the project folder:
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
