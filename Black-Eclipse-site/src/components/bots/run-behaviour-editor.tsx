'use client';

// Run-behaviour builder shared by the creation flow and the detail editor. It
// exposes the engine's EXECUTION / CONCURRENCY / RETRY policy — what happens on a
// missed fire, an overlap, a failure — which the backend has always supported but
// the UI never surfaced. Everything maps 1:1 onto `buildPolicies` in
// `lib/bots/state.ts`; no scheduling logic lives here.

import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  CONFLICT_CHOICES, MISFIRE_CHOICES, type BotDraft, type ConflictChoice, type MisfireChoice,
} from '@/lib/bots/state';

export interface RunBehaviourEditorProps {
  draft: BotDraft;
  onChange: (patch: Partial<BotDraft>) => void;
}

function NumberField({
  label, value, min, max, onChange, ariaLabel,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
  ariaLabel: string;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value) || min)))}
        className="h-8 w-20"
        aria-label={ariaLabel}
      />
    </label>
  );
}

export function RunBehaviourEditor({ draft, onChange }: RunBehaviourEditorProps) {
  const t = useT();
  return (
    <div className="space-y-2.5">
      <div className="space-y-1">
        <div className="text-[11px] font-medium text-muted-foreground">{t('bots.behaviour.misfire')}</div>
        <Select
          value={draft.misfire}
          onValueChange={(v) => onChange({ misfire: (v ?? draft.misfire) as MisfireChoice })}
        >
          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>
            {MISFIRE_CHOICES.map((c) => (
              <SelectItem key={c} value={c}>{t(`bots.behaviour.misfire.${c}` as TranslationKey)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {draft.misfire === 'catch_up' && (
        <NumberField
          label={t('bots.behaviour.catchUpMax')}
          value={draft.catchUpMax}
          min={1}
          max={50}
          onChange={(n) => onChange({ catchUpMax: n })}
          ariaLabel={t('bots.behaviour.catchUpMax')}
        />
      )}

      <div className="space-y-1">
        <div className="text-[11px] font-medium text-muted-foreground">{t('bots.behaviour.onConflict')}</div>
        <Select
          value={draft.onConflict}
          onValueChange={(v) => onChange({ onConflict: (v ?? draft.onConflict) as ConflictChoice })}
        >
          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>
            {CONFLICT_CHOICES.map((c) => (
              <SelectItem key={c} value={c}>{t(`bots.behaviour.conflict.${c}` as TranslationKey)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <NumberField
        label={t('bots.behaviour.maxRuns')}
        value={draft.maxRuns}
        min={1}
        max={50}
        onChange={(n) => onChange({ maxRuns: n })}
        ariaLabel={t('bots.behaviour.maxRuns')}
      />
      <NumberField
        label={t('bots.behaviour.maxAttempts')}
        value={draft.maxAttempts}
        min={1}
        max={10}
        onChange={(n) => onChange({ maxAttempts: n })}
        ariaLabel={t('bots.behaviour.maxAttempts')}
      />
      <NumberField
        label={t('bots.behaviour.maxRuntime')}
        value={draft.maxRuntimeS}
        min={30}
        max={86400}
        onChange={(n) => onChange({ maxRuntimeS: n })}
        ariaLabel={t('bots.behaviour.maxRuntime')}
      />
    </div>
  );
}
