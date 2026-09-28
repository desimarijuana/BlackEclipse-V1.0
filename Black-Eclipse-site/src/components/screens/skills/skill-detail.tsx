"use client";

// ── Skill Detail — instructions, contracts, history, actions ────────────────
// Progressive disclosure: this is where the full SKILL.md instructions are
// fetched and shown (the library only loaded metadata). Actions respect the
// server-side operator check; the UI hides/disables what the server would deny.

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, BookOpen, CheckCircle2, ChevronDown, ChevronRight,
  FlaskConical, GitBranch, History, Info, LineChart, Loader2, Pencil, Play, Power, ScrollText, ShieldCheck,
  Trash2, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SkillDetail as SkillDetailType, SkillVersionHistoryEntry } from "@/lib/harness/skills-types";
import { getSkillVersionHistory, skillVersionAction } from "@/lib/harness/skills-browser";
import { EvalBadge, formatDuration, formatWhen, MetaRow, Panel, RiskBadge, SectionTitle, StatusBadge } from "./skill-ui";
import { SkillQualityPanel } from "./skill-quality";

function Collapsible({
  title, icon: Icon, defaultOpen = false, children, badge,
}: {
  title: string;
  icon: React.ElementType;
  defaultOpen?: boolean;
  children: React.ReactNode;
  badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Panel>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 cursor-pointer hover:bg-accent/20 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Icon size={14} className="text-primary" />
          <span className="text-xs font-semibold text-foreground">{title}</span>
          {badge}
        </span>
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
      </button>
      {open && <div className="px-4 pb-4 pt-1 border-t border-border/10">{children}</div>}
    </Panel>
  );
}

