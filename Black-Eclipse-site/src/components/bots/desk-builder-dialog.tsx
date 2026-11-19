'use client';

// -- Desk builder -------------------------------------------------------------
// Authors the `TeamDefinition` that a desk automation carries (`config.team`).
// The draft → definition mapping lives in `src/lib/bots/desk.ts`; the server's
// `/team/validate` is the only gate that matters, so Save runs it before storing.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Plus, Trash2, Users } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  createAutomation,
  updateAutomation,
} from '@/lib/harness/clients/automation-browser';
import { validateTeam } from '@/lib/harness/clients/team-client';
import type { AutomationView } from '@/lib/harness/clients/automation-browser';
import {
  ROLE_TEMPLATES,
  deskCreateInput,
  deskDraftFromAutomation,
  deskIssues,
  deskToTeam,
  emptyDeskDraft,
  isDesk,
  newDeskStage,
  nextStageKey,
  type DeskDraft,
  type DeskRoleTemplate,
  type DeskStage,
} from '@/lib/bots/desk';

const ROLES = Object.keys(ROLE_TEMPLATES) as DeskRoleTemplate[];
const inputClass =
  'mt-1 w-full rounded-xl border border-border/20 bg-white/5 px-3 py-2 text-sm text-foreground outline-none focus:border-border/40';

function toolsText(tools: string[]): string {
  return tools.join(', ');
}

