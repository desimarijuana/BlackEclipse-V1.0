"use client";

// ── Shared UI atoms for the Skill Control Room ──────────────────────────────
// Status/risk badges and small formatting helpers used across all skill panels.
// Uses the existing frosted-glass classes (see the black-eclipse-ui skill) — no
// new visual language.

import { cn } from "@/lib/utils";
import type { EvaluationStatus, SkillRisk, SkillStatus } from "@/lib/harness/skills-types";

const STATUS_STYLES: Record<SkillStatus, string> = {
  draft: "border-slate-400/30 bg-slate-400/10 text-slate-300",
  evaluating: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  testing: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  canary: "border-cyan-400/30 bg-cyan-400/10 text-cyan-300",
  review: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  validated: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  approved: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  enabled: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  disabled: "border-border/40 bg-accent/40 text-muted-foreground",
  deprecated: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  superseded: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  rolled_back: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  rejected: "border-rose-400/30 bg-rose-400/10 text-rose-300",
};

const RISK_STYLES: Record<SkillRisk, string> = {
  low: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
  medium: "border-amber-400/25 bg-amber-400/10 text-amber-300",
  high: "border-orange-400/25 bg-orange-400/10 text-orange-300",
  critical: "border-rose-400/30 bg-rose-400/10 text-rose-300",
};

const EVAL_STYLES: Record<EvaluationStatus, string> = {
  not_evaluated: "border-border/40 bg-accent/40 text-muted-foreground",
  passed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  failed: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  needs_review: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-rose-400/30 bg-rose-400/10 text-rose-300",
};

export function StatusBadge({ status, className }: { status: SkillStatus | string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
        STATUS_STYLES[status as SkillStatus] ?? STATUS_STYLES.disabled,
        className
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export function RiskBadge({ risk, className }: { risk: SkillRisk | string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
        RISK_STYLES[risk as SkillRisk] ?? RISK_STYLES.low,
        className
      )}
    >
      {risk} risk
    </span>
  );
}

export function EvalBadge({ status, className }: { status: EvaluationStatus | string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
        EVAL_STYLES[status as EvaluationStatus] ?? EVAL_STYLES.not_evaluated,
        className
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

/** A small labelled key/value row. */
export function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 border-b border-border/10 last:border-0">
      <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground shrink-0 pt-0.5">{label}</span>
      <span className="text-xs text-foreground text-right break-words min-w-0">{children}</span>
    </div>
  );
}

export function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)}>
      {children}
    </div>
  );
}

export function SectionTitle({ icon: Icon, title, hint }: { icon: React.ElementType; title: string; hint?: string }) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <Icon size={14} className="text-primary shrink-0" />
        <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">{title}</h3>
      </div>
      {hint && <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">{hint}</p>}
    </div>
  );
}
