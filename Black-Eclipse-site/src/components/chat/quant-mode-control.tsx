"use client";

// ── QuantModeControl — the composer's Auto / Quant / Off pill ────────────────
//
// A per-question presentation preference, not a capability grant. "On" opts the
// turn into the quant protocol; "Off" suppresses it; "Auto" lets the runtime's
// deterministic classifier decide. The server validates the value, and the
// Python quant layer still grants nothing it did not already have.

import { useEffect, useState } from "react";
import { FlaskConical } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  getQuantMode,
  nextQuantMode,
  quantModeLabel,
  quantModeTitle,
  setQuantMode,
  subscribeQuantMode,
  type QuantMode,
} from "@/lib/agent/quant-mode";

export function QuantModeControl({ disabled = false }: { disabled?: boolean }) {
  const [mode, setMode] = useState<QuantMode>("auto");

  useEffect(() => {
    setMode(getQuantMode());
    return subscribeQuantMode(setMode);
  }, []);

  const on = mode === "on";
  return (
    <button
      type="button"
      suppressHydrationWarning
      disabled={disabled}
      title={quantModeTitle(mode)}
      aria-label={`Quant mode: ${mode}`}
      aria-pressed={on}
      onClick={() => setQuantMode(nextQuantMode(mode))}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 h-7 rounded-full border text-xs font-medium whitespace-nowrap transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default",
        on
          ? "bg-primary/15 border-primary/40 text-primary"
          : mode === "off"
            ? "bg-accent/25 border-border/40 text-muted-foreground"
            : "bg-accent/25 border-border/25 text-muted-foreground hover:text-foreground hover:border-border/40",
      )}
    >
      <FlaskConical size={12} className="shrink-0" />
      <span className="hidden min-[420px]:inline">{quantModeLabel(mode)}</span>
      <span className="min-[420px]:hidden" aria-hidden>
        {on ? "Q" : mode === "off" ? "Q–" : "Q"}
      </span>
    </button>
  );
}