export function DeskBuilderDialog({
  open,
  onOpenChange,
  desk,
  bots,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Edit this desk, or omit to create a new one. */
  desk?: AutomationView | null;
  /** The operator's bots, for the "when a bot finishes" wake-up. */
  bots: AutomationView[];
  onSaved: (bot: AutomationView) => void;
}) {
  const [draft, setDraft] = useState<DeskDraft>(emptyDeskDraft);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDraft(desk ? deskDraftFromAutomation(desk) : emptyDeskDraft());
    setError(null);
    // Keyed by identity, not by object: a 20 s bot refresh must not wipe edits.
  }, [open, desk?.id]);

  const issues = useMemo(() => deskIssues(draft), [draft]);
  const monitorChoices = useMemo(
    () => bots.filter((bot) => !isDesk(bot) && bot.id !== desk?.id),
    [bots, desk?.id],
  );

  const patchStage = useCallback((index: number, patch: Partial<DeskStage>) => {
    setDraft((current) => ({
      ...current,
      stages: current.stages.map((stage, i) => (i === index ? { ...stage, ...patch } : stage)),
    }));
  }, []);

  const removeStage = useCallback((index: number) => {
    setDraft((current) => {
      const removed = current.stages[index];
      return {
        ...current,
        stages: current.stages
          .filter((_, i) => i !== index)
          .map((stage) => ({
            ...stage,
            dependsOn: stage.dependsOn.filter((dep) => dep !== removed.key),
          })),
      };
    });
  }, []);

  const changeRole = useCallback((index: number, role: DeskRoleTemplate) => {
    setDraft((current) => ({
      ...current,
      stages: current.stages.map((stage, i) => {
        if (i !== index) return stage;
        const template = ROLE_TEMPLATES[role];
        return {
          ...stage,
          role,
          label: template.label,
          objective: template.objective,
          instructions: template.instructions,
          tools: [...template.tools],
          expectedKeys: template.expectedKeys,
        };
      }),
    }));
  }, []);

  const addStage = useCallback(() => {
    setDraft((current) => {
      const role: DeskRoleTemplate = 'research';
      const key = nextStageKey(current, role);
      const previous = current.stages[current.stages.length - 1]?.key;
      return {
        ...current,
        stages: [...current.stages, newDeskStage(role, key, previous ? [previous] : [])],
      };
    });
  }, []);

  const save = useCallback(async () => {
    if (issues.length) {
      setError(issues[0]);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const team = deskToTeam(draft);
      const check = await validateTeam(team);
      if (check.errors.length) {
        setError(check.errors.join('\n'));
        return;
      }
      const input = deskCreateInput(draft);
      const saved = desk
        ? await updateAutomation(desk.id, {
            name: input.name,
            description: input.description,
            action: input.action,
            trigger: input.trigger,
            tags: input.tags,
          })
        : await createAutomation(input);
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the desk.');
    } finally {
      setSaving(false);
    }
  }, [desk, draft, issues, onOpenChange, onSaved]);

  const team = useMemo(() => deskToTeam(draft), [draft]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users size={16} /> {desk ? 'Edit desk' : 'New desk'}
          </DialogTitle>
          <DialogDescription>
            A desk is a pipeline of bots working one question. Stages run as durable tasks and
            hand their memos forward; the last stage proposes, and only a trading bot places an
            order.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-muted-foreground">
              Name
              <input
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                placeholder="e.g. Rates desk"
                className={inputClass}
              />
            </label>
            <label className="block text-xs font-medium text-muted-foreground">
              What it is for
              <input
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                placeholder="One line the Bots list can show"
                className={inputClass}
              />
            </label>
          </div>

          <label className="block text-xs font-medium text-muted-foreground">
            The question every stage works on
            <textarea
              value={draft.objective}
              onChange={(e) => setDraft((d) => ({ ...d, objective: e.target.value }))}
              rows={2}
              placeholder="e.g. Should we add 2% NVDA over the next two quarters?"
              className={inputClass}
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-muted-foreground">
              Run
              <select
                value={draft.trigger.kind}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    trigger: { ...d.trigger, kind: e.target.value as 'manual' | 'interval' | 'event' },
                  }))
                }
                className={inputClass}
              >
                <option value="manual">Only when I run it</option>
                <option value="interval">On an interval</option>
                <option value="event">When a bot finishes</option>
              </select>
            </label>
            {draft.trigger.kind === 'interval' && (
              <label className="block text-xs font-medium text-muted-foreground">
                Every (minutes)
                <input
                  type="number"
                  min={1}
                  value={draft.trigger.intervalMinutes}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      trigger: {
                        ...d.trigger,
                        intervalMinutes: Math.max(1, Number(e.target.value) || 1),
                      },
                    }))
                  }
                  className={inputClass}
                />
              </label>
            )}
            {draft.trigger.kind === 'event' && (
              <label className="block text-xs font-medium text-muted-foreground">
                Wake on
                <select
                  value={draft.trigger.sourceBotId}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      trigger: { ...d.trigger, sourceBotId: e.target.value },
                    }))
                  }
                  className={inputClass}
                >
                  <option value="">Choose a bot…</option>
                  {monitorChoices.map((bot) => (
                    <option key={bot.id} value={bot.id}>
                      {bot.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {draft.trigger.kind === 'event' && (
            <p className="text-[11px] text-muted-foreground">
              The desk starts when that bot completes, and its last result is passed in as an
              unverified lead the first stage must re-check.
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Stages ({draft.stages.length})
            </div>
            <Button size="sm" variant="outline" onClick={addStage}>
              <Plus size={13} /> Add stage
            </Button>
          </div>

          {draft.stages.map((stage, index) => {
            const earlier = draft.stages.slice(0, index);
            return (
              <div key={`${stage.key}-${index}`} className="glass-card-subtle space-y-2 rounded-xl p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-white/[0.06] px-2 py-0.5 text-[11px] text-muted-foreground">
                    {index + 1}
                  </span>
                  <input
                    value={stage.label}
                    onChange={(e) => patchStage(index, { label: e.target.value })}
                    placeholder="Stage name"
                    className="min-w-0 flex-1 rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-sm text-foreground outline-none focus:border-border/40"
                  />
                  <select
                    value={stage.role}
                    onChange={(e) => changeRole(index, e.target.value as DeskRoleTemplate)}
                    className="rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-xs text-foreground outline-none"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_TEMPLATES[role].label}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={stage.review}
                      onChange={(e) => patchStage(index, { review: e.target.checked })}
                    />
                    review
                  </label>
                  <button
                    type="button"
                    aria-label={`Remove ${stage.label || stage.key}`}
                    onClick={() => removeStage(index)}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-white/5 hover:text-foreground"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>

                <textarea
                  value={stage.objective}
                  onChange={(e) => patchStage(index, { objective: e.target.value })}
                  rows={2}
                  aria-label="Stage objective"
                  className="w-full rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-xs text-foreground outline-none focus:border-border/40"
                />
                <textarea
                  value={stage.instructions}
                  onChange={(e) => patchStage(index, { instructions: e.target.value })}
                  rows={3}
                  aria-label="Stage instructions"
                  className="w-full rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-xs text-foreground outline-none focus:border-border/40"
                />

                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block text-[11px] text-muted-foreground">
                    Tools (comma separated)
                    <input
                      value={toolsText(stage.tools)}
                      onChange={(e) =>
                        patchStage(index, {
                          tools: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                        })
                      }
                      className="mt-1 w-full rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-xs text-foreground outline-none focus:border-border/40"
                    />
                  </label>
                  <label className="block text-[11px] text-muted-foreground">
                    Output keys (comma separated)
                    <input
                      value={stage.expectedKeys}
                      onChange={(e) => patchStage(index, { expectedKeys: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-border/20 bg-white/5 px-2 py-1.5 text-xs text-foreground outline-none focus:border-border/40"
                    />
                  </label>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <span>Reads first:</span>
                  {earlier.length === 0 ? (
                    <span className="text-muted-foreground/70">nothing (it starts the desk)</span>
                  ) : (
                    earlier.map((prior) => (
                      <label key={prior.key} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          checked={stage.dependsOn.includes(prior.key)}
                          onChange={(e) =>
                            patchStage(index, {
                              dependsOn: e.target.checked
                                ? [...stage.dependsOn, prior.key]
                                : stage.dependsOn.filter((dep) => dep !== prior.key),
                            })
                          }
                        />
                        {prior.label || prior.key}
                      </label>
                    ))
                  )}
                </div>
              </div>
            );
          })}

          {team && (
            <p className="text-[11px] text-muted-foreground">
              {team.members.length} roles · {team.subtasks.length} stages · strict review. Desks
              propose a trade with order_preview; the operator confirms it or a trading bot
              executes under its own mandate.
            </p>
          )}
          {issues.length > 0 && (
            <ul className="space-y-1 rounded-xl border border-amber-400/20 bg-amber-400/5 p-2 text-[11px] text-amber-200">
              {issues.slice(0, 4).map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          )}
          {error && (
            <p className="whitespace-pre-line rounded-xl border border-rose-400/20 bg-rose-400/5 p-2 text-[11px] text-rose-200">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={saving || issues.length > 0}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Users size={14} />}
            {desk ? 'Save changes' : 'Create desk'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
