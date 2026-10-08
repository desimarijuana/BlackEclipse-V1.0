'use client';

// ── Portfolio screen — fund manager ⇄ per-fund workspace ─────────────────────

import React, { useCallback, useEffect, useState } from 'react';
import { ChartPie } from '@/lib/icons';
import { loadFunds, saveFunds } from './fund-store';
import { FundManager } from './fund-manager';
import { FundWorkspace } from './fund-workspace';
import { PortfolioLedger } from './portfolio-ledger';
import { useCommandStore } from '@/lib/search/store';
import type { Fund } from '@/lib/portfolio/types';

export function PortfolioScreen() {
  const [funds, setFunds] = useState<Fund[] | null>(null);
  const [openFundId, setOpenFundId] = useState<string | null>(null);
  const [view, setView] = useState<'funds' | 'ledger'>('funds');

  useEffect(() => {
    setFunds(loadFunds().funds);
  }, []);

  // Consume a fund id dispatched by the global search bar (⌘K → fund result).
  // Subscribes so it works even when the tab is already mounted (keep-alive).
  useEffect(() => {
    const check = () => {
      const id = useCommandStore.getState().consumeFundId();
      if (id) setOpenFundId(id);
    };
    check();
    const unsub = useCommandStore.subscribe((state, prev) => {
      if (state.pendingFundId !== prev.pendingFundId && state.pendingFundId) check();
    });
    return unsub;
  }, []);

  const updateFund = useCallback((fundId: string, patch: Partial<Omit<Fund, 'id' | 'seeded'>>) => {
    setFunds(prev => {
      if (!prev) return prev;
      const next = prev.map(f => (f.id === fundId ? { ...f, ...patch } : f));
      saveFunds(next);
      return next;
    });
  }, []);

  const openFund = funds?.find(f => f.id === openFundId) ?? null;

  return (
    <div className="relative flex h-full w-full flex-col">
      <div className="absolute right-3 top-3 z-20 flex overflow-hidden rounded-full glass-card-subtle text-xs">
        <button
          className={view === 'funds' ? 'px-3 py-1 bg-white/10' : 'px-3 py-1'}
          onClick={() => setView('funds')}
        >
          Funds
        </button>
        <button
          className={view === 'ledger' ? 'px-3 py-1 bg-white/10' : 'px-3 py-1'}
          onClick={() => setView('ledger')}
        >
          Ledger
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {view === 'ledger' ? (
          <PortfolioLedger />
        ) : openFund ? (
          <FundWorkspace
            key={openFund.id}
            fund={openFund}
            onBack={() => setOpenFundId(null)}
            onUpdateFund={(patch) => updateFund(openFund.id, patch)}
          />
        ) : (
          <FundManager onOpenFund={setOpenFundId} />
        )}
      </div>
    </div>
  );
}

export { ChartPie as PortfolioTabIcon };
