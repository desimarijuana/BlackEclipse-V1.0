'use client';

// ── Per-fund workspace — kernel-driven customizable widget grid ──────────────

import React, { useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import {
  ArrowLeft, Plus, RefreshCw,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { fmtPct, fmtUsd } from '@/lib/portfolio-analysis';
import { CustomizableWorkspace } from '@/components/workspace/customizable-workspace';
import { DotGrid } from '@/components/ui/ascii-loader';
import { useFundData } from './use-fund-data';
import { FUND_WIDGETS, defaultFundLayout, renderFundWidget, fundWidgetIcon } from './widgets';
import { AddTransactionDialog } from './fund-dialogs';
import type { Fund, Transaction } from '@/lib/portfolio/types';

interface FundWorkspaceProps {
  fund: Fund;
  onBack: () => void;
  onUpdateFund: (patch: Partial<Omit<Fund, 'id' | 'seeded'>>) => void;
}

// v3 is a deliberate reset into the track-board grammar (v2 stored the retired
// row-band arrangement, which was gappy). Old payloads are left untouched.
const wsKeyFor = (fundId: string) => `be_ws_fund_${fundId}_v3`;

export function FundWorkspace({ fund, onBack, onUpdateFund }: FundWorkspaceProps) {
  const defaultLayout = useMemo(() => defaultFundLayout(), []);
  const [taxMethod, setTaxMethod] = useState<'FIFO' | 'LIFO'>('FIFO');
  const [addTxOpen, setAddTxOpen] = useState(false);
  const data = useFundData(fund, taxMethod);
  const s = data.stats;
  const loading = data.loading && !data.ready;

  const rootRef = useRef<HTMLDivElement>(null);
  usePageShortcuts(rootRef, [
    { id: 'fund.transaction', label: 'Add transaction', keys: 'Shift+N', run: () => setAddTxOpen(true), enabled: !addTxOpen },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Fund portfolio" className="animate-fade-in-up w-full">
      {/* Top bar — frosted glass */}
      <div className="glass-card mb-5 flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <button
          onClick={onBack}
          className="glass-button inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary rounded-xl px-3 py-1.5 transition-all cursor-pointer"
        >
          <ArrowLeft size={13} /> All Funds
        </button>
        <span className="h-6 w-1 rounded-full shrink-0" style={{ background: fund.accent }} />
        <div className="min-w-0">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground truncate">{fund.name}</h1>
          <p className="text-[10px] text-muted-foreground font-mono">
            {s.holdings.length} holdings · cost {fmtUsd(s.costBasis)}
          </p>
        </div>

        {/* Key stats ribbon */}
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2">
            <StatChip label="Value" value={fmtUsd(s.totalValue)} loading={loading} />
            <StatChip label="Unreal. P/L" value={fmtUsd(s.unrealizedPnL)} tone={s.unrealizedPnL} sub={fmtPct(s.roiPercent)} loading={loading} />
            <StatChip label="Day" value={fmtUsd(s.dailyChangeValue)} tone={s.dailyChangeValue} loading={loading} />
            {/* Display/accounting switch — FIFO vs LIFO cost basis */}
            <button
              onClick={() => setTaxMethod(m => (m === 'FIFO' ? 'LIFO' : 'FIFO'))}
              title="Toggle cost-basis accounting"
              className="glass-button rounded-xl px-2.5 py-1.5 text-[10px] font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            >
              <RefreshCw size={10} className="inline mr-1" />{taxMethod}
            </button>
          </div>
          <button
            onClick={() => setAddTxOpen(true)}
            className="glass-button-add inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
          >
            <Plus size={13} /> Transaction
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-3xl glass-card p-12 flex flex-col items-center gap-3 animate-fade-in">
          <DotGrid size={28} />
          <span className="text-xs text-muted-foreground font-mono">loading live prices…</span>
        </div>
      ) : (
        <CustomizableWorkspace
          storageKey={wsKeyFor(fund.id)}
          defaultLayout={defaultLayout}
          widgets={FUND_WIDGETS}
          widgetIcon={fundWidgetIcon}
          renderWidget={(widgetId) => renderFundWidget(widgetId, { fund, data })}
        />
      )}

      {addTxOpen && (
        <AddTransactionDialog
          onClose={() => setAddTxOpen(false)}
          onAdd={(tx: Transaction) => {
            onUpdateFund({ transactions: [...fund.transactions, tx] });
            setAddTxOpen(false);
          }}
        />
      )}
    </div>
  );
}

function StatChip({ label, value, tone, sub, loading }: { label: string; value: string; tone?: number; sub?: string; loading?: boolean }) {
  return (
    <div className="rounded-xl glass-card-subtle px-2.5 py-1 min-w-0">
      <p className="text-[8px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      {loading ? (
        <span className="mt-0.5 block h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" aria-hidden />
      ) : (
        <p className={cn('font-mono text-xs font-bold truncate',
          tone == null ? 'text-foreground' : tone > 0 ? 'text-emerald-400' : tone < 0 ? 'text-rose-400' : 'text-muted-foreground')}>
          {value}{sub ? ` · ${sub}` : ''}
        </p>
      )}
    </div>
  );
}
