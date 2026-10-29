'use client';

// ── Spec builder — a no-code view over the same JSON ────────────────────────
// Every control calls a pure editor from `spec-edit.ts` and hands the whole new
// spec back. The JSON stays the source of truth: unknown fields survive, and a
// part the builder cannot represent (an expression operand, or nesting deeper
// than the editor caps) is shown as "advanced" with a pointer to the JSON tab
// instead of being rewritten.

import React from 'react';
import {
  clearStop,
  clearTarget,
  readBasics,
  setCost,
  setIndicatorParam,
  setRisk,
  setSizing,
  setStop,
  setTarget,
} from '@/lib/strategy-studio/spec-edit';
import { RuleTreeEditor } from './rule-tree';
import { cn } from '@/lib/utils';

const INPUT =
  'glass-card-subtle rounded-lg px-2 py-1 font-mono text-[10px] text-foreground outline-none disabled:opacity-50';
const LABEL = 'text-[10px] uppercase tracking-wide text-muted-foreground';

const SIZING_TYPES = [
  'percent_equity',
  'percent_risk',
  'fixed_quantity',
  'fixed_dollar',
  'atr',
  'volatility',
  'fractional_kelly',
  'equal_weight',
];

const STOP_TYPES = ['atr', 'percent', 'fixed'];
const TARGET_TYPES = ['risk_reward', 'percent', 'fixed'];

export function SpecBuilder({
  spec,
  disabled = false,
  onChange,
}: {
  spec: Record<string, unknown>;
  disabled?: boolean;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const basics = readBasics(spec);

  return (
    <div className="flex flex-col gap-3 text-[11px]">
      <section className="rounded-xl border border-white/10 p-2">
        <p className={cn(LABEL, 'mb-1')}>Indicators</p>
        <div className="space-y-1">
          {basics.indicators.length === 0 ? (
            <p className="text-[10px] text-muted-foreground">No indicators declared (edit JSON to add one).</p>
          ) : null}
          {basics.indicators.map((indicator) => (
            <div key={`${indicator.index}-${indicator.id}`} className="flex flex-wrap items-center gap-1.5">
              <span className="min-w-[92px] font-mono text-[10px] text-foreground">{indicator.id}</span>
              <span className="rounded border border-white/10 px-1 font-mono text-[9px] text-muted-foreground">
                {indicator.type}
              </span>
              {indicator.params.length === 0 ? (
                <span className="text-[9px] text-muted-foreground">no numeric params</span>
              ) : null}
              {indicator.params.map((param) => (
                <label key={param.key} className="flex items-center gap-1 text-[9px] text-muted-foreground">
                  {param.key}
                  <input
                    type="number"
                    value={param.value}
                    disabled={disabled}
                    onChange={(event) =>
                      onChange(setIndicatorParam(spec, indicator.index, param.key, Number(event.target.value)))
                    }
                    className={cn(INPUT, 'w-16 text-right')}
                  />
                </label>
              ))}
            </div>
          ))}
        </div>
      </section>

      <RuleTreeEditor
        title="Entry (long)"
        spec={spec}
        groupPath="rules.entry.long"
        disabled={disabled}
        onChange={onChange}
      />
      <RuleTreeEditor
        title="Exit (long)"
        spec={spec}
        groupPath="rules.exit.long"
        disabled={disabled}
        onChange={onChange}
      />

      <section className="rounded-xl border border-white/10 p-2">
        <p className={cn(LABEL, 'mb-1')}>Risk and exits</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Stop type
            <select
              value={basics.stop?.type ?? 'atr'}
              disabled={disabled}
              onChange={(event) => onChange(setStop(spec, basics.stop?.value ?? 2, event.target.value))}
              className={INPUT}
            >
              {STOP_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Stop value
            <input
              type="number"
              step="0.1"
              value={basics.stop?.value ?? 2}
              disabled={disabled}
              onChange={(event) => onChange(setStop(spec, Number(event.target.value), basics.stop?.type ?? 'atr'))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Target type
            <select
              value={basics.target?.type ?? 'risk_reward'}
              disabled={disabled}
              onChange={(event) => onChange(setTarget(spec, basics.target?.value ?? 3, event.target.value))}
              className={INPUT}
            >
              {TARGET_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Target value
            <input
              type="number"
              step="0.1"
              value={basics.target?.value ?? 3}
              disabled={disabled}
              onChange={(event) => onChange(setTarget(spec, Number(event.target.value), basics.target?.type ?? 'risk_reward'))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Sizing
            <select
              value={basics.sizing.type}
              disabled={disabled}
              onChange={(event) => onChange(setSizing(spec, { type: event.target.value }))}
              className={INPUT}
            >
              {SIZING_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Sizing value
            <input
              type="number"
              value={basics.sizing.value}
              disabled={disabled}
              onChange={(event) => onChange(setSizing(spec, { value: Number(event.target.value) }))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Max position %
            <input
              type="number"
              value={basics.risk.maxPositionPct ?? 100}
              disabled={disabled}
              onChange={(event) => onChange(setRisk(spec, { maxPositionPct: Number(event.target.value) }))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Max open
            <input
              type="number"
              value={basics.risk.maxOpenPositions ?? 1}
              disabled={disabled}
              onChange={(event) => onChange(setRisk(spec, { maxOpenPositions: Number(event.target.value) }))}
              className={INPUT}
            />
          </label>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-foreground">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={basics.risk.allowLong}
              disabled={disabled}
              onChange={(event) => onChange(setRisk(spec, { allowLong: event.target.checked }))}
            />
            Long
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={basics.risk.allowShort}
              disabled={disabled}
              onChange={(event) => onChange(setRisk(spec, { allowShort: event.target.checked }))}
            />
            Short
          </label>
          {basics.stop ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(clearStop(spec))}
              className="glass-button rounded-md px-2 py-0.5 text-[10px]"
            >
              Remove stop
            </button>
          ) : (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(setStop(spec, 2))}
              className="glass-button rounded-md px-2 py-0.5 text-[10px]"
            >
              Add stop
            </button>
          )}
          {basics.target ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(clearTarget(spec))}
              className="glass-button rounded-md px-2 py-0.5 text-[10px]"
            >
              Remove target
            </button>
          ) : (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(setTarget(spec, 3))}
              className="glass-button rounded-md px-2 py-0.5 text-[10px]"
            >
              Add target
            </button>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-white/10 p-2">
        <p className={cn(LABEL, 'mb-1')}>Execution costs</p>
        <div className="grid grid-cols-3 gap-2">
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Commission %
            <input
              type="number"
              step="0.01"
              value={basics.costs.commission}
              disabled={disabled}
              onChange={(event) => onChange(setCost(spec, 'commission', Number(event.target.value)))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Slippage %
            <input
              type="number"
              step="0.01"
              value={basics.costs.slippage}
              disabled={disabled}
              onChange={(event) => onChange(setCost(spec, 'slippage', Number(event.target.value)))}
              className={INPUT}
            />
          </label>
          <label className="flex flex-col gap-0.5 text-[9px] text-muted-foreground">
            Spread bps
            <input
              type="number"
              step="0.1"
              value={basics.costs.spread}
              disabled={disabled}
              onChange={(event) => onChange(setCost(spec, 'spread', Number(event.target.value)))}
              className={INPUT}
            />
          </label>
        </div>
      </section>
    </div>
  );
}
