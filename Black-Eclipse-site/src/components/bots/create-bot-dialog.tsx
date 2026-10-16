'use client';

// ── New bot dialog ───────────────────────────────────────────────────────────
// The primary creation surface: pick a face (or upload a photo), name it, give it
// a title and a description, and optionally open Advanced to fine-tune the
// schedule. Nothing is saved until "Create bot" — creation persists through the
// REAL automation API and the chosen avatar through the client avatar store.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { ChevronDown, ImagePlus, Lock, Shuffle, Sparkles } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { ScheduleEditor } from '@/components/bots/schedule-editor';
import { RunBehaviourEditor } from '@/components/bots/run-behaviour-editor';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { createAutomation, type AutomationView } from '@/lib/harness/automation-browser';
import { useBotAvatarStore } from '@/lib/bots/avatar-store';
import { fileToAvatarDataUrl } from '@/lib/bots/image';
import {
  DEFAULT_GHOST_SPEC, createRng, ghostSpecFromId, ghostSpecKey, randomGhostSpec, type GhostSpec,
} from '@/lib/bots/ghost';
import {
  BOT_AGENTS, buildPolicies, buildTrigger, detectSchedule, emptyBotDraft, validateDraft,
  type BotDraft, type DraftIssue,
} from '@/lib/bots/state';

const FACE_COUNT = 12;

type Tab = 'bot' | 'generate' | 'upload' | 'pet';

const TABS: ReadonlyArray<{ id: Tab; labelKey: string }> = [
  { id: 'bot', labelKey: 'bots.dialog.tab.bot' },
  { id: 'generate', labelKey: 'bots.dialog.tab.generate' },
  { id: 'upload', labelKey: 'bots.dialog.tab.upload' },
  { id: 'pet', labelKey: 'bots.dialog.tab.pet' },
];

const PET_VARIANTS = [2, 3, 1, 2, 3, 0, 2, 1, 3, 0, 1, 2] as const;

export interface CreateBotDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingNames: string[];
  onCreated: (bot: AutomationView) => void;
}

