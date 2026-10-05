'use client';

// ── StatusBar — reusable bottom status strip ─────────────────────────────────
// Shows version, feed indicators (EQ/FX/CM/FI/CR), session uptime, layout
// status, feeds connected, memory usage, API latency, a pending-orders badge,
// and a notification bell. Mount it under any CustomizableWorkspace.

import React, { useEffect, useState } from 'react';
import { Bell, Cpu, Gauge, LayoutGrid, Radio, Timer } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface StatusBarProps {
  /** App version string. */
  version?: string;
  /** Feed status per asset class: EQ/FX/CM/FI/CR. */
  feeds?: Record<string, boolean>;
  /** Number of connected feeds. */
  feedsConnected?: number;
  /** Pending orders count (badge). */
  pendingOrders?: number;
  /** Session start timestamp (ms) for uptime. */
  sessionStart?: number;
  /** Layout status label. */
  layoutStatus?: string;
  /** Notification count (bell badge). */
  notifications?: number;
  className?: string;
}

const DEFAULT_FEEDS: Record<string, boolean> = { EQ: true, FX: true, CM: true, FI: true, CR: true };

export function StatusBar({
  version = 'v0.1.0',
  feeds = DEFAULT_FEEDS,
  feedsConnected,
  pendingOrders = 0,
  sessionStart,
  layoutStatus = 'saved',
  notifications = 0,
  className,
}: StatusBarProps) {
  const [now, setNow] = useState(() => Date.now());
  const [latency, setLatency] = useState<number | null>(null);

  // Tick every second for uptime.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Measure API latency once on mount.
  useEffect(() => {
    const start = performance.now();
    fetch('/api/indices?market=US', { method: 'HEAD' })
      .then(() => setLatency(Math.round(performance.now() - start)))
      .catch(() => setLatency(null));
  }, []);

  const uptimeSec = sessionStart ? Math.max(0, Math.floor((now - sessionStart) / 1000)) : 0;
  const uptime = `${Math.floor(uptimeSec / 3600)}h ${Math.floor((uptimeSec % 3600) / 60)}m ${uptimeSec % 60}s`;

  const connected = feedsConnected ?? Object.values(feeds).filter(Boolean).length;
  const totalFeeds = Object.keys(feeds).length;

  return (
    <div className={cn('glass-card mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-2xl border border-border/10 px-4 py-2 text-[10px] font-mono text-muted-foreground', className)}>
      {/* Version */}
      <span className="font-bold text-foreground/80">{version}</span>

      {/* Feed indicators */}
      <span className="flex items-center gap-1.5">
        <Radio size={11} className="text-primary" />
        {Object.entries(feeds).map(([k, on]) => (
          <span key={k} className={cn('rounded px-1 py-0.5 text-[9px] font-bold', on ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400')}>
            {k}
          </span>
        ))}
      </span>

      {/* Session uptime */}
      <span className="flex items-center gap-1">
        <Timer size={11} /> {uptime}
      </span>

      {/* Layout status */}
      <span className="flex items-center gap-1">
        <LayoutGrid size={11} /> {layoutStatus}
      </span>

      {/* Feeds connected */}
      <span className="flex items-center gap-1">
        <Radio size={11} /> {connected}/{totalFeeds} feeds
      </span>

      {/* Memory usage */}
      <span className="flex items-center gap-1">
        <Cpu size={11} /> {memoryMB()} MB
      </span>

      {/* API latency */}
      <span className="flex items-center gap-1">
        <Gauge size={11} /> {latency != null ? `${latency}ms` : '—'}
      </span>

      {/* Pending orders badge */}
      {pendingOrders > 0 && (
        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[9px] font-bold text-amber-400">
          {pendingOrders} pending
        </span>
      )}

      {/* Notification bell */}
      <span className="relative ml-auto">
        <Bell size={13} className="text-muted-foreground hover:text-primary cursor-pointer" />
        {notifications > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-rose-500 text-[8px] font-bold text-white">
            {notifications}
          </span>
        )}
      </span>
    </div>
  );
}

function memoryMB(): string {
  if (typeof performance !== 'undefined' && 'memory' in performance) {
    const m = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
    if (m) return Math.round(m.usedJSHeapSize / 1024 / 1024).toString();
  }
  return '—';
}
