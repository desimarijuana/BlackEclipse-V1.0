'use client';

import React, { useId } from 'react';
import { ArrowDownRight, ArrowUpRight, Info, Minus } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { Tone } from '@/lib/dashboard/home-model';

export const TONE_TEXT: Record<Tone, string> = {
  bullish: 'text-emerald-400',
  bearish: 'text-rose-400',
  neutral: 'text-zinc-300',
  unavailable: 'text-muted-foreground',
};

export const TONE_DOT: Record<Tone, string> = {
  bullish: 'bg-emerald-400',
  bearish: 'bg-rose-400',
  neutral: 'bg-zinc-300',
  unavailable: 'bg-muted-foreground',
};

export const SECTOR_COLORS = ['rgba(255,255,255,0.95)', 'rgba(255,255,255,0.80)', 'rgba(255,255,255,0.65)', 'rgba(255,255,255,0.52)', 'rgba(255,255,255,0.42)', 'rgba(255,255,255,0.34)', 'rgba(255,255,255,0.27)', 'rgba(255,255,255,0.20)'];

export function toneForChange(value: number): Tone {
  if (value > 0.0001) return 'bullish';
  if (value < -0.0001) return 'bearish';
  return 'neutral';
}

export function formatSignedPct(value: number, digits = 2): string {
  const rounded = Number(value.toFixed(digits));
  return `${rounded >= 0 ? '+' : ''}${rounded.toFixed(digits)}%`;
}

