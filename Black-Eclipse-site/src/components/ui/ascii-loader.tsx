'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

// ── Plus-X 5x5 grid loader ─────────────────────────────────────────────────
// A 25-dot grid in a quiet grey. A plus (cross) and an X trade places around
// the cycle — one fades in while the other holds, the same aesthetic as the
// reference loader it replaces. Animation is JS-driven (a rAF ticker sampling
// a 2.2s phase map), so it ALWAYS animates and does not depend on CSS
// keyframes.

const SIZE = 5;
const PITCH = 20;
const OFF = 10;
const CYCLE = 2200; // one full plus↔X cycle, ms
const HALF = CYCLE / 2;

// Dots that form the plus (delay 0) and the X (delay half a cycle).
const PLUS_X: Array<{ r: number; c: number; delay: number }> = [
  { r: 0, c: 2, delay: 0 }, { r: 1, c: 2, delay: 0 }, { r: 2, c: 2, delay: 0 }, { r: 3, c: 2, delay: 0 }, { r: 4, c: 2, delay: 0 },
  { r: 2, c: 0, delay: 0 }, { r: 2, c: 1, delay: 0 }, { r: 2, c: 3, delay: 0 }, { r: 2, c: 4, delay: 0 },
  { r: 0, c: 0, delay: HALF }, { r: 0, c: 4, delay: HALF }, { r: 1, c: 1, delay: HALF }, { r: 1, c: 3, delay: HALF },
  { r: 3, c: 1, delay: HALF }, { r: 3, c: 3, delay: HALF }, { r: 4, c: 0, delay: HALF }, { r: 4, c: 4, delay: HALF },
];

const SHAPE_DELAY = new Map<string, number>(PLUS_X.map((d) => [`${d.r}-${d.c}`, d.delay]));

const K0 = 0.08;
const RISE_END = CYCLE * 0.14;
const HOLD_END = CYCLE * 0.72;
function envelope(ph: number): number {
  if (ph < RISE_END) return K0 + (ph / RISE_END) * (1 - K0);
  if (ph < HOLD_END) return 1 - ((ph - RISE_END) / (HOLD_END - RISE_END)) * 0.08;
  return 0.92 - ((ph - HOLD_END) / (CYCLE - HOLD_END)) * (0.92 - K0);
}

/** Pure 5x5 plus/X grid spinner, small and grey. Animates unconditionally. */
export function DotGrid({ size = 32, className }: { size?: number; className?: string }) {
  const [t, setT] = useState(0);

  useEffect(() => {
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      setT((now - start) % CYCLE);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Loading"
      className={cn('shrink-0 text-muted-foreground', className)}
    >
      {Array.from({ length: SIZE }).map((_, r) =>
        Array.from({ length: SIZE }).map((_, c) => {
          const cx = c * PITCH + OFF;
          const cy = r * PITCH + OFF;
          const delay = SHAPE_DELAY.get(`${r}-${c}`);
          const phase = delay !== undefined ? (((t - delay) % CYCLE) + CYCLE) % CYCLE : 0;
          const active = delay !== undefined;
          return (
            <circle
              key={`${r}-${c}`}
              cx={cx}
              cy={cy}
              r={active ? 5 : 4}
              fill="currentColor"
              opacity={active ? envelope(phase) : 0.1}
            />
          );
        })
      )}
    </svg>
  );
}

export function AsciiProgress({
  pct,
  label,
  className,
  size = 32,
}: {
  pct: number;
  label?: string;
  className?: string;
  size?: number;
}) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-3 font-mono text-[11px] w-fit max-w-full', className)}
      role="status"
      aria-live="polite"
      aria-label={`Loading ${Math.floor(pct)}%`}
    >
      <div className="flex items-center justify-center">
        <DotGrid size={size} />
      </div>
      <div className="flex items-center justify-center gap-2.5">
         <span className="text-muted-foreground font-bold tabular-nums">
           {Math.floor(pct)}%
         </span>
        {label && <span className="text-muted-foreground/60 truncate">· {label}</span>}
      </div>
    </div>
  );
}

export function AsciiLoaderPanel({ pct, label }: { pct: number; label?: string }) {
  return (
    <div className="w-full flex items-center justify-center py-10">
      <AsciiProgress pct={pct} label={label} size={40} />
    </div>
  );
}
