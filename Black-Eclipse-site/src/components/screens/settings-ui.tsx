"use client";

// ── Shared settings building blocks ─────────────────────────────────────────
// Small presentational primitives reused across every Settings surface: the
// glass panel shell, a labelled field, a switch, and the section/sub-section
// headers. Kept in one module so the individual panels (General, Customization,
// Background, Settings shell) stop re-declaring identical helpers and cannot
// drift apart. Purely presentational — no state, no stores.

import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { IconBadge } from "@/components/layout/page-header";

/** Frosted-glass panel shell — the standard Settings card. */
export function Panel({
  className,
  children,
  ...rest
}: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

/** A labelled control with an optional hint line beneath it. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>}
    </div>
  );
}

/** Compact switch control (not the shadcn Switch — matches the Settings look). */
export function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors",
        disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70",
        )}
      />
    </button>
  );
}

/** Large icon + title header that leads a settings section body. */
export function SectionHeader({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3">
        <IconBadge icon={Icon} size="sm" />
        <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">{title}</h2>
      </div>
      <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">{description}</p>
    </div>
  );
}

/** A labelled sub-section within a settings page, for consistent organization. */
export function SubSection({
  icon: Icon,
  title,
  description,
  children,
  className,
}: {
  icon?: React.ElementType;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex items-center gap-2">
        {Icon && <Icon size={13} className="text-primary shrink-0" />}
        <h3 className="text-xs font-semibold tracking-tight text-foreground">{title}</h3>
      </div>
      {description && <p className="text-[10px] text-muted-foreground leading-relaxed -mt-1">{description}</p>}
      {children}
    </section>
  );
}