export function formatPct(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

export function formatCompactMoney(value: number, currency = 'USD'): string {
  const symbol = currency === 'USD' || currency === '$' ? '$' : `${currency} `;
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${symbol}${(value / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${symbol}${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `${symbol}${(value / 1_000).toFixed(1)}K`;
  return `${symbol}${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatMoney(value: number, currency = 'USD'): string {
  const symbol = currency === 'USD' || currency === '$' ? '$' : `${currency} `;
  return `${symbol}${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPrice(value: number, currency = 'USD'): string {
  const symbol = currency === 'USD' || currency === '$' ? '$' : `${currency} `;
  const digits = Math.abs(value) >= 1000 ? 2 : Math.abs(value) >= 1 ? 2 : 6;
  return `${symbol}${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function formatAge(value: Date | number | string | null): string {
  if (value == null) return '—';
  const date = value instanceof Date ? value : new Date(value);
  const age = Date.now() - date.getTime();
  if (!Number.isFinite(age) || age < 0) return 'now';
  if (age < 60_000) return 'now';
  if (age < 3_600_000) return `${Math.floor(age / 60_000)}m ago`;
  if (age < 86_400_000) return `${Math.floor(age / 3_600_000)}h ago`;
  return `${Math.floor(age / 86_400_000)}d ago`;
}

export function shortDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function HomeCard({
  children,
  className,
  accent = false,
}: {
  children: React.ReactNode;
  className?: string;
  accent?: boolean;
}) {
  return (
    <section
      className={cn(
        'relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-white/10 glass-card p-4 md:p-5',
        accent && 'border-white/15',
        className,
      )}
    >
      {accent && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent"
        />
      )}
      {children}
    </section>
  );
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn('text-[10px] font-medium uppercase tracking-[0.18em] text-white/45', className)}>
      {children}
    </p>
  );
}

export function CardTitle({
  eyebrow,
  title,
  right,
  className,
}: {
  eyebrow: string;
  title?: string;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        <Eyebrow>{eyebrow}</Eyebrow>
        {title && <h3 className="mt-1 truncate text-sm font-medium text-foreground">{title}</h3>}
      </div>
      {right}
    </div>
  );
}

export function Pill({
  children,
  tone = 'neutral',
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]',
        TONE_TEXT[tone],
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', TONE_DOT[tone])} />
      {children}
    </span>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div className={cn('rounded-xl border border-white/5 bg-white/[0.025] px-3 py-2.5', className)}>
      <p className="text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">{label}</p>
      <p className={cn('mt-1 truncate text-lg font-semibold tabular-nums text-foreground', tone && TONE_TEXT[tone])}>
        {value}
      </p>
      {sub && <p className="mt-0.5 truncate text-[10px] text-muted-foreground/80">{sub}</p>}
    </div>
  );
}

export function ChangeText({
  value,
  digits = 2,
  className,
  suffix,
}: {
  value: number | null;
  digits?: number;
  className?: string;
  suffix?: React.ReactNode;
}) {
  if (value == null || !Number.isFinite(value)) {
    return <span className={cn('tabular-nums text-muted-foreground', className)}>—</span>;
  }
  const Icon = value > 0.0001 ? ArrowUpRight : value < -0.0001 ? ArrowDownRight : Minus;
  return (
    <span className={cn('inline-flex items-center gap-0.5 tabular-nums', TONE_TEXT[toneForChange(value)], className)}>
      <Icon size={12} />
      {formatSignedPct(value, digits)}
      {suffix}
    </span>
  );
}

function buildPath(values: number[], close: boolean): string {
  if (values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100;
    const y = 36 - ((value - min) / span) * 32;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return `M${points.join(' L')}${close ? ' L100,40 L0,40 Z' : ''}`;
}

export function AreaSpark({
  values,
  className,
  stroke = '#e5e7eb',
  fill = true,
  strokeWidth = 1.6,
}: {
  values: number[];
  className?: string;
  stroke?: string;
  fill?: boolean;
  strokeWidth?: number;
}) {
  const id = useId().replace(/:/g, '');
  if (values.length < 2) {
    return <div className={cn('flex h-full w-full items-center justify-center text-[10px] text-muted-foreground/60', className)}>UNAVAILABLE</div>;
  }
  const path = buildPath(values, false);
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className={cn('h-full w-full overflow-visible', className)} aria-hidden>
      {fill && (
        <>
          <defs>
            <linearGradient id={`fill-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={buildPath(values, true)} fill={`url(#fill-${id})`} />
        </>
      )}
      <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

interface WeatherPoint {
  index: number;
  tone: Tone;
}

function weatherPoints(closes: number[]): WeatherPoint[] {
  const out: WeatherPoint[] = [];
  for (let index = 0; index < closes.length; index += 1) {
    if (index < 20) {
      out.push({ index, tone: 'neutral' });
      continue;
    }
    const window = closes.slice(index - 19, index + 1);
    const average = window.reduce((sum, value) => sum + value, 0) / window.length;
    const deviation = average > 0 ? (closes[index] / average - 1) * 100 : 0;
    out.push({ index, tone: deviation > 1 ? 'bullish' : deviation < -1 ? 'bearish' : 'neutral' });
  }
  return out;
}

function weatherRuns(points: WeatherPoint[]): Array<{ tone: Tone; points: WeatherPoint[] }> {
  const runs: Array<{ tone: Tone; points: WeatherPoint[] }> = [];
  for (const point of points) {
    const last = runs[runs.length - 1];
    if (last && last.tone === point.tone) last.points.push(point);
    else runs.push({ tone: point.tone, points: [point] });
  }
  return runs;
}

export function WeatherLine({
  closes,
  dates,
  stale = false,
  className,
}: {
  closes: number[];
  dates: string[];
  stale?: boolean;
  className?: string;
}) {
  if (closes.length < 2) {
    return (
      <div className={cn('flex h-32 items-center justify-center rounded-xl border border-white/5 bg-white/[0.02] text-[10px] text-muted-foreground/60', className)}>
        UNAVAILABLE
      </div>
    );
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const project = (point: WeatherPoint) => {
    const x = (point.index / (closes.length - 1)) * 100;
    const y = 36 - ((closes[point.index] - min) / span) * 32;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };
  const points = weatherPoints(closes);
  const runs = weatherRuns(points);
  const strokeFor: Record<Tone, string> = {
    bullish: '#34d399',
    bearish: '#fb7185',
    neutral: '#e5e7eb',
    unavailable: '#94a3b8',
  };
  const first = dates[0] ? shortDate(dates[0]) : '';
  const mid = dates[Math.floor(dates.length / 2)] ? shortDate(dates[Math.floor(dates.length / 2)]) : '';
  const last = dates[dates.length - 1] ? shortDate(dates[dates.length - 1]) : '';

  return (
    <div className={cn('min-w-0', className)}>
      <div className="relative h-32 w-full">
        <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-full w-full" aria-hidden>
          {[8, 20, 32].map((y) => (
            <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
          ))}
          {runs.map((run, index) => {
            const start = Math.max(0, run.points[0].index - 1);
            const slice = points.slice(start, run.points[run.points.length - 1].index + 1);
            return (
              <polyline
                key={`${run.tone}-${index}`}
                points={slice.map(project).join(' ')}
                fill="none"
                stroke={strokeFor[run.tone]}
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
        {stale && (
          <span className="absolute right-0 top-0 rounded-full border border-white/15 bg-white/[0.06] px-2 py-0.5 text-[9px] uppercase tracking-[0.12em] text-white/60">
            stale
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center justify-between text-[9px] uppercase tracking-[0.12em] text-muted-foreground/50">
        <span>{first}</span>
        <span>{mid}</span>
        <span>{last}</span>
      </div>
      <div className="mt-2 flex items-center gap-3 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/70">
        <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Bullish</span>
        <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-zinc-300" />Neutral</span>
        <span className="inline-flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-rose-400" />Bearish</span>
      </div>
    </div>
  );
}

export function HealthRing({ score, className }: { score: number | null; className?: string }) {
  const size = 116;
  const thickness = 10;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = score == null ? 0 : Math.max(0, Math.min(100, score));
  const offset = circumference * (1 - value / 100);
  const color = score == null ? '#94a3b8' : score >= 70 ? '#34d399' : score >= 55 ? '#e5e7eb' : '#fb7185';
  return (
    <div className={cn('relative inline-flex shrink-0 items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={thickness} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold tabular-nums text-foreground">{score == null ? '—' : score}</span>
        <span className="text-[8px] font-medium uppercase tracking-[0.18em] text-muted-foreground/70">score</span>
      </div>
    </div>
  );
}

export function SplitBar({
  segments,
  className,
}: {
  segments: Array<{ name: string; value: number; color: string }>;
  className?: string;
}) {
  const total = segments.reduce((sum, segment) => sum + Math.max(0, segment.value), 0);
  if (total <= 0) {
    return <div className={cn('h-2 w-full rounded-full bg-white/[0.06]', className)} />;
  }
  return (
    <div className={cn('flex h-2 w-full overflow-hidden rounded-full bg-white/[0.06]', className)}>
      {segments.filter((segment) => segment.value > 0).map((segment) => (
        <div
          key={segment.name}
          style={{ width: `${(segment.value / total) * 100}%`, backgroundColor: segment.color }}
          title={`${segment.name}: ${segment.value.toFixed(1)}%`}
        />
      ))}
    </div>
  );
}

export function WeightBar({
  value,
  color,
  className,
}: {
  value: number;
  color: string;
  className?: string;
}) {
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]', className)}>
      <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: color }} />
    </div>
  );
}

export function ComponentMeter({
  label,
  score,
  detail,
  available,
  stale,
}: {
  label: string;
  score: number | null;
  detail?: string;
  available: boolean;
  stale?: boolean;
}) {
  const position = score == null ? 50 : ((Math.max(-1, Math.min(1, score)) + 1) / 2) * 100;
  return (
    <div className="min-w-0" title={detail}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[10px] text-muted-foreground/80">{label}</span>
        <span className={cn('shrink-0 text-[10px] tabular-nums', !available || stale ? 'text-muted-foreground/50' : 'text-foreground/80')}>
          {score == null ? '—' : score.toFixed(2)}
        </span>
      </div>
      <div className="relative mt-1.5 h-1.5 w-full rounded-full bg-gradient-to-r from-rose-500/60 via-white/40 to-emerald-400/60">
        <div
          className={cn('absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/40 bg-foreground shadow', (!available || stale) && 'opacity-40')}
          style={{ left: `${position}%` }}
        />
      </div>
    </div>
  );
}

export function SectorDonut({
  slices,
  className,
}: {
  slices: Array<{ name: string; weightPct: number }>;
  className?: string;
}) {
  const size = 120;
  const thickness = 14;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const total = slices.reduce((sum, slice) => sum + Math.max(0, slice.weightPct), 0);
  if (total <= 0) {
    return <div className={cn('flex h-[120px] w-[120px] items-center justify-center rounded-full border border-white/10 text-[10px] text-muted-foreground/60', className)}>UNAVAILABLE</div>;
  }
  return (
    <div className={cn('relative inline-flex shrink-0 items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={thickness} />
        {slices.map((slice, index) => {
          const share = Math.max(0, slice.weightPct) / total;
          const length = share * circumference;
          const circle = (
            <circle
              key={slice.name}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={SECTOR_COLORS[index % SECTOR_COLORS.length]}
              strokeWidth={thickness}
              strokeDasharray={`${Math.max(0, length - 1.5)} ${circumference}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              strokeLinecap="butt"
            />
          );
          offset += length;
          return circle;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-semibold tabular-nums text-foreground">{slices.length}</span>
        <span className="text-[8px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">groups</span>
      </div>
    </div>
  );
}

export function UnavailableNote({
  children,
  action,
  className,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-start gap-2 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5', className)}>
      <Info size={13} className="mt-0.5 shrink-0 text-muted-foreground/70" />
      <div className="min-w-0 flex-1 text-[11px] leading-relaxed text-muted-foreground">{children}</div>
      {action}
    </div>
  );
}

export function SymbolChip({
  symbol,
  tone,
  onClick,
}: {
  symbol: string;
  tone?: Tone;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'rounded-md border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-foreground/80 transition-colors',
        onClick && 'cursor-pointer hover:border-white/25 hover:text-foreground',
        tone && TONE_TEXT[tone],
      )}
    >
      {symbol}
    </button>
  );
}
