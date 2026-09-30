"use client";

// ── MCP server lifecycle / capability status (Phase 6.1) ────────────────────
// Renders the runtime's bounded lifecycle block honestly: retry attempts, last
// error code, keepalive failures, recycle reason, in-flight count and the call
// metrics trio. A value the runtime omits renders as an explicit unknown, never
// a fabricated zero.

import { cn } from "@/lib/utils";
import type { MCPServerView } from "@/lib/harness/mcp-types";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" | "bad" | "ok" }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</span>
      <span className={cn("text-[11px] font-mono",
        tone === "bad" ? "text-rose-400" : tone === "warn" ? "text-amber-300" : tone === "ok" ? "text-emerald-400" : "text-foreground")}>
        {value}
      </span>
    </div>
  );
}

function metric(value: unknown): string {
  return typeof value === "number" ? String(value) : "unknown";
}

export function MCPLifecyclePanel({ server }: { server: MCPServerView }) {
  const lifecycle = server.lifecycle;
  const metrics = lifecycle?.metrics;
  const lazy = server.lazy || lifecycle?.lazyActive;
  const cached = lifecycle?.cachedTools;

  return (
    <div className="rounded-xl border border-border/20 glass-card-subtle p-3.5 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Connection lifecycle</span>
        {lazy && (
          <span className="text-[10px] font-mono text-amber-300">
            Lazy{typeof cached === "number" ? ` · ${cached} cached tool(s)` : ""} — not connected; the first call will connect.
          </span>
        )}
      </div>
      {!lifecycle ? (
        <p className="text-[11px] text-muted-foreground/70">Lifecycle status is not available for this server.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Connect attempts" value={metric(lifecycle.initialAttempts)} />
            <Stat label="Reconnects" value={metric(lifecycle.reconnectAttempts)} />
            <Stat label="In flight" value={metric(lifecycle.inFlight)} />
            <Stat label="Keepalive failures" value={metric(lifecycle.keepaliveFailures)} tone={lifecycle.keepaliveFailures ? "warn" : undefined} />
            <Stat label="Last error" value={lifecycle.lastErrorCode || "none"} tone={lifecycle.lastErrorCode ? "bad" : undefined} />
            <Stat label="Recycled" value={lifecycle.recycledReason || "no"} />
            <Stat label="Retry budget" value={lifecycle.exhausted ? "exhausted" : "available"} tone={lifecycle.exhausted ? "bad" : "ok"} />
            <Stat label="Keepalive interval" value={typeof lifecycle.keepaliveInterval === "number" ? `${lifecycle.keepaliveInterval}s` : "off"} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Calls" value={metrics ? metric(metrics.calls) : "unknown"} />
            <Stat label="Errors" value={metrics ? metric(metrics.errors) : "unknown"} tone={metrics && metrics.errors ? "warn" : undefined} />
            <Stat label="Avg latency" value={metrics ? `${metric(metrics.avgLatencyMs)} ms` : "unknown"} />
          </div>
          {(lifecycle.sampling || lifecycle.interactions) && (
            <div className="border-t border-border/10 pt-2">
              <p className="text-[9px] uppercase tracking-widest text-muted-foreground mb-1">
                Server-initiated interactions (billed to your model budget when enabled)
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Sampling" value={JSON.stringify(lifecycle.sampling ?? {})} />
                <Stat label="Elicitation" value={JSON.stringify(lifecycle.interactions ?? {})} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
