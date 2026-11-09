"use client";

import { cn } from "@/lib/utils";

/**
 * A real switch: a 44×24 track with a 20px knob, a visible On/Off label, a
 * focus ring and a disabled state. No nested button, no cut-off knob.
 */
export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <span className="inline-flex shrink-0 items-center gap-2">
      <span className={cn("text-[9px] font-medium tabular-nums", checked ? "text-emerald-300" : "text-muted-foreground/60")}>
        {checked ? "On" : "Off"}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full border p-0.5 transition-colors outline-none cursor-pointer",
          "focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-40",
          checked
            ? "border-emerald-400/40 bg-emerald-500/80"
            : "border-white/15 bg-white/[0.06]",
        )}
      >
        <span
          className={cn(
            "block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200",
            checked ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    </span>
  );
}
