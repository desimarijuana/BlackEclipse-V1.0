'use client';

import { cn } from "@/lib/utils";

/**
 * BlackEclipse skeleton primitives.
 * Very subtle, minimal loading treatment — near-black surfaces with
 * only a whisper of grey. No borders, no accent color.
 */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-zinc-900/60 dark:bg-white/[0.04]", className)} />;
}

/** A block / card-sized placeholder surface. */
export function SkeletonBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  return (
    <div className={cn("animate-pulse rounded-2xl border border-zinc-200/60 dark:border-white/[0.06] bg-zinc-900/30 dark:bg-white/[0.02]", className)}>
      {children}
    </div>
  );
}

/** Page header placeholder (title + subtitle + trailing control). */
export function SkeletonHeader({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6", className)}>
      <div className="space-y-2.5">
        <Skeleton className="h-3.5 w-28" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Skeleton className="h-10 w-40" />
    </div>
  );
}

/** Metric / KPI card placeholder. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <SkeletonBlock className={cn("p-5 space-y-3", className)}>
      <div className="flex items-center justify-between">
        <Skeleton className="h-3.5 w-24" />
        <Skeleton className="h-3 w-6" />
      </div>
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-3 w-40" />
    </SkeletonBlock>
  );
}

/** Compact card for narrow grids (e.g. index tickers). */
export function SkeletonIndexCard({ className }: { className?: string }) {
  return (
    <SkeletonBlock className={cn("h-20 p-3.5 flex flex-col justify-between", className)}>
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-8" />
      </div>
      <Skeleton className="h-4 w-16" />
    </SkeletonBlock>
  );
}

/** Grid of metric cards. */
export function SkeletonCardGrid({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

/** Table placeholder with header bar + rows. */
export function SkeletonTable({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-8 w-28" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 pb-3 last:pb-0">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/4" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  );
}

/** Simple centered state (e.g. chart / empty panel). */
export function SkeletonPanel({ className }: { className?: string }) {
  return <SkeletonBlock className={cn("h-64 w-full", className)} />;
}
