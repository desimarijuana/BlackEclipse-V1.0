'use client';

// ── Thesis panel ────────────────────────────────────────────────────────────
// The plain-English input: the thesis, the instrument, the window and the
// capital. The model drafts the spec from this; it never computes results.

import React from 'react';
import { Loader2, Sparkles } from '@/lib/icons';

export interface ThesisInputs {
  prompt: string;
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  capital: number;
}

const FIELD =
  'mt-1 w-full rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 font-mono text-xs normal-case text-foreground outline-none focus:border-primary/40';

export function ThesisPanel({
  value,
  onChange,
  onDraft,
  drafting,
  disabled,
}: {
  value: ThesisInputs;
  onChange: (patch: Partial<ThesisInputs>) => void;
  onDraft: () => void;
  drafting: boolean;
  disabled: boolean;
}) {
  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Thesis</h2>
      </div>
      <textarea
        value={value.prompt}
        onChange={(event) => onChange({ prompt: event.target.value })}
        rows={7}
        className="w-full resize-y rounded-xl border border-white/10 bg-black/25 p-3 text-xs leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/40"
        placeholder="Describe entries, exits, sizing and risk in plain English."
      />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Symbol
          <input
            value={value.symbol}
            onChange={(event) => onChange({ symbol: event.target.value })}
            className={FIELD}
          />
        </label>
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Timeframe
          <select
            value={value.timeframe}
            onChange={(event) => onChange({ timeframe: event.target.value })}
            className={FIELD}
          >
            {['15m', '1h', '4h', '1d', '1w'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Start
          <input type="date" value={value.start} onChange={(event) => onChange({ start: event.target.value })} className={FIELD} />
        </label>
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground">
          End
          <input type="date" value={value.end} onChange={(event) => onChange({ end: event.target.value })} className={FIELD} />
        </label>
        <label className="col-span-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          Initial capital
          <input
            type="number"
            min={100}
            step={1000}
            value={value.capital}
            onChange={(event) => onChange({ capital: Number(event.target.value) || 0 })}
            className={FIELD}
          />
        </label>
      </div>
      <button
        type="button"
        onClick={onDraft}
        disabled={disabled}
        className="glass-button-add mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold disabled:opacity-50"
      >
        {drafting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        {drafting ? 'Drafting...' : 'Draft with AI'}
      </button>
      <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
        The model authors the spec only. Every fill, metric and drawdown is computed by the Eclipse quant engine.
      </p>
    </div>
  );
}
