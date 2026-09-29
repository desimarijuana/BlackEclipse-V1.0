"use client";

// ── Eclipse-Memory presentational primitives ────────────────────────────────
// Small, pure UI atoms shared by the Memory Control Room panels. Extracted from
// `eclipse-memory-screen.tsx` so that screen (and future panels) stay navigable.
// No data fetching and no business logic here — presentation only.

import {
  AlertCircle, Brain, Database, Loader2, MessageSquare, Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { MemoryRecord } from "@/lib/harness/eclipse-memory-types";

// ── The three-part mental model (facts / session history / skills) ───────────

export function MemoryModelLegend() {
  const items = [
    { icon: Database, title: "Facts", body: "Small, durable, declarative facts recalled on relevant turns (identity, preferences, conventions, environment). Nothing is stored automatically unless you ask." },
    { icon: MessageSquare, title: "Session History", body: "Past conversations and run traces. Never injected every turn — searched on demand (\"what did we decide last week?\")." },
    { icon: Wrench, title: "Skills", body: "Reusable procedures loaded only when relevant. A proposal stays inert until evaluated and approved by an operator." },
  ];
  return (
    <div className="mb-6 grid gap-2 md:grid-cols-3">
      {items.map((item) => (
        <div key={item.title} className="rounded-2xl border border-white/10 dark:border-white/5 glass-card-subtle p-3">
          <div className="flex items-center gap-2">
            <item.icon size={13} className="text-primary shrink-0" />
            <span className="text-[11px] font-semibold text-foreground">{item.title}</span>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">{item.body}</p>
        </div>
      ))}
    </div>
  );
}

// ── How a memory came to exist (automatic / explicit / imported / external) ──

export type Origin = "automatic" | "explicit" | "imported" | "external" | "suggested";

const ORIGIN_STYLES: Record<Origin, { label: string; className: string }> = {
  automatic: { label: "auto", className: "border-violet-400/25 bg-violet-400/10 text-violet-300" },
  explicit: { label: "explicit", className: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" },
  imported: { label: "imported", className: "border-sky-400/25 bg-sky-400/10 text-sky-300" },
  external: { label: "external", className: "border-amber-400/25 bg-amber-400/10 text-amber-300" },
  suggested: { label: "suggested", className: "border-sky-400/25 bg-sky-400/10 text-sky-300" },
};

/** Classify a memory's origin from its authority/source. Never invents a value. */
export function originOf(memory: Pick<MemoryRecord, "authority" | "source" | "status">): Origin {
  if (memory.status === "proposed") return "suggested";
  const source = (memory.source ?? "").toLowerCase();
  if (source.includes("import")) return "imported";
  if (source.includes("external")) return "external";
  if ((memory.authority ?? "") === "automatic") return "automatic";
  return "explicit";
}

export function OriginBadge({ memory }: { memory: Pick<MemoryRecord, "authority" | "source" | "status"> }) {
  const origin = originOf(memory);
  const style = ORIGIN_STYLES[origin];
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", style.className)}>
      {style.label}
    </span>
  );
}

export function Header({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
        <Brain className="text-primary" size={22} />
      </span>
      <div>
        <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-2xl">{hint}</p>
      </div>
    </div>
  );
}

export function FilterRow({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      {options.map((option) => (
        <button key={option} onClick={() => onChange(option)}
          className={cn("rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer",
            value === option ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")}>
          {option}
        </button>
      ))}
    </div>
  );
}

export function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    preference: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    semantic: "border-violet-400/30 bg-violet-400/10 text-violet-300",
    procedural: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    episodic: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    correction: "border-rose-400/30 bg-rose-400/10 text-rose-300",
    constraint: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  };
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", colors[type] ?? "border-border/40 text-muted-foreground")}>
      {type}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    proposed: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    superseded: "border-border/40 text-muted-foreground",
    archived: "border-border/40 text-muted-foreground",
    rejected: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  };
  return <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", colors[status] ?? "border-border/40 text-muted-foreground")}>{status}</span>;
}

export function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1 border-b border-border/10 last:border-0">
      <dt className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-[11px] text-foreground text-right break-words min-w-0">{value}</dd>
    </div>
  );
}

export function Section({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 glass-card p-4">
      <div className="flex items-center gap-2 mb-3"><Icon size={13} className="text-primary" /><span className="text-[11px] font-semibold text-foreground">{title}</span></div>
      {children}
    </div>
  );
}

export function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] text-muted-foreground">{children}</p>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] w-full flex-col items-center justify-center gap-2 text-muted-foreground">
      <Loader2 className="animate-spin" size={18} />
      <p className="text-[11px]">{label}</p>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center">
      <AlertCircle size={22} className="mx-auto text-rose-400" />
      <p className="mt-2 text-sm text-foreground">{message}</p>
    </div>
  );
}

export function EmptyBox({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-border/20 glass-card-subtle p-10 text-center">
      <Database size={24} className="mx-auto text-muted-foreground/60" />
      <p className="mt-3 text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
