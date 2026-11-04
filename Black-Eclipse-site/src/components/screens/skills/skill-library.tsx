"use client";

// ── Skills Library — search, filters, cards ─────────────────────────────────
// The landing view of the Skill Control Room. Discovery metadata only; the
// detailed instructions load on the Skill Detail view (progressive disclosure).

import { useMemo, useState } from "react";
import {
  AlertCircle, Blocks, FolderGit2, Plus, RefreshCcw, Search, ShieldAlert, Sparkles, User,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { SkillSummary } from "@/lib/harness/skills-types";
import { EvalBadge, LoadingState, RiskBadge, StatusBadge } from "./skill-ui";
import { IconBadge } from "@/components/layout/page-header";

const CATEGORIES = ["all", "research", "quality", "finance", "system"] as const;
const STATUSES = ["all", "enabled", "validated", "testing", "draft", "disabled", "deprecated", "archived", "rejected"] as const;
const RISKS = ["all", "low", "medium", "high", "critical"] as const;

const CATEGORY_LABEL: Record<string, string> = {
  all: "All",
  research: "Research",
  quality: "Quality",
  finance: "Finance",
  system: "System",
};

export function SkillLibrary({
  skills,
  loading,
  error,
  loadErrors,
  duplicates,
  projectNotices = [],
  isOperator = false,
  onOpen,
  onRefresh,
  onAdd,
}: {
  skills: SkillSummary[];
  loading: boolean;
  error: string | null;
  loadErrors: string[];
  duplicates: string[];
  projectNotices?: string[];
  isOperator?: boolean;
  onOpen: (id: string) => void;
  onRefresh: () => void;
  onAdd: () => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [risk, setRisk] = useState<string>("all");

  const filtered = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return skills.filter((skill) => {
      if (category !== "all" && skill.category !== category) return false;
      if (status !== "all" && skill.status !== status) return false;
      if (risk !== "all" && skill.riskLevel !== risk) return false;
      if (terms.length) {
        const hay = `${skill.id} ${skill.name} ${skill.description} ${skill.tags.join(" ")}`.toLowerCase();
        if (!terms.every((term) => hay.includes(term))) return false;
      }
      return true;
    });
  }, [skills, query, category, status, risk]);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <IconBadge icon={Blocks} size="sm" />
          <div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Skills Library</h2>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-lg">
              Versioned financial procedures the agent executes through the same runtime as a chat turn.
              Enable, evaluate and review them here — or write your own.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={onRefresh} disabled={loading}>
            <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" className="cursor-pointer rounded-xl" onClick={onAdd} disabled={!isOperator} title={isOperator ? undefined : "Requires operator authorization"}>
            <Plus size={13} className="mr-1" /> Add skill
          </Button>
        </div>
      </div>

      {(loadErrors.length > 0 || duplicates.length > 0) && (
        <div className="mb-5 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-[11px] text-amber-200">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldAlert size={13} /> Registry warnings
          </div>
          <ul className="mt-1 list-disc list-inside space-y-0.5">
            {loadErrors.map((message) => <li key={message}>{message}</li>)}
            {duplicates.map((dup) => <li key={dup}>Duplicate skill id: {dup}</li>)}
          </ul>
        </div>
      )}

      {projectNotices.length > 0 && (
        <div className="mb-5 rounded-xl border border-sky-400/30 bg-sky-400/10 p-3 text-[11px] text-sky-200">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldAlert size={13} /> Project skills not loaded
          </div>
          <ul className="mt-1 list-disc list-inside space-y-0.5">
            {projectNotices.map((message) => <li key={message}>{message}</li>)}
          </ul>
          <p className="mt-1 text-sky-200/70">Trust the project from the Project Skills tab to enable them.</p>
        </div>
      )}

      <div className="mb-5 flex flex-col gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search skills by name, tag or capability…"
            className="pl-9 rounded-xl bg-background/60"
          />
        </div>
        <div className="flex flex-wrap gap-4">
          <FilterRow label="Category" options={CATEGORIES} value={category} onChange={setCategory} labels={CATEGORY_LABEL} />
          <FilterRow label="Status" options={STATUSES} value={status} onChange={setStatus} />
          <FilterRow label="Risk" options={RISKS} value={risk} onChange={setRisk} />
        </div>
      </div>

      {loading ? (
        <LoadingGrid />
      ) : error ? (
        <Empty icon={AlertCircle} title="Could not load skills" hint={error} />
      ) : filtered.length === 0 ? (
        <Empty
          icon={Search}
          title={skills.length === 0 ? "No skills installed" : "No skills match your filters"}
          hint={skills.length === 0 ? "The runtime library is empty or the Python runtime is not ready." : "Adjust the search or filters."}
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {filtered.map((skill) => (
            <button
              key={skill.id}
              onClick={() => onOpen(skill.id)}
              className="group text-left rounded-2xl border border-white/10 dark:border-white/5 glass-card p-4 transition-all hover:border-primary/30 cursor-pointer"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{skill.name}</p>
                  <p className="font-mono text-[10px] text-muted-foreground truncate">{skill.id}</p>
                </div>
                <StatusBadge status={skill.status} />
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed line-clamp-3">{skill.description}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="rounded-md border border-border/30 bg-accent/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground">
                  v{skill.latestVersion ?? skill.version}
                </span>
                {skill.provenance === "project" ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-sky-400/30 bg-sky-400/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-sky-300">
                    <FolderGit2 size={9} /> Project
                  </span>
                ) : skill.provenance === "profile" || skill.origin === "author" ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-300">
                    <User size={9} /> Yours
                  </span>
                ) : skill.provenance === "generated" || skill.origin === "learning" ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-300">
                    <Sparkles size={9} /> Generated
                  </span>
                ) : null}
                <RiskBadge risk={skill.riskLevel} />
                <EvalBadge status={skill.evaluationStatus} />
              </div>
              {skill.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {skill.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary/90">#{tag}</span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterRow<T extends string>({
  label, options, value, onChange, labels,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
  labels?: Record<string, string>;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1">
        {options.map((option) => (
          <button
            key={option}
            onClick={() => onChange(option)}
            className={cn(
              "rounded-lg px-2 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer",
              value === option ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            {labels?.[option] ?? option}
          </button>
        ))}
      </div>
    </div>
  );
}

function LoadingGrid() {
  // A labelled, centred spinner, not empty card shells: empty pulsing boxes
  // read as a broken/blank page while the (slow) Python runtime answers.
  return <LoadingState label="Loading the skill library…" hint="First load starts the Python runtime, which can take a few seconds." />;
}

function Empty({ icon: Icon, title, hint }: { icon: React.ElementType; title: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-border/20 glass-card-subtle p-10 text-center">
      <Icon size={26} className="mx-auto text-muted-foreground/60" />
      <p className="mt-3 text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
