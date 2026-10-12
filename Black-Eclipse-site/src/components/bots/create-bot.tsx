'use client';

// Guided bot creation. Two reviewable steps — describe, then confirm — that
// persist through the REAL automation API. Nothing is saved until the user
// confirms; a draft is always distinguishable from a saved bot. No LLM is
// required: names and instructions are derived deterministically from the
// objective, and the same tools are available to the chat agent.

import { useMemo, useState } from 'react';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n';
import { ArrowLeft, CheckCircle2, Plus, Play, Sparkles } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { ScheduleEditor } from '@/components/bots/schedule-editor';
import { createAutomation, type AutomationView } from '@/lib/harness/automation-browser';
import { avatarFor, useBotAvatarStore } from '@/lib/bots/avatar-store';
import {
  BOT_AGENTS,
  buildTrigger,
  emptyBotDraft,
  summarizeDraft,
  suggestName,
  validateDraft,
  type BotDraft,
  type DraftIssue,
} from '@/lib/bots/state';

export interface CreateBotProps {
  existingNames: string[];
  onCreated: (bot: AutomationView) => void;
  onRunNow: (bot: AutomationView) => void;
  onClose: () => void;
  onCreateWithChat: (prefill: string) => void;
}

function IssueText({ issue }: { issue?: DraftIssue }) {
  if (!issue) return null;
  return <p className="mt-1 text-xs text-rose-300">{issue.message}</p>;
}

export function CreateBot({ existingNames, onCreated, onRunNow, onClose, onCreateWithChat }: CreateBotProps) {
  const t = useT();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const [step, setStep] = useState<'describe' | 'review'>('describe');
  const [draft, setDraft] = useState<BotDraft>(emptyBotDraft());
  const [issues, setIssues] = useState<DraftIssue[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<AutomationView | null>(null);

  const names = useMemo(() => existingNames.map((n) => n.trim().toLowerCase()), [existingNames]);
  const issueFor = (field: DraftIssue['field']) => issues.find((i) => i.field === field);

  const patch = (p: Partial<BotDraft>) => {
    setDraft((d) => ({ ...d, ...p }));
    setIssues((prev) => prev.filter((i) => !(i.field in p)));
  };

  const toReview = () => {
    const derivedName = draft.name.trim() || suggestName(draft.objective);
    const next = { ...draft, name: derivedName };
    setDraft(next);
    const local = validateDraft(next).filter((i) => i.field !== 'schedule');
    setIssues(local);
    if (local.length === 0) setStep('review');
  };

  const save = async () => {
    if (saving) return;
    const found = validateDraft(draft);
    if (names.includes(draft.name.trim().toLowerCase())) {
      found.push({ field: 'name', message: t('bots.create.duplicate') });
    }
    setIssues(found);
    if (found.length) return;
    setSaving(true);
    setError(null);
    try {
      const bot = await createAutomation({
        name: draft.name.trim(),
        description: draft.objective.trim(),
        state: 'active',
        trigger: buildTrigger(draft),
        action: { type: 'run_agent', objective: draft.objective.trim(), agentId: draft.agentId },
        tags: ['bot'],
      });
      setCreated(bot);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'creation failed');
    } finally {
      setSaving(false);
    }
  };

  if (created) {
    return (
      <div className="glass-card rounded-2xl p-5">
        <div className="flex items-center gap-2 text-emerald-300">
          <CheckCircle2 size={18} weight="fill" />
          <h2 className="text-sm font-semibold">{t('bots.create.saved', { name: created.name })}</h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{t('bots.create.savedHint')}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => onCreated(created)}>{t('bots.create.openNow')}</Button>
          <Button variant="outline" onClick={() => onRunNow(created)}>
            <Play size={14} /> {t('bots.create.runNow')}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setCreated(null);
              setDraft(emptyBotDraft());
              setIssues([]);
              setStep('describe');
            }}
          >
            <Plus size={14} /> {t('bots.create.another')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl p-5">
      <div className="mb-3 flex items-start gap-3">
        <GhostAvatar spec={avatarFor(avatars, draft.name || 'new-bot')} size={44} />
        <div>
          <h2 className="text-sm font-semibold">
            {step === 'describe' ? t('bots.create.title') : t('bots.create.reviewTitle')}
          </h2>
          <p className="text-xs text-muted-foreground">
            {step === 'describe' ? t('bots.create.intro') : t('bots.create.reviewHint')}
          </p>
        </div>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={onClose}>
          {t('bots.cancel')}
        </Button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {step === 'describe' ? (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="bot-objective">
              {t('bots.create.describe')}
            </label>
            <textarea
              id="bot-objective"
              value={draft.objective}
              onChange={(e) => patch({ objective: e.target.value })}
              placeholder={t('bots.create.describeHint')}
              rows={4}
              className="min-h-24 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <IssueText issue={issueFor('objective')} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={toReview} disabled={!draft.objective.trim()}>
              {t('bots.create.analyze')}
            </Button>
            <Button variant="ghost" onClick={() => onCreateWithChat(draft.objective)}>
              <Sparkles size={14} /> {t('bots.createWithChat')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="bot-name">
                {t('bots.create.name')}
              </label>
              <Input id="bot-name" value={draft.name} onChange={(e) => patch({ name: e.target.value })} />
              <IssueText issue={issueFor('name')} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {t('bots.create.agent')}
              </label>
              <Select value={draft.agentId} onValueChange={(v) => patch({ agentId: v ?? draft.agentId })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BOT_AGENTS.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="bot-purpose">
                {t('bots.create.purpose')}
              </label>
              <textarea
                id="bot-purpose"
                value={draft.objective}
                onChange={(e) => patch({ objective: e.target.value })}
                rows={3}
                className="min-h-16 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
              />
              <IssueText issue={issueFor('objective')} />
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">{t('bots.create.scheduleTitle')}</div>
            <ScheduleEditor draft={draft} onChange={patch} />
            <p className="mt-2 text-xs text-muted-foreground">
              {t('bots.create.summaryLabel')}: <span className="text-foreground">{summarizeDraft(draft)}</span>
            </p>
            <IssueText issue={issueFor('schedule')} />
          </div>

          <ReviewSummary draft={draft} />

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={() => setStep('describe')}>
              <ArrowLeft size={14} /> {t('bots.create.back')}
            </Button>
            <Button onClick={save} disabled={saving}>
              {saving ? t('bots.creating') : t('bots.create.confirm')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Honest review of what will be saved. Fields the backend does not let us set
 *  here are shown as their real defaults rather than hidden. */
function ReviewSummary({ draft }: { draft: BotDraft }) {
  const t = useT();
  const rows: Array<[TranslationKey, string]> = [
    ['bots.create.scheduleTitle', summarizeDraft(draft)],
    ['bots.detail.capabilities', 'Default capabilities for this agent — no extra permissions granted'],
    ['bots.requiresApproval', 'None — research only, no automatic external actions'],
    ['bots.budget', 'Runtime defaults'],
    ['bots.notifications', 'In-app on success and failure'],
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded-xl glass-card-subtle p-3 text-xs sm:grid-cols-2">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt className="font-semibold text-muted-foreground">{t(key)}</dt>
          <dd className="text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
