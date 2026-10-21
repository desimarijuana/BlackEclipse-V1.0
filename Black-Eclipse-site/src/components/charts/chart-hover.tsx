'use client';

// ── The chart's hover layer ─────────────────────────────────────────────────
//
// A picture cannot be hovered. But the engine knows where each category sits
// on the picture and what each series' value is there, so it returns an
// INTERACTION MAP with the picture. This layer draws the pointer experience
// over it: a crosshair at the nearest category and a tooltip with the values.
//
// The map is in the PNG's own pixels; the layer converts it to percentages, so
// the picture can be any size on screen and the crosshair still lands on the
// right column. Nothing here invents a number: the values are the ones the
// picture was drawn from.

import { useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export interface ChartInteractionColumn {
  label: string;
  /** The column's x position, in the picture's pixels. */
  x: number;
  values: Array<{ name: string; value: number; color: string }>;
}

export interface ChartInteraction {
  width: number;
  height: number;
  plot: { left: number; right: number; top: number; bottom: number };
  columns: ChartInteractionColumn[];
}

export interface ChartHoverProps {
  interaction?: ChartInteraction | null;
  /** The number format for the values (e.g. a currency). */
  format?: (value: number) => string;
  className?: string;
}

export function ChartHover({ interaction, format, className }: ChartHoverProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [active, setActive] = useState<number | null>(null);

  const columns = interaction?.columns ?? [];
  const geometry = useMemo(() => {
    if (!interaction) return null;
    const { width, height, plot } = interaction;
    if (!width || !height) return null;
    return {
      // Percentages, so the layer scales with the picture.
      left: (plot.left / width) * 100,
      right: (plot.right / width) * 100,
      top: ((height - plot.bottom) / height) * 100,
      bottom: ((height - plot.top) / height) * 100,
      xs: columns.map((column) => (column.x / width) * 100),
    };
  }, [interaction, columns]);

  if (!geometry || columns.length === 0) return null;

  const onMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const host = hostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    if (!rect.width) return;
    const percent = ((event.clientX - rect.left) / rect.width) * 100;
    // The nearest column, within the plot's own x range.
    let nearest = -1;
    let best = Number.POSITIVE_INFINITY;
    geometry.xs.forEach((x, index) => {
      const distance = Math.abs(x - percent);
      if (distance < best) {
        best = distance;
        nearest = index;
      }
    });
    setActive(nearest >= 0 && best < 6 ? nearest : null);
  };

  const column = active != null ? columns[active] : null;
  const crosshairX = active != null ? geometry.xs[active] : null;

  return (
    <div
      ref={hostRef}
      className={cn('absolute inset-0', className)}
      onPointerMove={onMove}
      onPointerLeave={() => setActive(null)}
      data-testid="chart-hover"
    >
      {crosshairX != null && (
        <div
          className="pointer-events-none absolute w-px bg-foreground/25"
          style={{
            left: `${crosshairX}%`,
            top: `${geometry.top}%`,
            height: `${Math.max(0, geometry.bottom - geometry.top)}%`,
          }}
        />
      )}
      {column && crosshairX != null && (
        <div
          className="glass-tooltip pointer-events-none absolute z-20 min-w-[120px] px-2.5 py-1.5"
          style={{
            left: `${Math.min(crosshairX, 82)}%`,
            top: `${geometry.top + 2}%`,
          }}
          role="tooltip"
        >
          <div className="text-[10px] font-semibold text-foreground">{column.label}</div>
          <div className="mt-1 flex flex-col gap-0.5">
            {column.values.map((value) => (
              <div key={value.name} className="flex items-center gap-1.5 text-[10px]">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: value.color }}
                />
                <span className="text-muted-foreground">{value.name}</span>
                <span className="ml-auto font-mono font-semibold text-foreground">
                  {format ? format(value.value) : value.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ChartHover;
