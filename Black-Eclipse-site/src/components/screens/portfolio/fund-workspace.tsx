'use client';

// ── Per-fund workspace — kernel-driven customizable widget grid ──────────────

import React, { useMemo, useState } from 'react';
import {
  ArrowLeft, Settings2, Plus, RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { fmtPct, fmtUsd } from '@/lib/portfolio-analysis';
import { useWorkspace } from '@/lib/workspace/use-workspace';
import { WorkspaceCanvas } from '@/lib/workspace/workspace-canvas';
import { DotGrid } from '@/components/ui/ascii-loader';
import { useFundData } from './use-fund-data';
import { FUND_WIDGETS, defaultFundLayout, renderFundWidget } from './widgets';
import { AddTransactionDialog } from './fund-dialogs';
import type { Fund, Transaction } from '@/lib/portfolio/types';

interface FundWorkspaceProps {
  fund: Fund;
  onBack: () => void;
  onUpdateFund: (patch: Partial<Omit<Fund, 'id' | 'seeded'>>) => void;
}

const wsKeyFor = (fundId: string) => `be_ws_fund_${fundId}_v2`;

export function FundWorkspace({ fund, onBack, onUpdateFund }: FundWorkspaceProps) {
  const defaultLayout = useMemo(() => defaultFundLayout(), []);
  const workspace = useWorkspace({
    storageKey: wsKeyFor(fund.id),
    defaultLayout,
    knownWidgetIds: FUND_WIDGETS.map(w => w.widgetId),
  });
  const [taxMethod, setTaxMethod] = useState<'FIFO' | 'LIFO'>('FIFO');
  const [addTxOpen, setAddTxOpen] = useState(false);
  const data = useFundData(fund, taxMethod);
  const s = data.stats;
  const loading = data.loading && !data.ready;

  return (
    <div className="animate-fade-in-up w-full">
      {/* Top bar */}
      <div className="mb-5 flex flex-wrap items-center gap-3 border-b border-border/10 pb-4">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-border/40 hover:border-primary/40 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer"
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
        {loading && (
          <span className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground/70" role="status" aria-label="Loading fund data">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" aria-hidden />
            <span className="font-bold">loading prices</span>
          </span>
        )}

        {/* Key stats ribbon */}
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2">
            <StatChip label="Value" value={fmtUsd(s.totalValue)} />
            <StatChip label="Unreal. P/L" value={fmtUsd(s.unrealizedPnL)} tone={s.unrealizedPnL} sub={fmtPct(s.roiPercent)} />
            <StatChip label="Day" value={fmtUsd(s.dailyChangeValue)} tone={s.dailyChangeValue} />
            {/* Display/accounting switch — FIFO vs LIFO cost basis */}
            <button
              onClick={() => setTaxMethod(m => (m === 'FIFO' ? 'LIFO' : 'FIFO'))}
              title="Toggle cost-basis accounting"
              className="rounded-xl border border-border/40 bg-accent/30 hover:border-primary/40 hover:text-primary px-2.5 py-1.5 text-[10px] font-bold text-muted-foreground transition-all cursor-pointer"
            >
              <RefreshCw size={10} className="inline mr-1" />{taxMethod}
            </button>
          </div>
          <button
            onClick={() => workspace.setEditMode(!workspace.editMode)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
              workspace.editMode
                ? 'border-primary/40 bg-primary/15 text-primary'
                : 'border-border/40 bg-accent/30 text-muted-foreground hover:text-primary hover:border-primary/40',
            )}
          >
            <Settings2 size={13} /> Customize
          </button>
          <button
            onClick={() => setAddTxOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
          >
            <Plus size={13} /> Transaction
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-3xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-12 flex flex-col items-center gap-3 animate-fade-in">
          <DotGrid size={28} />
          <span className="text-xs text-muted-foreground font-mono">loading live prices…</span>
        </div>
      ) : (
        <WorkspaceCanvas
          workspace={workspace}
          widgets={FUND_WIDGETS}
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

function StatChip({ label, value, tone, sub }: { label: string; value: string; tone?: number; sub?: string }) {
  return (
    <div className="rounded-xl border border-border/20 bg-accent/20 backdrop-blur-md px-2.5 py-1 min-w-0">
      <p className="text-[8px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      <p className={cn('font-mono text-xs font-bold truncate',
        tone == null ? 'text-foreground' : tone > 0 ? 'text-emerald-400' : tone < 0 ? 'text-rose-400' : 'text-muted-foreground')}>
        {value}{sub ? ` · ${sub}` : ''}
      </p>
    </div>
  );
}
