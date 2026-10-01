'use client';

// ── Job editor (Phase 6) ─────────────────────────────────────────────────────
// Cadence is offered in human language; the schedule expression is DATA shown
// only behind "details". The user never authors a definition or meets a skill id.

import { useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { cn } from '@/lib/utils';
import type { CreateJobInput, DeliveryAdapter, JobDefinitionView, JobKind } from '@/lib/harness/jobs-client';

type Cadence = 'weekdayMorning' | 'daily' | 'every6h' | 'every12h' | 'fileChange' | 'webAddress' | 'manual';

// The destination picker offers a HUMAN choice; the adapter name is data behind it.
const DELIVERY_KEY: Record<DeliveryAdapter, TranslationKey> = {
  in_app: 'jobs.editor.delivery.inApp',
  artifact: 'jobs.editor.delivery.artifact',
  messaging: 'jobs.editor.delivery.messaging',
};

const DELIVERY_ADAPTERS: DeliveryAdapter[] = ['in_app', 'artifact', 'messaging'];

const CADENCE_KEY: Record<Cadence, TranslationKey> = {
  weekdayMorning: 'jobs.editor.cadence.weekdayMorning',
  daily: 'jobs.editor.cadence.daily',
  every6h: 'jobs.editor.cadence.every6h',
  every12h: 'jobs.editor.cadence.every12h',
  fileChange: 'jobs.editor.cadence.fileChange',
  webAddress: 'jobs.editor.cadence.webAddress',
  manual: 'jobs.editor.cadence.manual',
};

const CADENCES: Cadence[] = ['weekdayMorning', 'daily', 'every6h', 'every12h', 'fileChange', 'webAddress', 'manual'];

function cadenceToKind(cadence: Cadence): { kind: JobKind; cron?: string; intervalSeconds?: number } {
  switch (cadence) {
    case 'weekdayMorning':
      return { kind: 'cron', cron: '30 7 * * 1-5' };
    case 'daily':
      return { kind: 'cron', cron: '0 8 * * *' };
    case 'every6h':
      return { kind: 'interval', intervalSeconds: 6 * 3600 };
    case 'every12h':
      return { kind: 'interval', intervalSeconds: 12 * 3600 };
    case 'fileChange':
      return { kind: 'file_watch' };
    case 'webAddress':
      return { kind: 'webhook' };
    default:
      return { kind: 'manual' };
  }
}

export interface JobEditorProps {
  initial?: JobDefinitionView;
  onSave: (input: CreateJobInput) => Promise<void>;
  onCancel?: () => void;
}

export function JobEditor({ initial, onSave, onCancel }: JobEditorProps) {
  const t = useT();
  const [name, setName] = useState(initial?.name ?? '');
  const [objective, setObjective] = useState(initial?.target?.objective ?? '');
  const [cadence, setCadence] = useState<Cadence>(kindToCadence(initial));
  const [folder, setFolder] = useState(initial?.target?.workspaceRoot ?? '');
  const [adapter, setAdapter] = useState<DeliveryAdapter>(initial?.delivery?.adapter ?? 'in_app');
  const [destination, setDestination] = useState(initial?.delivery?.destination ?? '');
  const [showDetails, setShowDetails] = useState(false);
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    const { kind, cron, intervalSeconds } = cadenceToKind(cadence);
    // The user's chosen label travels as DATA; the adapter name stays behind it.
    const label = destination.trim() || t(DELIVERY_KEY[adapter]);
    const input: CreateJobInput = {
      name: name.trim() || t('jobs.title'),
      kind,
      cron,
      intervalSeconds,
      watchPath: kind === 'file_watch' ? folder : undefined,
      onMissed: 'skip',
      target: {
        kind: 'objective',
        objective: objective.trim() || name.trim(),
        agentId: 'eclipse-agent',
        workspaceRoot: folder.trim() || null,
      },
      delivery: {
        adapter,
        destination: label,
        targets: [{ destination: label, adapter }],
      },
    };
    try {
      await onSave(input);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="glass-card rounded-2xl p-3.5">
      <label className="block text-[12px] text-muted-foreground">
        {t('jobs.editor.name')}
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('jobs.editor.namePlaceholder')}
          className="mt-1 w-full rounded-lg bg-background/60 px-2.5 py-1.5 text-[13px] text-foreground outline-none"
        />
      </label>

      <label className="mt-2.5 block text-[12px] text-muted-foreground">
        What should it do?
        <input
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          className="mt-1 w-full rounded-lg bg-background/60 px-2.5 py-1.5 text-[13px] text-foreground outline-none"
        />
      </label>

      <p className="mt-3 text-[12px] text-muted-foreground">{t('jobs.editor.cadence')}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {CADENCES.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setCadence(option)}
            className={cn(
              'glass-card-subtle rounded-lg px-2.5 py-1 text-[11px] transition-colors',
              cadence === option ? 'border border-primary/50 text-foreground' : 'text-muted-foreground',
            )}
          >
            {t(CADENCE_KEY[option])}
          </button>
        ))}
      </div>

      {(cadence === 'fileChange' || cadence === 'webAddress') && (
        <label className="mt-2.5 block text-[12px] text-muted-foreground">
          {t('jobs.editor.whichFolder')}
          <input
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            className="mt-1 w-full rounded-lg bg-background/60 px-2.5 py-1.5 text-[13px] text-foreground outline-none"
          />
        </label>
      )}

      <p className="mt-3 text-[12px] text-muted-foreground">{t('jobs.editor.delivery')}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {DELIVERY_ADAPTERS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setAdapter(option)}
            className={cn(
              'glass-card-subtle rounded-lg px-2.5 py-1 text-[11px] transition-colors',
              adapter === option ? 'border border-primary/50 text-foreground' : 'text-muted-foreground',
            )}
          >
            {t(DELIVERY_KEY[option])}
          </button>
        ))}
      </div>

      {adapter === 'messaging' && (
        <label className="mt-2.5 block text-[12px] text-muted-foreground">
          {t('jobs.editor.destination')}
          <input
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder={t('jobs.editor.destination.placeholder')}
            className="mt-1 w-full rounded-lg bg-background/60 px-2.5 py-1.5 text-[13px] text-foreground outline-none"
          />
        </label>
      )}

      <button
        type="button"
        onClick={() => setShowDetails((v) => !v)}
        className="mt-2 text-[11px] text-muted-foreground underline-offset-2 hover:underline"
      >
        {t('jobs.editor.details')}
      </button>
      {showDetails && (
        <pre className="glass-card-subtle mt-1.5 overflow-x-auto rounded-lg p-2 text-[11px] text-muted-foreground">
          {JSON.stringify(
            { kind: cadenceToKind(cadence), adapter, destination: destination || null, folder: folder || null },
            null,
            2,
          )}
        </pre>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={submit}
          className="glass-button rounded-lg px-3 py-1.5 text-[12px] text-foreground disabled:opacity-50"
        >
          {t('jobs.editor.save')}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-[11px] text-muted-foreground hover:underline">
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function kindToCadence(job?: JobDefinitionView): Cadence {
  if (!job) return 'weekdayMorning';
  if (job.kind === 'interval') return job.intervalSeconds === 12 * 3600 ? 'every12h' : 'every6h';
  if (job.kind === 'file_watch') return 'fileChange';
  if (job.kind === 'webhook') return 'webAddress';
  if (job.kind === 'manual') return 'manual';
  if (job.cron === '0 8 * * *') return 'daily';
  return 'weekdayMorning';
}
