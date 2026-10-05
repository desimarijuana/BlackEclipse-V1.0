"use client";

// ── Theme full-screen preview launcher + floating Apply/Discard bar ─────────
// Split out of `customization-settings.tsx` to keep that panel under its size
// budget. Self-contained: owns no draft state, only the presentational launcher
// and the portaled control bar that hands the user the REAL app wearing the
// live-preview theme.

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, Maximize2, RotateCcw, Save, X } from "@/lib/icons";
import { Button } from "@/components/ui/button";

/**
 * Full-screen preview launcher. Instead of a tiny fake desktop, this hands the
 * user the REAL app — already wearing the live-preview theme — with a floating
 * Apply / Discard / Exit bar. The Settings modal is hidden (not unmounted) while
 * previewing, so the panel's draft state survives the round-trip.
 */
export function PreviewLauncher({
  active,
  onEnter,
  onExit,
  onApply,
  onDiscard,
  dirty,
}: {
  active: boolean;
  onEnter: () => void;
  onExit: () => void;
  onApply: () => void;
  onDiscard: () => void;
  dirty: boolean;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Escape returns to Settings — a predictable exit for a mode with no dialog
  // chrome of its own. Capture phase because the hidden base-ui dialog's dismiss
  // handler stops Escape propagation during the bubble phase.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      e.preventDefault();
      onExit();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [active, onExit]);

  // The bar is portaled to <body> because the Settings popup it lives in is
  // `display:none` while previewing — a child of a hidden ancestor would never
  // paint, but a portal escapes that.
  const bar = active && mounted
    ? createPortal(
        // Deliberately NOT a keyboard overlay: the whole point is to interact
        // with the real app, so page shortcuts must keep working.
        <div className="fixed inset-x-0 top-3 z-[200] flex justify-center px-3">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-primary/25 glass-card-strong px-3 py-2 shadow-2xl shadow-black/40">
            <span className="inline-flex items-center gap-1.5 px-1 text-xs font-semibold text-foreground">
              <Eye size={13} className="text-primary" />
              Previewing theme
            </span>
            <span className="hidden text-[10px] text-muted-foreground sm:inline">
              Interact with the real app. Nothing is saved until you apply.
            </span>
            <span className="mx-1 hidden h-4 w-px bg-border/50 sm:block" />
            <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={onDiscard} disabled={!dirty}>
              <RotateCcw className="mr-1 h-3.5 w-3.5" /> Discard
            </Button>
            <Button size="sm" className="rounded-xl cursor-pointer" onClick={onApply} disabled={!dirty}>
              <Save className="mr-1 h-3.5 w-3.5" /> Apply theme
            </Button>
            <Button size="sm" variant="ghost" className="rounded-xl cursor-pointer" onClick={onExit} title="Back to settings">
              <X className="mr-1 h-3.5 w-3.5" /> Exit preview
            </Button>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15 text-primary">
            <Maximize2 size={15} />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground">Preview on the real app</p>
            <p className="text-[10px] text-muted-foreground">Open the live app full screen to audition your draft theme in place.</p>
          </div>
        </div>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" onClick={onEnter}>
          <Eye className="mr-1 h-3.5 w-3.5" /> Enter full-screen preview
        </Button>
      </div>
      {bar}
    </>
  );
}
