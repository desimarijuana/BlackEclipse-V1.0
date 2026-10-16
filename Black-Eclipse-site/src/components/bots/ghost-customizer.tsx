// ── Ghost customizer ─────────────────────────────────────────────────────────
// The "random customizer" for a bot's face: a live preview plus per-part option
// strips (body, eyes, mouth, accessory, pattern) and two color pickers. Every
// part is a closed, authored option set from `lib/bots/ghost`, so a custom face
// can never render broken. Controlled: the parent owns the `spec`.

'use client';

import { cn } from '@/lib/utils';
import { Shuffle } from '@/lib/icons';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n';
import { GhostAvatar } from './ghost-avatar';
import { LiveGhostAvatar } from './live-ghost-avatar';
import {
  GHOST_ACCESSORY_COUNT,
  GHOST_EYE_COUNT,
  GHOST_MOUTH_COUNT,
  GHOST_PALETTE,
  GHOST_PATTERN_COUNT,
  GHOST_VARIANT_COUNT,
  type GhostSpec,
} from '@/lib/bots/ghost';

export interface GhostCustomizerProps {
  spec: GhostSpec;
  onChange: (spec: GhostSpec) => void;
  onRandomize: () => void;
  onReset: () => void;
  className?: string;
}

type PartKey = 'variant' | 'eyes' | 'mouth' | 'accessory' | 'pattern';

const PARTS: Array<{ key: PartKey; count: number; labelKey: TranslationKey }> = [
  { key: 'variant', count: GHOST_VARIANT_COUNT, labelKey: 'bots.body' },
  { key: 'eyes', count: GHOST_EYE_COUNT, labelKey: 'bots.eyes' },
  { key: 'mouth', count: GHOST_MOUTH_COUNT, labelKey: 'bots.mouth' },
  { key: 'accessory', count: GHOST_ACCESSORY_COUNT, labelKey: 'bots.accessory' },
  { key: 'pattern', count: GHOST_PATTERN_COUNT, labelKey: 'bots.pattern' },
];

function OptionStrip({
  label,
  count,
  selected,
  spec,
  part,
  onSelect,
}: {
  label: string;
  count: number;
  selected: number;
  spec: GhostSpec;
  part: PartKey;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: count }, (_, i) => {
          const active = selected === i;
          return (
            <button
              key={i}
              type="button"
              onClick={() => onSelect(i)}
              aria-pressed={active}
              className={cn(
                'flex h-11 w-11 items-center justify-center rounded-xl border transition-colors cursor-pointer',
                active
                  ? 'border-white/40 bg-white/[0.10]'
                  : 'border-transparent bg-white/[0.03] hover:bg-white/[0.07]',
              )}
            >
              <GhostAvatar spec={{ ...spec, [part]: i }} size={30} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ColorRow({
  label,
  value,
  onPick,
  accent = false,
}: {
  label: string;
  value: string;
  onPick: (hex: string) => void;
  accent?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {GHOST_PALETTE.map((pair) => {
          const hex = accent ? pair.accent : pair.body;
          const active = hex.toLowerCase() === value.toLowerCase();
          return (
            <button
              key={hex}
              type="button"
              onClick={() => onPick(hex)}
              aria-pressed={active}
              aria-label={hex}
              className={cn(
                'h-6 w-6 rounded-full border transition-transform cursor-pointer',
                active ? 'scale-110 border-white/70' : 'border-white/20 hover:scale-105',
              )}
              style={{ backgroundColor: hex }}
            />
          );
        })}
        <label
          className="relative ml-1 inline-flex h-6 w-6 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-white/25"
          style={{ backgroundColor: value }}
          title={label}
        >
          <input
            type="color"
            value={value}
            onChange={(e) => onPick(e.target.value)}
            aria-label={`${label} — custom`}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          />
        </label>
      </div>
    </div>
  );
}

export function GhostCustomizer({ spec, onChange, onRandomize, onReset, className }: GhostCustomizerProps) {
  const t = useT();
  return (
    <div className={cn('glass-card rounded-2xl p-4', className)}>
      <div className="flex items-start gap-4">
        <div className="flex flex-col items-center gap-2">
          <div className="glass-card-subtle flex h-28 w-28 items-center justify-center rounded-2xl">
            <LiveGhostAvatar spec={spec} size={92} interactive />
          </div>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={onRandomize}
              className="glass-card-subtle inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium hover:text-foreground cursor-pointer"
            >
              <Shuffle size={13} /> {t('bots.randomize')}
            </button>
            <button
              type="button"
              onClick={onReset}
              className="glass-card-subtle rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground cursor-pointer"
            >
              {t('common.reset')}
            </button>
          </div>
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          {PARTS.map(({ key, count, labelKey }) => (
            <OptionStrip
              key={key}
              label={t(labelKey)}
              count={count}
              selected={spec[key]}
              spec={spec}
              part={key}
              onSelect={(index) => onChange({ ...spec, [key]: index })}
            />
          ))}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ColorRow
              label={t('bots.bodyColor')}
              value={spec.bodyColor}
              onPick={(hex) => onChange({ ...spec, bodyColor: hex })}
            />
            <ColorRow
              label={t('bots.accentColor')}
              value={spec.accentColor}
              accent
              onPick={(hex) => onChange({ ...spec, accentColor: hex })}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
