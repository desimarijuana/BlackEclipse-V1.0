'use client';

// ── Portfolio screen — fund manager ⇄ per-fund workspace ─────────────────────

import React, { useCallback, useEffect, useState } from 'react';
import { Briefcase } from 'lucide-react';
import { loadFunds, saveFunds } from './fund-store';
import { FundManager } from './fund-manager';
import { FundWorkspace } from './fund-workspace';
import type { Fund } from '@/lib/portfolio/types';

export function PortfolioScreen() {
  const [funds, setFunds] = useState<Fund[] | null>(null);
  const [openFundId, setOpenFundId] = useState<string | null>(null);

  useEffect(() => {
    setFunds(loadFunds().funds);
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

  return openFund ? (
    <FundWorkspace
      key={openFund.id}
      fund={openFund}
      onBack={() => setOpenFundId(null)}
      onUpdateFund={(patch) => updateFund(openFund.id, patch)}
    />
  ) : (
    <FundManager onOpenFund={setOpenFundId} />
  );
}

export { Briefcase as PortfolioTabIcon };
