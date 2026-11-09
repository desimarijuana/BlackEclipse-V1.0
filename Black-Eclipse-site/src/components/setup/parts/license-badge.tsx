"use client";

import { cn } from "@/lib/utils";
import { commercialLabel } from "@/lib/setup/source-catalog";
import type { CommercialStatus } from "@/lib/setup/types";

const TONE: Record<CommercialStatus, string> = {
  ok: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  attribution: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  "personal-only": "border-rose-500/25 bg-rose-500/10 text-rose-300",
  verify: "border-white/15 bg-white/[0.04] text-muted-foreground",
};

export function LicenseBadge({ status, className }: { status: CommercialStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full border px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider",
        TONE[status],
        className,
      )}
    >
      {commercialLabel(status)}
    </span>
  );
}
