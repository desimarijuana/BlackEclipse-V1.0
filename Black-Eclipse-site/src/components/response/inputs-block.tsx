'use client';

// ── The `inputs` block ────────────────────────────────────────────────────────
// Renders the envelope-level shared `state` as controls. A change here updates
// the message's envelope state; every figure bound to a `computed` value (or the
// same state) re-renders LOCALLY with 0 model calls. Renders nothing when the
// response carries no envelope state.

import { SlidersHorizontal } from '@/lib/icons';
import type { InputsBlock as InputsBlockType, StateVar } from '@/lib/response/contract';
import { reportResponseTelemetry } from '@/lib/response/telemetry';
import { useInputsState } from './figure-context';

function clamp(n: number, min?: number, max?: number): number {
  let out = n;
  if (min != null) out = Math.max(min, out);
  if (max != null) out = Math.min(max, out);
  return out;
}

function StateControl({
  variable,
  value,
  onChange,
}: {
  variable: StateVar;
  value: number;
  onChange: (next: number) => void;
}) {
  const id = `input-${variable.id}`;
  const label = variable.label ?? variable.id;
  if (variable.kind === 'toggle') {
    return (
      <label htmlFor={id} className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        {label}
        <input
          id={id}
          type="checkbox"
          checked={value !== 0}
          onChange={(e) => onChange(e.target.checked ? 1 : 0)}
          className="h-4 w-4 cursor-pointer accent-primary"
        />
      </label>
    );
  }
  if (variable.kind === 'select') {
    return (
      <label htmlFor={id} className="flex flex-col gap-1.5">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <select
          id={id}
          value={String(value)}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full rounded-lg border border-border/50 bg-background/40 px-2 py-1 text-[12px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          {(variable.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const min = variable.min ?? 0;
  const max = variable.max ?? Math.max(min + 100, value * 2 || 100);
  const step = variable.step ?? 0.01;
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between text-[11px] text-muted-foreground">
        {label}
        <span className="font-mono tabular-nums text-foreground">{value}</span>
      </span>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(clamp(Number(e.target.value), min, max))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-accent accent-primary"
        aria-label={label}
      />
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(clamp(n, min, max));
        }}
        className="w-full rounded-lg border border-border/50 bg-background/40 px-2 py-1 font-mono text-[12px] tabular-nums text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        aria-label={`${label} value`}
      />
    </label>
  );
}

export function InputsBlock({ block }: { block: InputsBlockType }) {
  const state = useInputsState();
  if (!state) return null;
  const vars = block.vars ? state.vars.filter((v) => block.vars?.includes(v.id)) : state.vars;
  if (vars.length === 0) return null;
  return (
    <div className="w-full">
      <div className="glass-card rounded-2xl p-3.5">
        <div className="mb-3 flex items-center gap-2">
          <SlidersHorizontal size={14} className="text-primary/70" />
          <h4 className="text-sm font-semibold text-foreground">{block.title ?? 'Inputs'}</h4>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {vars.map((variable) => (
            <StateControl
              key={variable.id}
              variable={variable}
              value={state.values[variable.id] ?? variable.value}
              onChange={(next) => {
                reportResponseTelemetry({ event: 'interaction', blockType: 'inputs' });
                state.setValue(variable.id, next);
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
