'use client';

// ── The `simulation` block: a declarative in-chat calculator ──────────────────
// Inputs are local state; outputs are safe expressions evaluated LOCALLY by the
// shared evaluator (`lib/response/evaluate.ts`). No model call, no backend, no
// arbitrary code — a slider move recomputes in place.
//
// It is explicitly ILLUSTRATIVE: it never reads market data, and every figure is
// derived only from the user's own inputs. The "Illustrative" chip and the
// disclaimer are always visible, so a computed ratio can never be mistaken for a
// real backtest or a market observation.

import { useMemo, useState } from 'react';
import { MessageSquare, SlidersHorizontal } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { reportResponseTelemetry } from '@/lib/response/telemetry';
import { composeFollowupPrompt, labelsById } from '@/lib/response/followup';
import type { SimulationBlock as SimulationBlockType } from '@/lib/response/contract';
import {
  computeSimulation,
  initialSimulationValues,
  resolveSimulationInputs,
  resolveSimulationOutputs,
  type ResolvedInput,
} from '@/lib/response/simulation';

const DEFAULT_DISCLAIMER =
  'Illustrative hypothetical, excluding fees, slippage and gaps. These figures do not establish strategy profitability.';

const ACCENT_TEXT: Record<string, string> = {
  neutral: 'text-foreground',
  info: 'text-primary',
  success: 'text-emerald-300',
  warning: 'text-amber-300',
  danger: 'text-rose-300',
};

function clamp(n: number, min?: number, max?: number): number {
  let out = n;
  if (min != null) out = Math.max(min, out);
  if (max != null) out = Math.min(max, out);
  return out;
}

function InputField({
  input,
  value,
  onChange,
}: {
  input: ResolvedInput;
  value: number;
  onChange: (next: number) => void;
}) {
  const id = `sim-${input.id}`;
  if (input.kind === 'toggle') {
    return (
      <label htmlFor={id} className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        {input.label}
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
  if (input.kind === 'select') {
    return (
      <label htmlFor={id} className="flex flex-col gap-1.5">
        <span className="text-[11px] text-muted-foreground">{input.label}</span>
        <select
          id={id}
          value={String(value)}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full rounded-lg border border-border/50 bg-background/40 px-2 py-1 text-[12px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          {(input.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const min = input.min ?? 0;
  const max = input.max ?? Math.max(min + 100, value * 2 || 100);
  const step = input.step ?? 0.01;
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between text-[11px] text-muted-foreground">
        {input.label}
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
        aria-label={input.label}
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
        aria-label={`${input.label} value`}
      />
    </label>
  );
}

export function SimulationBlock({
  block,
  onFollowup,
}: {
  block: SimulationBlockType;
  onFollowup?: (prompt: string) => void;
}) {
  const inputs = useMemo(() => resolveSimulationInputs(block), [block]);
  const outputs = useMemo(() => resolveSimulationOutputs(block), [block]);
  const [values, setValues] = useState<Record<string, number>>(() => initialSimulationValues(inputs));

  const computed = useMemo(() => computeSimulation(outputs, values), [outputs, values]);

  const set = (id: string, next: number) => {
    reportResponseTelemetry({ event: 'interaction', blockType: 'simulation' });
    setValues((prev) => ({ ...prev, [id]: next }));
  };

  const explainPrompt = () => {
    const state = Object.fromEntries(inputs.map((input) => [input.id, values[input.id] ?? input.value]));
    const base = composeFollowupPrompt({
      state,
      order: inputs.map((input) => input.id),
      labels: labelsById(inputs),
      lead: 'Explain this configuration',
    });
    const derived = computed.map((c) => `${c.output.label} ${c.display}`).join(', ');
    return derived ? `${base}. Derived: ${derived}.` : `${base}.`;
  };

  return (
    <div className="w-full">
      <div className="glass-card rounded-2xl p-3.5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SlidersHorizontal size={14} className="text-primary/70" />
          <h4 className="text-sm font-semibold text-foreground">{block.title ?? 'Interactive calculator'}</h4>
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-200/90">
            Illustrative
          </span>
        </div>
        {block.description && (
          <p className="mb-3 text-[12px] leading-relaxed text-muted-foreground">{block.description}</p>
        )}

        {inputs.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {inputs.map((input) => (
              <InputField key={input.id} input={input} value={values[input.id] ?? input.value} onChange={(n) => set(input.id, n)} />
            ))}
          </div>
        )}

        {computed.length > 0 && (
          <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {computed.map(({ output, display }) => (
              <div key={output.id} className="glass-card-subtle flex flex-col gap-0.5 rounded-xl px-3 py-2.5">
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
                  {output.label}
                </span>
                <span
                  className={cn('font-mono tabular-nums', ACCENT_TEXT[output.tone ?? 'neutral'])}
                  aria-live="polite"
                >
                  {display}
                </span>
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 text-[10.5px] leading-relaxed text-muted-foreground/70">
          {block.disclaimer ?? DEFAULT_DISCLAIMER}
        </p>
      </div>

      {onFollowup && inputs.length > 0 && (
        <button
          type="button"
          onClick={() => onFollowup(explainPrompt())}
          className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-accent/30 px-3 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
        >
          <MessageSquare size={11} /> Explain this configuration in chat
        </button>
      )}

      {block.caption && <p className="mt-1.5 text-[10px] text-muted-foreground/60">{block.caption}</p>}
    </div>
  );
}
