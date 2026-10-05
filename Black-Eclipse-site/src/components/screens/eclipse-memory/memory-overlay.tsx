"use client";

// ── Eclipse-Memory overlay primitives ───────────────────────────────────────
// One place that owns every floating surface in the Memory Control Room, so the
// six hand-rolled drawers/modals cannot drift apart again.
//
// Why a portal is mandatory here: the Memory screen is rendered inside the app
// shell's `glass-card` container, which uses `backdrop-filter`/`transform` and is
// therefore a *containing block / backdrop root*. A `position: fixed` drawer
// rendered inline is scoped to that container — it clips, sits under the header
// and collides with the floating chat dock. `createPortal(document.body)` escapes
// that subtree so the overlay covers the real viewport (same lesson as the
// workspace/widget and Skills drawers).
//
// z-index tiers (app-wide convention): fullscreen panels z-[80..86] < floating
// chat dock z-[90] < drawers/dialogs z-[100] < toasts z-[110]. Memory overlays
// live at the drawer tier so they always sit above the dock instead of behind it.

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "@/lib/icons";
import { cn } from "@/lib/utils";

/** Shared behaviour for every overlay: Escape-to-close + body scroll lock. */
function useOverlayBehaviour(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);
}

/** Wait until mounted client-side before portaling (SSR-safe). */
function usePortalTarget() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted ? document.body : null;
}

/**
 * A right-side frosted-glass drawer — the default detail surface. Portaled to
 * <body>, width-tiered, with a sticky header (title + close) that never scrolls
 * away, Escape + backdrop close, and background scroll lock.
 */
export function MemoryDrawer({
  open,
  onClose,
  title,
  subtitle,
  width = "md",
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  /** `md` ≈ max-w-md (compact), `lg` ≈ max-w-lg (conflict review), `xl` ≈ max-w-xl (detail). */
  width?: "md" | "lg" | "xl";
  children: ReactNode;
  footer?: ReactNode;
}) {
  const target = usePortalTarget();
  useOverlayBehaviour(open, onClose);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const widthClass = width === "md" ? "max-w-md" : width === "lg" ? "max-w-lg" : "max-w-xl";

  if (!open || !target) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex justify-end" role="dialog" aria-modal="true">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        className={cn(
          "relative flex h-full w-full flex-col border-l border-white/10 glass-card-strong",
          widthClass,
        )}
      >
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-border/10 bg-background/70 px-5 py-3.5 backdrop-blur">
          <div className="min-w-0">
            <h3 className="truncate font-serif text-sm font-semibold tracking-tight text-foreground">{title}</h3>
            {subtitle ? <div className="mt-0.5 text-[10px] text-muted-foreground">{subtitle}</div> : null}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:text-foreground cursor-pointer"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <div className="sticky bottom-0 border-t border-border/10 bg-background/70 px-5 py-3 backdrop-blur">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    target,
  );
}

/** A centered frosted-glass modal for shorter, focused content. */
export function MemoryModal({
  open,
  onClose,
  title,
  width = "lg",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  width?: "md" | "lg" | "xl";
  children: ReactNode;
}) {
  const target = usePortalTarget();
  useOverlayBehaviour(open, onClose);
  const widthClass = width === "md" ? "max-w-md" : width === "lg" ? "max-w-3xl" : "max-w-4xl";

  if (!open || !target) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
      <div
        className={cn(
          "relative flex max-h-[85vh] w-full flex-col overflow-hidden rounded-2xl border border-white/10 glass-card-strong",
          widthClass,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border/10 px-4 py-3">
          <h3 className="truncate font-serif text-sm font-semibold text-foreground">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:text-foreground cursor-pointer"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>,
    target,
  );
}

/** A transient toast pinned bottom-right, above every other surface. */
export function useFlash(timeoutMs = 4000) {
  const [message, setMessage] = useState<string | null>(null);
  const flash = useCallback(
    (text: string) => {
      setMessage(text);
      setTimeout(() => setMessage(null), timeoutMs);
    },
    [timeoutMs],
  );
  return { message, flash };
}