export function SkillDetailPanel({
  skill,
  loading,
  error,
  isOperator,
  onBack,
  onRun,
  onEvaluate,
  onLifecycle,
  onEdit,
  onDelete,
}: {
  skill: SkillDetailType | null;
  loading: boolean;
  error: string | null;
  isOperator: boolean;
  onBack: () => void;
  onRun: (skillId: string, input: Record<string, unknown>, mode: string) => void;
  onEvaluate: (skillId: string, version: string) => void;
  onLifecycle: (skillId: string, action: "enable" | "disable" | "deprecate" | "rollback", version?: string) => void;
  onEdit?: (skill: SkillDetailType) => void;
  onDelete?: (skillId: string) => void;
}) {
  const [runInput, setRunInput] = useState("{}");
  const [runMode, setRunMode] = useState("interactive");
  const [inputError, setInputError] = useState<string | null>(null);

  useEffect(() => {
    setRunInput("{}");
    setInputError(null);
  }, [skill?.id]);

  const inputFields = useMemo(() => {
    const props = (skill?.inputSchema?.properties ?? {}) as Record<string, { description?: string; type?: string }>;
    return Object.entries(props);
  }, [skill]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="animate-spin mr-2" size={16} /> Loading skill…
      </div>
    );
  }
  if (error || !skill) {
    return (
      <div>
        <BackButton onBack={onBack} />
        <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center">
          <AlertTriangle size={24} className="mx-auto text-rose-400" />
          <p className="mt-2 text-sm font-semibold text-foreground">{error ?? "Skill not found"}</p>
        </div>
      </div>
    );
  }

  const canEnable = skill.status !== "enabled" && skill.status !== "deprecated";
  const canDisable = skill.status === "enabled";

  const handleRun = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = runInput.trim() ? JSON.parse(runInput) : {};
    } catch {
      setInputError("Input must be valid JSON.");
      return;
    }
    setInputError(null);
    onRun(skill.id, parsed, runMode);
  };

  return (
    <div className="animate-fade-in-up">
      <BackButton onBack={onBack} />

      <div className="mb-5 flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">{skill.name}</h2>
            <StatusBadge status={skill.status} />
            <RiskBadge risk={skill.riskLevel} />
            <EvalBadge status={skill.evaluationStatus} />
          </div>
          <p className="font-mono text-[11px] text-muted-foreground mt-1">
            {skill.id} · v{skill.latestVersion ?? skill.version} · {skill.category}
          </p>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-2xl">{skill.description}</p>
        </div>
      </div>

      {/* Actions */}
      <Panel className="mb-5">
        <div className="p-4">
          <SectionTitle icon={Play} title="Actions" hint="All lifecycle actions are enforced server-side; without operator authorization the runtime denies them." />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              className="rounded-xl cursor-pointer"
              onClick={handleRun}
              disabled={skill.storedStatus !== "enabled" && skill.storedStatus !== "validated" && skill.storedStatus !== "testing"}
            >
              <Play size={13} className="mr-1" /> Run
            </Button>
            <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => onEvaluate(skill.id, skill.latestVersion ?? skill.version)}>
              <FlaskConical size={13} className="mr-1" /> Evaluate
            </Button>
            {canEnable && (
              <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => onLifecycle(skill.id, "enable")} disabled={!isOperator}>
                <Power size={13} className="mr-1" /> Enable
              </Button>
            )}
            {canDisable && (
              <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => onLifecycle(skill.id, "disable")} disabled={!isOperator}>
                <Power size={13} className="mr-1" /> Disable
              </Button>
            )}
            <Button variant="outline" size="sm" className="rounded-xl cursor-pointer text-rose-300" onClick={() => onLifecycle(skill.id, "deprecate")} disabled={!isOperator || skill.status === "deprecated"}>
              <XCircle size={13} className="mr-1" /> Deprecate
            </Button>
            {skill.origin === "author" && onEdit && (
              <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => onEdit(skill)} disabled={!isOperator}>
                <Pencil size={13} className="mr-1" /> Edit
              </Button>
            )}
            {skill.origin === "author" && onDelete && (
              <Button
                variant="outline" size="sm" className="rounded-xl cursor-pointer text-rose-300"
                onClick={() => { if (window.confirm(`Delete ${skill.name}? This cannot be undone.`)) onDelete(skill.id); }}
                disabled={!isOperator}
              >
                <Trash2 size={13} className="mr-1" /> Delete
              </Button>
            )}
          </div>
          {!isOperator && (
            <p className="mt-2 flex items-center gap-1 text-[10px] text-amber-300/90">
              <ShieldCheck size={11} /> Read-only operator session — enable/disable/deprecate require the runtime secret.
            </p>
          )}

          <div className="mt-4">
            <label className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Run input (JSON)</label>
            <div className="mt-1 flex gap-2 items-start">
              <textarea
                value={runInput}
                onChange={(e) => setRunInput(e.target.value)}
                rows={3}
                spellCheck={false}
                className="flex-1 rounded-xl border border-border/30 bg-background/60 px-3 py-2 font-mono text-[11px] text-foreground outline-none focus:border-primary/40"
                placeholder='{"symbol": "AAPL", "market": "US"}'
              />
              <select
                value={runMode}
                onChange={(e) => setRunMode(e.target.value)}
                className="rounded-xl border border-border/30 bg-background/60 px-2 py-2 text-[11px] text-foreground outline-none focus:border-primary/40"
              >
                {["interactive", "workflow", "agent", "scheduled", "evaluation"].map((mode) => (
                  <option key={mode} value={mode}>{mode}</option>
                ))}
              </select>
            </div>
            {inputError && <p className="mt-1 text-[10px] text-rose-300">{inputError}</p>}
            {inputFields.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {inputFields.map(([name, spec]) => (
                  <span key={name} className="rounded-md border border-border/30 bg-accent/30 px-1.5 py-0.5 text-[9px] text-muted-foreground">
                    <span className="text-foreground">{name}</span>{spec.type ? `: ${spec.type}` : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </Panel>

      {/* Validation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
        <Collapsible title="Validation" icon={CheckCircle2} defaultOpen badge={
          <span className={cn("text-[10px] font-bold", skill.validation.ok ? "text-emerald-300" : "text-rose-300")}>
            {skill.validation.ok ? "passed" : "failed"}
          </span>
        }>
          <ul className="space-y-1.5">
            {skill.validation.checks.map((check) => (
              <li key={check.check} className="flex items-start gap-2 text-[11px]">
                {check.ok ? <CheckCircle2 size={12} className="text-emerald-400 mt-0.5 shrink-0" /> : <XCircle size={12} className="text-rose-400 mt-0.5 shrink-0" />}
                <span className="min-w-0">
                  <span className="font-semibold text-foreground">{check.check}</span>
                  <span className="text-muted-foreground"> — {check.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </Collapsible>

        <Collapsible title="Contracts" icon={ScrollText} defaultOpen>
          <MetaRow label="Required tools">{skill.requiredTools.length ? skill.requiredTools.join(", ") : "none"}</MetaRow>
          {skill.dependencyGraph && skill.dependencyGraph.edges.length > 0 ? (
            <div className="py-1.5 border-b border-border/10">
              <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-1">Dependencies (resolved)</p>
              <ul className="space-y-0.5">
                {skill.dependencyGraph.edges.map((edge, i) => (
                  <li key={`${edge.from}-${edge.to}-${i}`} className="flex items-center gap-2 text-[11px]">
                    <span className={cn(
                      "rounded-full border px-1.5 py-0.5 text-[9px] font-bold uppercase",
                      edge.status === "ok" ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                        : edge.status === "optional" ? "border-border/40 text-muted-foreground"
                        : "border-rose-400/30 bg-rose-400/10 text-rose-300"
                    )}>{edge.status}</span>
                    <span className="text-foreground">{edge.to}</span>
                    {edge.resolvedVersion && <span className="text-muted-foreground">v{edge.resolvedVersion}</span>}
                    {edge.constraint && <span className="text-muted-foreground">({edge.constraint})</span>}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <MetaRow label="Required skills">{skill.requiredSkills.length ? skill.requiredSkills.map((d) => d.skillId).join(", ") : "none"}</MetaRow>
          )}
          <MetaRow label="Permissions">{skill.permissions.length ? skill.permissions.join(", ") : "none"}</MetaRow>
          <MetaRow label="Limits">{`${skill.limits.maxSteps} steps · ${formatDuration(skill.limits.timeoutMs)} · ${skill.limits.maxToolCalls} tool calls`}</MetaRow>
          <MetaRow label="Origin">{skill.origin}{skill.sourceRunId ? ` · ${skill.sourceRunId}` : ""}</MetaRow>
          <MetaRow label="Compat runtime">{skill.compatibleRuntime}</MetaRow>
          <MetaRow label="Author">{skill.author}</MetaRow>
          {skill.deprecation && <MetaRow label="Deprecation">{skill.deprecation.reason}</MetaRow>}
        </Collapsible>
      </div>

      <Collapsible title="Quality over time" icon={LineChart}>
        <SkillQualityPanel skillId={skill.id} version={skill.latestVersion ?? skill.version} />
      </Collapsible>

      {/* Instructions */}
      <Collapsible title="Instructions (SKILL.md)" icon={BookOpen}>
        {skill.instructions ? (
          <pre className="max-h-[420px] overflow-auto rounded-xl border border-border/20 bg-background/40 p-3 text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap font-mono">
            {skill.instructions}
          </pre>
        ) : (
          <p className="text-[11px] text-muted-foreground flex items-center gap-1"><Info size={11} /> This skill is manifest-only (no prose procedure).</p>
        )}
      </Collapsible>

      {/* Schemas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 my-3">
        <Collapsible title="Input schema" icon={Info}>
          <SchemaView schema={skill.inputSchema} />
        </Collapsible>
        <Collapsible title="Output schema" icon={Info}>
          {skill.outputSchema ? <SchemaView schema={skill.outputSchema} /> : <p className="text-[11px] text-muted-foreground">No output schema declared.</p>}
        </Collapsible>
      </div>

      {/* History */}
      <Collapsible title={`Version history (${skill.versions.length})`} icon={History} defaultOpen>
        <HistoryList versions={skill.versions} onRollback={(version) => onLifecycle(skill.id, "rollback", version)} isOperator={isOperator} />
      </Collapsible>
      <div className="mt-3">
        <Collapsible title="Patch versions (self-improvement)" icon={GitBranch}>
          <PatchVersionPanel skillId={skill.id} isOperator={isOperator} />
        </Collapsible>
      </div>
      <div className="mt-3">
        <Collapsible title={`Evaluation history (${skill.evaluations.length})`} icon={FlaskConical}>
          <EvaluationsList evaluations={skill.evaluations} />
        </Collapsible>
      </div>
      <div className="mt-3">
        <Collapsible title={`Execution history (${skill.executions.length})`} icon={Play}>
          <ExecutionsList executions={skill.executions} />
        </Collapsible>
      </div>
      <div className="mt-3">
        <Collapsible title={`Review history (${skill.reviews.length})`} icon={ShieldCheck}>
          <ReviewsList reviews={skill.reviews} />
        </Collapsible>
      </div>
    </div>
  );
}

const PATCH_ACTIONS = [
  { action: "evaluate" as const, label: "Evaluate" },
  { action: "activate" as const, label: "Activate" },
  { action: "promote" as const, label: "Promote" },
  { action: "auto-rollback-check" as const, label: "Rollback check" },
];

function PatchVersionPanel({ skillId, isOperator }: { skillId: string; isOperator: boolean }) {
  const [versions, setVersions] = useState<SkillVersionHistoryEntry[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getSkillVersionHistory(skillId)
      .then((data) => { if (active) setVersions(data.versions ?? []); })
      .catch(() => { if (active) setVersions([]); });
    return () => { active = false; };
  }, [skillId]);

  const run = async (version: string, action: typeof PATCH_ACTIONS[number]["action"]) => {
    setBusy(`${version}:${action}`);
    setMessage(null);
    try {
      const result = await skillVersionAction(skillId, version, action);
      setMessage(result.success === false ? `Error: ${result.error ?? action} failed` : `${action} OK`);
      const refreshed = await getSkillVersionHistory(skillId);
      setVersions(refreshed.versions ?? []);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "action failed");
    } finally {
      setBusy(null);
    }
  };

  const patched = versions.filter((v) => v.patch || v.canaryState || v.status === "rolled_back");
  if (!patched.length) {
    return (
      <p className="text-[11px] text-muted-foreground">
        No self-improvement patch versions. Background reviews may propose one after a failed skill run.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {message && <p className="text-[11px] text-foreground">{message}</p>}
      {patched.map((v) => {
        const eligibleActions = v.status === "canary"
          ? PATCH_ACTIONS.filter((a) => a.action === "promote" || a.action === "auto-rollback-check")
          : v.status === "rolled_back" || v.status === "active" || v.status === "enabled"
            ? []
            : PATCH_ACTIONS;
        return (
        <div key={v.version} className="rounded-xl border border-border/20 glass-card-subtle p-3">
          <div className="flex items-center gap-2 flex-wrap text-[11px]">
            <span className="font-mono font-semibold text-foreground">{v.version}</span>
            <StatusBadge status={v.status} />
            <EvalBadge status={v.evaluationStatus ?? "not_evaluated"} />
            {v.isActive && <span className="rounded-full border border-emerald-400/40 px-2 py-0.5 text-[9px] uppercase tracking-wide text-emerald-300">active</span>}
            {v.canaryState && <span className="rounded-full border border-cyan-400/40 px-2 py-0.5 text-[9px] uppercase tracking-wide text-cyan-300">canary: {v.canaryState}</span>}
            {v.baseVersion && <span className="text-muted-foreground">from {v.baseVersion}</span>}
            {v.patchAuthor && <span className="text-muted-foreground">author: {v.patchAuthor}</span>}
            {v.activatedAt && <span className="text-emerald-300">activated {formatWhen(v.activatedAt)}</span>}
            {v.rolledBackAt && <span className="text-rose-300">rolled back {formatWhen(v.rolledBackAt)}</span>}
          </div>
          {v.patchSummary && <p className="mt-1 text-[11px] text-muted-foreground">{v.patchSummary}</p>}
          {v.patch?.operations?.length ? (
            <div className="mt-2 rounded-lg border border-border/20 bg-background/30 p-2 font-mono text-[10px]">
              {v.patch.operations.map((op, i) => (
                <p key={i} className={cn(op.op === "add" ? "text-emerald-300" : op.op === "remove" ? "text-rose-300" : "text-sky-300")}>
                  {op.op === "add" ? "+ " : op.op === "remove" ? "- " : "~ "}{op.path}
                  {op.value !== undefined ? ` = ${JSON.stringify(op.value)}` : ""}
                </p>
              ))}
            </div>
          ) : null}
          {(v.patch?.evidenceRuns?.length || v.patch?.regressionCases?.length) ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {(v.patch?.evidenceRuns ?? []).map((run) => (
                <span key={run} className="rounded-md border border-border/30 bg-accent/20 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">evidence {run.slice(0, 12)}</span>
              ))}
              {(v.patch?.regressionCases ?? []).map((rc) => (
                <span key={rc} className="rounded-md border border-border/30 bg-accent/20 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">regression {rc.slice(0, 18)}</span>
              ))}
            </div>
          ) : null}
          {isOperator && eligibleActions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {eligibleActions.map((a) => (
                <button
                  key={a.action}
                  onClick={() => run(v.version, a.action)}
                  disabled={busy !== null}
                  className="rounded-lg border border-border/30 px-2 py-0.5 text-[10px] hover:bg-accent/30 disabled:opacity-40 cursor-pointer disabled:cursor-default"
                >
                  {busy === `${v.version}:${a.action}` ? "…" : a.label}
                </button>
              ))}
            </div>
          )}
        </div>
        );
      })}
    </div>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button onClick={onBack} className="mb-4 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">
      <ArrowLeft size={13} /> Back to library
    </button>
  );
}

