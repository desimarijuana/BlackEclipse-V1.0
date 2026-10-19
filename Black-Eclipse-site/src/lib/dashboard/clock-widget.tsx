'use client';

import React, { useEffect, useState } from 'react';
import { Clock } from '@/lib/icons';
import type { WidgetPlacement } from '@/lib/workspace/types';

export interface ClockConfig {
  timezone: string;
  format: '12h' | '24h';
  showSeconds: boolean;
  showDate: boolean;
  label: string;
}

export const DEFAULT_CLOCK_CONFIG: ClockConfig = {
  timezone: '',
  format: '24h',
  showSeconds: true,
  showDate: true,
  label: 'Clock',
};

export function normalizeClockConfig(raw: Record<string, unknown> | undefined): ClockConfig {
  const value = raw ?? {};
  const timezone = typeof value.timezone === 'string' ? value.timezone.trim() : '';
  return {
    timezone,
    format: value.format === '12h' ? '12h' : '24h',
    showSeconds: value.showSeconds !== false,
    showDate: value.showDate !== false,
    label: typeof value.label === 'string' && value.label.trim() ? value.label.trim() : DEFAULT_CLOCK_CONFIG.label,
  };
}

export interface ClockDisplay {
  time: string;
  date: string;
  zone: string;
  error: string | null;
}

export function clockDisplay(now: Date, config: ClockConfig): ClockDisplay {
  const zone = config.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'local';
  try {
    const time = new Intl.DateTimeFormat('en-GB', {
      timeZone: config.timezone || undefined,
      hour: '2-digit',
      minute: '2-digit',
      ...(config.showSeconds ? { second: '2-digit' } : {}),
      hour12: config.format === '12h',
    }).format(now);
    const date = config.showDate
      ? new Intl.DateTimeFormat('en-GB', {
          timeZone: config.timezone || undefined,
          weekday: 'short',
          day: '2-digit',
          month: 'short',
          year: 'numeric',
        }).format(now)
      : '';
    return { time, date, zone, error: null };
  } catch {
    return {
      time: '--:--',
      date: '',
      zone: config.timezone,
      error: `UNAVAILABLE — unknown timezone "${config.timezone}".`,
    };
  }
}

export function ClockWidget({ placement }: { placement: WidgetPlacement }) {
  const config = normalizeClockConfig(placement.config);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const delay = 1000 - (Date.now() % 1000);
    const timeout = setTimeout(() => {
      setNow(new Date());
      timer = setInterval(() => setNow(new Date()), 1000);
    }, delay);
    return () => {
      clearTimeout(timeout);
      if (timer) clearInterval(timer);
    };
  }, []);

  const display = clockDisplay(now, config);

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-3 flex items-center justify-between gap-2 border-b border-border/10 pb-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Clock size={14} className="shrink-0 text-primary" />
          <h3 className="truncate font-serif text-sm font-semibold text-foreground">{config.label}</h3>
        </div>
        <span className="shrink-0 font-mono text-[9px] text-muted-foreground/70">{display.zone}</span>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        {display.error ? (
          <p className="max-w-[30ch] text-xs italic text-amber-400/80">{display.error}</p>
        ) : (
          <>
            <p className="font-mono text-4xl font-semibold tabular-nums tracking-tight text-foreground">{display.time}</p>
            {display.date && <p className="mt-2 text-xs text-muted-foreground">{display.date}</p>}
          </>
        )}
      </div>
    </div>
  );
}
