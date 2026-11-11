"use client";

import { Check } from "@/lib/icons";
import { cn } from "@/lib/utils";

export function CheckRow({
  checked,
  onChange,
  children,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2.5 text-[11.5px] leading-relaxed text-muted-foreground",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
          "border-white/25 bg-white/[0.03]",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-ring/60",
          checked && "border-primary bg-primary text-primary-foreground",
        )}
      >
        {checked && <Check size={10} weight="bold" />}
      </span>
      <span>{children}</span>
    </label>
  );
}