function SchemaView({ schema }: { schema: Record<string, unknown> }) {
  const props = (schema.properties ?? {}) as Record<string, { type?: string; description?: string }>;
  const required = (schema.required as string[]) ?? [];
  const entries = Object.entries(props);
  if (!entries.length) return <p className="text-[11px] text-muted-foreground">No fields declared.</p>;
  return (
    <ul className="space-y-1">
      {entries.map(([name, spec]) => (
        <li key={name} className="flex items-start gap-2 text-[11px]">
          <span className="font-mono text-foreground shrink-0">{name}{required.includes(name) ? "*" : ""}</span>
          <span className="rounded-md bg-accent/40 px-1.5 py-0.5 text-[9px] text-muted-foreground">{spec.type ?? "any"}</span>
          {spec.description && <span className="text-muted-foreground min-w-0">{spec.description}</span>}
        </li>
      ))}
    </ul>
  );
}

function HistoryList({
  versions, onRollback, isOperator,
}: {
  versions: SkillDetailType["versions"];
  onRollback: (version: string) => void;
  isOperator: boolean;
}) {
  if (!versions.length) return <p className="text-[11px] text-muted-foreground">No versions recorded.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-[9px] uppercase tracking-widest text-muted-foreground">
            <th className="py-1 pr-3">Version</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Evaluation</th>
            <th className="py-1 pr-3">Hash</th>
            <th className="py-1 pr-3">Created</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {versions.map((version) => (
            <tr key={version.version} className="border-t border-border/10">
              <td className="py-1.5 pr-3 font-mono text-foreground">{version.version}</td>
              <td className="py-1.5 pr-3"><StatusBadge status={version.status} /></td>
              <td className="py-1.5 pr-3"><EvalBadge status={version.evaluationStatus} /></td>
              <td className="py-1.5 pr-3 font-mono text-muted-foreground">{version.contentHash.slice(0, 10)}</td>
              <td className="py-1.5 pr-3 text-muted-foreground">{formatWhen(version.createdAt)}</td>
              <td className="py-1.5 text-right">
                <button
                  onClick={() => onRollback(version.version)}
                  disabled={!isOperator}
                  className="text-[10px] text-primary hover:underline disabled:opacity-40 disabled:no-underline cursor-pointer disabled:cursor-default"
                >
                  Set latest
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvaluationsList({ evaluations }: { evaluations: SkillDetailType["evaluations"] }) {
  if (!evaluations.length) return <p className="text-[11px] text-muted-foreground">Not evaluated yet.</p>;
  return (
    <div className="space-y-2">
      {evaluations.map((evaluation) => (
        <div key={evaluation.id} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-foreground">
              v{evaluation.version} · <EvalBadge status={evaluation.status} />
            </span>
            <span className="text-[10px] text-muted-foreground">{formatWhen(evaluation.createdAt)}</span>
          </div>
          {evaluation.summary && <p className="mt-1 text-[10px] text-muted-foreground">{evaluation.summary}</p>}
          <div className="mt-1.5 flex flex-wrap gap-1">
            {evaluation.dimensions.map((dimension) => (
              <span
                key={dimension.name}
                className={cn(
                  "rounded-md px-1.5 py-0.5 text-[9px] font-semibold",
                  dimension.status === "passed" ? "bg-emerald-400/10 text-emerald-300"
                  : dimension.status === "failed" ? "bg-rose-400/10 text-rose-300"
                  : "bg-amber-400/10 text-amber-300"
                )}
                title={dimension.detail}
              >
                {dimension.name}{dimension.mandatory ? "*" : ""}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ExecutionsList({ executions }: { executions: SkillDetailType["executions"] }) {
  if (!executions.length) return <p className="text-[11px] text-muted-foreground">No executions yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-[9px] uppercase tracking-widest text-muted-foreground">
            <th className="py-1 pr-3">Run</th>
            <th className="py-1 pr-3">Mode</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Duration</th>
            <th className="py-1 pr-3">When</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((execution) => (
            <tr key={execution.id} className="border-t border-border/10">
              <td className="py-1.5 pr-3 font-mono text-muted-foreground truncate max-w-[160px]">{execution.runId}</td>
              <td className="py-1.5 pr-3 text-muted-foreground">{execution.executionMode}</td>
              <td className="py-1.5 pr-3">
                <span className={cn("text-[10px] font-bold", execution.status === "completed" ? "text-emerald-300" : "text-rose-300")}>{execution.status}</span>
              </td>
              <td className="py-1.5 pr-3 text-muted-foreground">{formatDuration(execution.durationMs)}</td>
              <td className="py-1.5 pr-3 text-muted-foreground">{formatWhen(execution.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewsList({ reviews }: { reviews: SkillDetailType["reviews"] }) {
  if (!reviews.length) return <p className="text-[11px] text-muted-foreground">No reviews yet.</p>;
  return (
    <ul className="space-y-1.5">
      {reviews.map((review) => (
        <li key={review.id} className="text-[11px] flex items-start gap-2">
          <span className="font-semibold text-foreground shrink-0">{review.decision}</span>
          <span className="text-muted-foreground min-w-0">v{review.version} · {review.notes || "—"} · {formatWhen(review.createdAt)}</span>
        </li>
      ))}
    </ul>
  );
}
