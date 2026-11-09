"use client";

// ── Skills Library — search, filters, cards ─────────────────────────────────
// The landing view of the Skill Control Room. Discovery metadata only; the
// detailed instructions load on the Skill Detail view (progressive disclosure).

import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpDown, Blocks, FolderGit2, Plus, RefreshCcw, Search, ShieldAlert, Sparkles, User,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import type { SkillSummary } from "@/lib/harness/skills-types";
import { libraryHref, parseLibraryView, type LibrarySort } from "@/lib/skills/library-view";
import { EmptyState, ErrorState, EvalBadge, LoadingState, PanelHeader, RiskBadge, StatusBadge } from "./skill-ui";

const RISKS = ["all", "low", "medium", "high", "critical"] as const;
const SORTS: { id: LibrarySort; label: string }[] = [
  { id: "name", label: "Name" },
  { id: "status", label: "Status" },
  { id: "risk", label: "Risk" },
  { id: "updated", label: "Updated" },
];

const CATEGORY_LABEL: Record<string, string> = {
  all: "All",
  research: "Research",
  quality: "Quality",
  finance: "Finance",
  system: "System",
};

const RISK_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

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
  onStartHere,
  onBulkLifecycle,
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
  onStartHere?: () => void;
  onBulkLifecycle?: (ids: string[], action: "enable" | "disable") => Promise<void>;
}) {
  // Hydrate from the URL so a reload / shared link / Cmd-click restores the
  // exact view instead of dropping the user back on an unfiltered grid.
  const initialView = useMemo(
    () => parseLibraryView(typeof window === "undefined" ? "" : window.location.search),
    [],
  );
  const [query, setQuery] = useState(initialView.query);
  const [category, setCategory] = useState<string>(initialView.category);
  const [status, setStatus] = useState<string>(initialView.status);
  const [risk, setRisk] = useState<string>(initialView.risk);
  const [sort, setSort] = useState<LibrarySort>(initialView.sort);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const selectedIds = useMemo(
    () => Array.from(selected).filter((id) => skills.some((skill) => skill.id === id)),
    [selected, skills],
  );

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const runBulk = async (action: "enable" | "disable") => {
    if (!onBulkLifecycle || selectedIds.length === 0) return;
    setBulkBusy(true);
    try {
      await onBulkLifecycle(selectedIds, action);
      setSelected(new Set());
    } finally {
      setBulkBusy(false);
    }
  };

  // Keep the URL in step with the view. `replaceState` avoids a history entry
  // per keystroke; the shell preserves this URL while the Skills tab is active.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const href = libraryHref(
      { query, category, status, risk, sort },
      {},
      window.location.pathname,
    );
    if (`${window.location.pathname}${window.location.search}` !== href) {
      window.history.replaceState(null, "", href);
    }
  }, [query, category, status, risk, sort]);

  // Derive the filter chips from the registry itself, so a status the runtime
  // adds (canary, review, superseded…) can never become unreachable by filter.
  const categories = useMemo(
    () => ["all", ...Array.from(new Set(skills.map((s) => s.category))).sort()],
    [skills],
  );
  const statuses = useMemo(
    () => ["all", ...Array.from(new Set(skills.map((s) => s.status))).sort()],
    [skills],
  );

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

  const sorted = useMemo(() => {
    const list = [...filtered];
    if (sort === "status") {
      list.sort((a, b) => a.status.localeCompare(b.status) || a.name.localeCompare(b.name));
    } else if (sort === "risk") {
      list.sort(
        (a, b) =>
          (RISK_ORDER[a.riskLevel] ?? 9) - (RISK_ORDER[b.riskLevel] ?? 9) ||
          a.name.localeCompare(b.name),
      );
    } else if (sort === "updated") {
      list.sort(
        (a, b) =>
          (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "") ||
          a.name.localeCompare(b.name),
      );
    } else {
      list.sort((a, b) => a.name.localeCompare(b.name));
    }
    return list;
  }, [filtered, sort]);

  const pagination = usePagination(sorted, 25);

  return (
    <div className="animate-fade-in-up">
      <PanelHeader
        icon={Blocks}
        title="Skills Library"
        description="Versioned financial procedures the agent executes through the same runtime as a chat turn. Enable, evaluate and review them here — or write your own."
        actions={
          <>
            <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={onRefresh} disabled={loading}>
              <RefreshCcw className={cn("w-3.5 h-3.5 mr-1", loading && "animate-spin")} /> Refresh
            </Button>
            <Button size="sm" className="cursor-pointer rounded-xl" onClick={onAdd} disabled={!isOperator}>
              <Plus size={13} className="mr-1" /> Add skill
            </Button>
          </>
        }
      />

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
            placeholder="Search skills by name, id, tag or description…"
            aria-label="Search skills"
            className="pl-9 rounded-xl bg-background/60"
          />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <FilterRow label="Category" options={categories} value={category} onChange={setCategory} labels={CATEGORY_LABEL} />
          <FilterRow label="Status" options={statuses} value={status} onChange={setStatus} />
          <FilterRow label="Risk" options={RISKS} value={risk} onChange={setRisk} />
          <div className="flex items-center gap-1.5">
            <span className="flex items-center gap-1 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
              <ArrowUpDown size={11} /> Sort
            </span>
            <div className="flex flex-wrap gap-1">
              {SORTS.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setSort(option.id)}
                  aria-pressed={sort === option.id}
                  className={cn(
                    "rounded-lg px-2 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer",
                    sort === option.id
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <LoadingGrid />
      ) : error ? (
        <ErrorState title="Could not load skills" message={error} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Search}
          title={skills.length === 0 ? "No skills installed" : "No skills match your filters"}
          hint={skills.length === 0 ? "The runtime library is empty or the Python runtime is not ready. New here? Start with a short tour of what skills are." : "Adjust the search or filters."}
          action={
            skills.length === 0 && onStartHere ? (
              <Button variant="outline" size="sm" className="mt-3 cursor-pointer rounded-xl" onClick={onStartHere}>
                <Sparkles size={13} className="mr-1" /> Start here
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
        {selectedIds.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/20 bg-primary/5 px-3 py-2">
            <span className="text-[11px] font-semibold text-foreground">
              {selectedIds.length} selected
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="rounded-xl cursor-pointer"
                disabled={bulkBusy || !isOperator || !onBulkLifecycle}
                onClick={() => void runBulk("enable")}
              >
                Enable
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="rounded-xl cursor-pointer text-amber-300"
                disabled={bulkBusy || !isOperator || !onBulkLifecycle}
                onClick={() => void runBulk("disable")}
              >
                Disable
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="rounded-xl cursor-pointer"
                disabled={bulkBusy}
                onClick={() => setSelected(new Set())}
              >
                Clear
              </Button>
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {pagination.pageItems.map((skill) => (
            <div key={skill.id} className="relative">
            <button
              onClick={() => onOpen(skill.id)}
              className="group w-full text-left rounded-2xl border border-white/10 dark:border-white/5 glass-card p-4 pb-10 transition-all hover:border-primary/30 cursor-pointer"
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
            <label
              className="absolute bottom-2.5 right-2.5 z-10 flex h-6 w-6 cursor-pointer items-center justify-center rounded-lg border border-border/40 bg-background/80"
              title={`Select ${skill.name}`}
            >
              <input
                type="checkbox"
                checked={selected.has(skill.id)}
                onChange={() => toggleSelected(skill.id)}
                aria-label={`Select ${skill.name}`}
                className="h-3.5 w-3.5 cursor-pointer accent-[var(--brand)]"
              />
            </label>
            </div>
          ))}
        </div>
        <PaginationFooter pagination={pagination} label="skills" />
        </>
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
            aria-pressed={value === option}
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


