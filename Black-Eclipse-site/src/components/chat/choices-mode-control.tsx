"use client";

// ── ChoicesModeControl — the composer's Auto / Choices / Off pill ────────────
//
// A per-question presentation preference, not a capability grant. "On" nudges
// the model to ask one question with clickable options before it starts an
// ambiguous turn; "Off" suppresses that nudge; "Auto" lets the base prompt's
// act-don't-ask guidance decide. The `clarify` tool itself stays read-only and
// the runtime still bounds one question per turn.

import { useEffect, useState } from "react";
import { ListChecks } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  choicesModeLabel,
  choicesModeTitle,
  getChoicesMode,
  nextChoicesMode,
  setChoicesMode,
  subscribeChoicesMode,
  type ChoicesMode,
} from "@/lib/agent/choices-mode";

export function ChoicesModeControl({ disabled = false }: { disabled?: boolean }) {
  const [mode, setMode] = useState<ChoicesMode>("auto");

  useEffect(() => {
    setMode(getChoicesMode());
    return subscribeChoicesMode(setMode);
  }, []);

  const on = mode === "on";
  return (
    <button
      type="button"
      suppressHydrationWarning
      disabled={disabled}
      title={choicesModeTitle(mode)}
      aria-label={`Choices mode: ${mode}`}
      aria-pressed={on}
      onClick={() => setChoicesMode(nextChoicesMode(mode))}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 h-7 rounded-full border text-xs font-medium whitespace-nowrap transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default",
        on
          ? "bg-primary/15 border-primary/40 text-primary"
          : mode === "off"
            ? "bg-accent/25 border-border/40 text-muted-foreground"
            : "bg-accent/25 border-border/25 text-muted-foreground hover:text-foreground hover:border-border/40",
      )}
    >
      <ListChecks size={12} className="shrink-0" />
      <span className="hidden min-[420px]:inline">{choicesModeLabel(mode)}</span>
      <span className="min-[420px]:hidden" aria-hidden>
        {on ? "C" : mode === "off" ? "C–" : "C"}
      </span>
    </button>
  );
}