export function CreateBotDialog({ open, onOpenChange, existingNames, onCreated }: CreateBotDialogProps) {
  const t = useT();
  const setAvatar = useBotAvatarStore((s) => s.setAvatar);
  const setAvatarImage = useBotAvatarStore((s) => s.setImage);

  const [tab, setTab] = useState<Tab>('bot');
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1e9));
  const [variantLock, setVariantLock] = useState<number | null>(null);
  const [spec, setSpec] = useState<GhostSpec>(() => randomGhostSpec(createRng()));
  const [locked, setLocked] = useState(false);
  const [followName, setFollowName] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState<BotDraft>(() => emptyBotDraft());
  // True once the operator edits the schedule by hand in Advanced — after that,
  // a schedule phrase in the description must NOT override their explicit choice.
  const [scheduleTouched, setScheduleTouched] = useState(false);
  const [detectedSchedule, setDetectedSchedule] = useState<string | null>(null);
  // True while the current schedule came from the description (not the operator).
  // Lets us revert to "on demand" when that phrase is deleted, instead of leaving
  // a phantom schedule the user can no longer see.
  const [autoSchedule, setAutoSchedule] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [issues, setIssues] = useState<DraftIssue[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Fresh dialog each time it opens — a new face, empty fields, collapsed Advanced.
  useEffect(() => {
    if (!open) return;
    const nextSeed = Math.floor(Math.random() * 1e9);
    setTab('bot');
    setSeed(nextSeed);
    setVariantLock(null);
    setSpec(randomGhostSpec(createRng(nextSeed)));
    setLocked(false);
    setFollowName(false);
    setImage(null);
    setName('');
    setTitle('');
    setDescription('');
    setDraft(emptyBotDraft());
    setScheduleTouched(false);
    setDetectedSchedule(null);
    setAutoSchedule(false);
    setAdvanced(false);
    setIssues([]);
    setError(null);
  }, [open]);

  const candidates = useMemo<GhostSpec[]>(() => {
    const rng = createRng(seed);
    return Array.from({ length: FACE_COUNT }, () => {
      const face = randomGhostSpec(rng);
      return variantLock === null ? face : { ...face, variant: variantLock };
    });
  }, [seed, variantLock]);

  const petFaces = useMemo<GhostSpec[]>(() => {
    const rng = createRng(seed + 7);
    return Array.from({ length: FACE_COUNT }, (_, i) => ({
      ...randomGhostSpec(rng),
      variant: PET_VARIANTS[i % PET_VARIANTS.length],
    }));
  }, [seed]);

  const nameKey = useMemo(() => name.trim().toLowerCase(), [name]);
  const issueFor = (field: DraftIssue['field']) => issues.find((i) => i.field === field);

  const randomize = useCallback(() => {
    if (locked) return;
    const nextSeed = Math.floor(Math.random() * 1e9);
    setSeed(nextSeed);
    setFollowName(false);
    setSpec(randomGhostSpec(createRng(nextSeed)));
  }, [locked]);

  const onNameChange = (value: string) => {
    setName(value);
    if (followName) setSpec(ghostSpecFromId(value.trim() || 'new-bot'));
  };

  // Read a schedule out of the description ("check my portfolio every 5 minutes")
  // and apply it, unless the operator has already set the schedule by hand.
  const onDescriptionChange = (value: string) => {
    setDescription(value);
    setIssues((prev) => prev.filter((i) => i.field !== 'objective'));
    if (scheduleTouched) return;
    const detected = detectSchedule(value);
    if (detected) {
      setDraft((d) => ({ ...d, ...detected.patch }));
      setDetectedSchedule(detected.summary);
      setAutoSchedule(true);
    } else {
      setDetectedSchedule(null);
      // The phrase that scheduled it is gone — undo the auto-schedule so the bot
      // is not silently left on a cadence the description no longer mentions.
      if (autoSchedule) {
        setDraft((d) => ({ ...d, schedule: 'manual' }));
        setAutoSchedule(false);
      }
    }
  };

  const pickFace = (face: GhostSpec) => {
    setFollowName(false);
    setSpec(face);
  };

  const useClassicShapes = () => {
    setFollowName(false);
    setVariantLock(0);
    setSpec({ ...DEFAULT_GHOST_SPEC, bodyColor: spec.bodyColor, accentColor: spec.accentColor });
  };

  const onUpload = async (file: File | undefined) => {
    if (!file) return;
    try {
      setError(null);
      setImage(await fileToAvatarDataUrl(file));
      setTab('upload');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read the image.');
    }
  };

  const create = useCallback(async () => {
    if (saving) return;
    const nextDraft: BotDraft = { ...draft, name: name.trim(), objective: description.trim() };
    const found = validateDraft(nextDraft);
    if (nameKey && existingNames.some((n) => n.trim().toLowerCase() === nameKey)) {
      found.push({ field: 'name', message: t('bots.create.duplicate') });
    }
    setIssues(found);
    if (found.length) return;
    setSaving(true);
    setError(null);
    try {
      const bot = await createAutomation({
        name: nextDraft.name,
        description: title.trim() || undefined,
        state: 'active',
        trigger: buildTrigger(nextDraft),
        action: { type: 'run_agent', objective: nextDraft.objective, agentId: nextDraft.agentId },
        ...buildPolicies(nextDraft),
        tags: ['bot'],
      });
      setAvatar(bot.id, spec);
      setAvatarImage(bot.id, image);
      onCreated(bot);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'creation failed');
    } finally {
      setSaving(false);
    }
  }, [saving, draft, name, description, title, nameKey, existingNames, t, spec, image, onCreated, onOpenChange, setAvatar, setAvatarImage]);

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!saving) onOpenChange(next); }}>
      <DialogContent className="glass-card-strong max-h-[92vh] overflow-y-auto rounded-2xl border border-white/15 dark:border-white/10 sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('bots.dialog.title')}</DialogTitle>
          <DialogDescription>{t('bots.dialog.subtitle')}</DialogDescription>
        </DialogHeader>

        {/* Face preview */}
        <div className="flex justify-center">
          <div className="glass-card-subtle flex h-20 w-20 items-center justify-center rounded-2xl">
            {image ? (
              <img src={image} alt="" className="h-16 w-16 rounded-xl object-cover" />
            ) : (
              <GhostAvatar spec={spec} size={62} />
            )}
          </div>
        </div>

        {/* Tab strip */}
        <div role="tablist" className="grid grid-cols-4 gap-1 rounded-xl glass-card-subtle p-1">
          {TABS.map(({ id, labelKey }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={cn(
                'rounded-lg py-1.5 text-xs font-semibold transition-colors cursor-pointer',
                tab === id ? 'bg-white/[0.09] text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(labelKey as never)}
            </button>
          ))}
        </div>

        {tab === 'upload' ? (
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="glass-card-subtle flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed border-border/50 px-4 py-6 text-xs text-muted-foreground hover:border-border hover:text-foreground"
            >
              <ImagePlus size={20} />
              {t('bots.dialog.uploadHint')}
              <span className="font-semibold text-foreground">{t('bots.dialog.chooseFile')}</span>
            </button>
            {image && (
              <div className="flex items-center justify-between gap-2 rounded-xl glass-card-subtle px-3 py-2">
                <span className="flex items-center gap-2 text-xs">
                  <img src={image} alt="" className="h-7 w-7 rounded-md object-cover" />
                  {t('bots.dialog.uploaded')}
                </span>
                <button type="button" onClick={() => setImage(null)} className="text-xs text-muted-foreground hover:text-foreground">
                  {t('bots.dialog.removeImage')}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2.5">
            <div className="grid grid-cols-6 gap-1.5">
              {tab === 'bot' && (
                <button
                  type="button"
                  onClick={randomize}
                  disabled={locked}
                  title={t('bots.dialog.auto')}
                  className="flex h-11 items-center justify-center rounded-xl border border-transparent bg-white/[0.03] text-[10px] font-semibold text-muted-foreground hover:bg-white/[0.07] disabled:opacity-40"
                >
                  {t('bots.dialog.auto')}
                </button>
              )}
              {(tab === 'pet' ? petFaces : tab === 'generate' ? candidates.slice(0, 1) : candidates).map((face, i) => {
                const active = !image && ghostSpecKey(face) === ghostSpecKey(spec);
                return (
                  <button
                    key={`${ghostSpecKey(face)}-${i}`}
                    type="button"
                    onClick={() => pickFace(face)}
                    aria-pressed={active}
                    className={cn(
                      'flex h-11 items-center justify-center rounded-xl border transition-colors cursor-pointer',
                      active ? 'border-white/40 bg-white/[0.10]' : 'border-transparent bg-white/[0.03] hover:bg-white/[0.07]',
                    )}
                  >
                    <GhostAvatar spec={face} size={30} />
                  </button>
                );
              })}
            </div>

            <div className="flex items-center justify-center gap-2 pt-0.5">
              <button
                type="button"
                onClick={randomize}
                disabled={locked}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-white/[0.06] hover:text-foreground disabled:opacity-40 cursor-pointer"
              >
                <Shuffle size={13} /> {tab === 'generate' ? t('bots.dialog.generate') : t('bots.dialog.randomize')}
              </button>
              <button
                type="button"
                onClick={() => setLocked((v) => !v)}
                aria-pressed={locked}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium cursor-pointer',
                  locked ? 'bg-white/[0.09] text-foreground' : 'text-muted-foreground hover:bg-white/[0.06] hover:text-foreground',
                )}
              >
                <Lock size={13} /> {locked ? t('bots.dialog.unlockFace') : t('bots.dialog.lockFace')}
              </button>
            </div>

            {tab === 'bot' && (
              <div className="flex items-center justify-center gap-4 text-[11px] text-muted-foreground">
                <button
                  type="button"
                  onClick={() => { setFollowName(true); setSpec(ghostSpecFromId(name.trim() || 'new-bot')); setVariantLock(null); }}
                  className={cn('hover:text-foreground cursor-pointer', followName && 'text-foreground')}
                >
                  {t('bots.dialog.followName')}
                </button>
                <button type="button" onClick={useClassicShapes} className="hover:text-foreground cursor-pointer">
                  {t('bots.dialog.classicShapes')}
                </button>
              </div>
            )}
          </div>
        )}

        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => { void onUpload(e.target.files?.[0]); e.target.value = ''; }}
        />

        {/* Identity fields */}
        <div className="space-y-3">
          <Field label={t('bots.dialog.name')} htmlFor="new-bot-name">
            <Input
              id="new-bot-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder={t('bots.dialog.namePlaceholder')}
              autoFocus
            />
            <FieldError issue={issueFor('name')} />
          </Field>
          <Field label={t('bots.dialog.titleField')} htmlFor="new-bot-title">
            <Input
              id="new-bot-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('bots.dialog.titlePlaceholder')}
            />
          </Field>
          <Field label={t('bots.dialog.description')} htmlFor="new-bot-description">
            <textarea
              id="new-bot-description"
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              rows={3}
              placeholder={t('bots.dialog.descriptionPlaceholder')}
              className="min-h-16 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <FieldError issue={issueFor('objective')} />
            {detectedSchedule && !scheduleTouched && (
              <p className="mt-1 flex items-center gap-1.5 text-[11px] text-emerald-300/90">
                <Sparkles size={11} className="shrink-0" />
                {t('bots.schedule')}: {detectedSchedule}
              </p>
            )}
          </Field>
        </div>

        {/* Advanced — schedule + agent, collapsed by default */}
        <div className="rounded-xl glass-card-subtle">
          <button
            type="button"
            onClick={() => setAdvanced((v) => !v)}
            aria-expanded={advanced}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
          >
            <ChevronDown size={13} className={cn('transition-transform', !advanced && '-rotate-90')} />
            {t('bots.dialog.advanced')}
          </button>
          {advanced && (
            <div className="space-y-3 border-t border-border/10 px-3 py-3">
              <div>
                <div className="mb-1 text-[11px] font-medium text-muted-foreground">{t('bots.create.agent')}</div>
                <Select value={draft.agentId} onValueChange={(v) => setDraft((d) => ({ ...d, agentId: v ?? d.agentId }))}>
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
              <div>
                <div className="mb-1 text-[11px] font-medium text-muted-foreground">{t('bots.dialog.schedule')}</div>
                <ScheduleEditor
                  draft={draft}
                  onChange={(patch) => {
                    setScheduleTouched(true);
                    setDetectedSchedule(null);
                    setAutoSchedule(false);
                    setDraft((d) => ({ ...d, ...patch }));
                    setIssues((prev) => prev.filter((i) => i.field !== 'schedule' && i.field !== 'cron' && i.field !== 'runAt' && i.field !== 'intervalValue'));
                  }}
                />
                <FieldError issue={issueFor('schedule') ?? issueFor('cron') ?? issueFor('runAt') ?? issueFor('intervalValue')} />
              </div>
              <div>
                <div className="mb-1 text-[11px] font-medium text-muted-foreground">{t('bots.behaviour.title')}</div>
                <RunBehaviourEditor
                  draft={draft}
                  onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
                />
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
            {error}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('bots.dialog.cancel')}
          </Button>
          <Button onClick={() => void create()} disabled={saving || !name.trim() || !description.trim()}>
            {saving ? t('bots.dialog.creating') : (
              <>
                <Sparkles size={14} /> {t('bots.dialog.create')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

function FieldError({ issue }: { issue?: DraftIssue }) {
  if (!issue) return null;
  return <p className="mt-1 text-xs text-rose-300">{issue.message}</p>;
}
