"use client";

// Shared, small UI primitives for the MCP settings surfaces. Kept in one place
// so the screen, the server editor and the lifecycle panel cannot drift.

import { cn } from "@/lib/utils";
import type { MCPEffect, MCPServerView } from "@/lib/harness/mcp-types";

export const EFFECT_LABEL: Record<MCPEffect, string> = {
  read: "Read-only",
  write: "Writes data",
  external_action: "External action",
  unknown: "Unknown effect",
};

export const EFFECT_CLASS: Record<MCPEffect, string> = {
  read: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  write: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  external_action: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  unknown: "border-border/40 bg-muted/30 text-muted-foreground",
};

export function Panel({ className, children, ...rest }: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)} {...rest}>
      {children}
    </div>
  );
}

export function EffectBadge({ effect }: { effect: MCPEffect }) {
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-bold border", EFFECT_CLASS[effect])}>
      {EFFECT_LABEL[effect]}
    </span>
  );
}

/**
 * An honest label + colour for every state the runtime can emit. A lazy server
 * is NOT connected; an unavailable runtime is not a server failure.
 */
export function stateDot(state: MCPServerView["state"], enabled: boolean): { ok: boolean; label: string; tone: "ok" | "warn" | "bad" | "idle" } {
  if (!enabled) return { ok: false, label: "Disabled", tone: "idle" };
  if (state === "connected") return { ok: true, label: "Connected", tone: "ok" };
  if (state === "lazy") return { ok: false, label: "Lazy (cached, not connected)", tone: "warn" };
  if (state === "unavailable") return { ok: false, label: "Runtime unavailable", tone: "warn" };
  if (state === "failed" || state === "failed_refused") return { ok: false, label: "Failed", tone: "bad" };
  if (state === "closed") return { ok: false, label: "Closed", tone: "idle" };
  if (state === "pending") return { ok: false, label: "Connecting…", tone: "warn" };
  return { ok: false, label: state, tone: "idle" };
}

export function StateDot({ tone }: { tone: "ok" | "warn" | "bad" | "idle" }) {
  const cls =
    tone === "ok" ? "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/60"
      : tone === "warn" ? "bg-amber-400"
        : tone === "bad" ? "bg-rose-400"
          : "bg-muted-foreground/40";
  return <span className={cn("w-2 h-2 rounded-full shrink-0", cls)} />;
}
