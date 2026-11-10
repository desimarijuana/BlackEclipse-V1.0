'use client';

// ── The Quant Figure Kit on the Backtest bench ──────────────────────────────
//
// The chat is not the only place a quant result should be readable. This panel
// reuses the SAME figure kit (the Python visuals module) and the SAME chat chart
// surface (ResponseChart), so the two screens cannot drift: every figure is
// built from the stored experiment by the quant engine, never by ECharts code
// that computes its own values in the browser.

import { useMemo, useState } from 'react';
import { ResponseChart } from '@/components/response/response-chart';
import type { ChartBlock } from '@/lib/response/contract';

type Preset = 'core' | 'risk' | 'robustness';

const PRESETS: Array<{ id: Preset; label: string }> = [
  { id: 'core', label: 'Core' },
  { id: 'risk', label: 'Risk' },
  { id: 'robustness', label: 'Robustness' },
];

const FIGURES: Record<Exclude<Preset, 'robustness'>, string[]> = {
  core: ['equity', 'underwater', 'monthly_returns', 'trade_distribution'],
  risk: ['exposure', 'rolling_risk', 'cost_waterfall'],
};

export interface QuantFigurePanelProps {
  experimentId: string;
  monteCarloExperimentId?: string;
  className?: string;
}

export function QuantFigurePanel({
  experimentId,
  monteCarloExperimentId,
  className,
}: QuantFigurePanelProps) {
  const [preset, setPreset] = useState<Preset>('core');

  const blocks = useMemo(() => {
    if (!experimentId) return [] as ChartBlock[];
    const names = preset === 'robustness'
      ? (monteCarloExperimentId ? ['montecarlo', 'regime_attribution'] : [])
      : FIGURES[preset];
    return names.map((figure) => {
      const source = preset === 'robustness' ? monteCarloExperimentId! : experimentId;
      return {
        type: 'chart',
        chartType: 'auto',
        title: figure.replaceAll('_', ' '),
        quant: { experimentId: source, figure },
      } as ChartBlock;
    });
  }, [experimentId, monteCarloExperimentId, preset]);

  return (
    <section className={className}>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-xs font-semibold text-foreground">Quant figures</h3>
        <span className="font-mono text-[10px] text-muted-foreground">
          computed from the stored artifact
        </span>
        <div className="ml-auto flex gap-1">
          {PRESETS.map((item) => {
            const disabled = item.id === 'robustness' && !monteCarloExperimentId;
            return (
              <button
                key={item.id}
                type="button"
                disabled={disabled}
                onClick={() => setPreset(item.id)}
                className={`rounded-lg px-2 py-1 text-[10px] transition-colors disabled:opacity-40 ${
                  preset === item.id
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:bg-accent'
                }`}
                title={disabled ? 'Choose a Monte-Carlo run to see robustness figures' : undefined}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
      {blocks.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          Choose a stored experiment{monteCarloExperimentId ? '' : ' and a Monte-Carlo'} to see figures.
        </p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {blocks.map((block) => (
            <div key={`${block.quant?.experimentId}:${block.quant?.figure}`} className="glass-card-subtle rounded-xl p-2">
              <ResponseChart block={block} height={230} focusable={false} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
