'use client';

// Data for the Home dashboard's Trading section. Composes the shared broker
// snapshot (15s poll, IPC-aware) with the local journal analytics bundle
// (fetched once — it only changes when trades are logged). Kept out of
// use-home-data so broker failures never blank the market cards.

import { useEffect, useMemo, useState } from 'react';
import { useBrokerSnapshot, type BrokerSnapshotState } from './use-broker-snapshot';
import {
  buildDailyRealized,
  computeExposure,
  computeTodayPnl,
  trimSeries,
  type ExposureSummary,
  type RealizedSeries,
  type TodayPnl,
} from './trading-home-model';
import type { CurrencyEquityPoint, JournalAnalytics } from '@/lib/journal/types';

export interface TradingHomeData extends BrokerSnapshotState {
  todayPnl: TodayPnl;
  exposure: ExposureSummary;
  realized: RealizedSeries;
  journal: JournalAnalytics | null;
  journalCurve: CurrencyEquityPoint[];
  journalLoading: boolean;
}

export function useTradingHomeData(): TradingHomeData {
  const broker = useBrokerSnapshot();
  const [journal, setJournal] = useState<JournalAnalytics | null>(null);
  const [journalLoading, setJournalLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/journal/analytics', { cache: 'no-store' })
      .then((res) => (res.ok ? (res.json() as Promise<{ analytics?: JournalAnalytics }>) : null))
      .then((body) => {
        if (!cancelled) setJournal(body?.analytics ?? null);
      })
      .catch(() => {
        if (!cancelled) setJournal(null);
      })
      .finally(() => {
        if (!cancelled) setJournalLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const todayPnl = useMemo(
    () => computeTodayPnl(broker.fills, broker.account?.profit ?? null),
    [broker.fills, broker.account?.profit],
  );
  const exposure = useMemo(
    () => computeExposure(broker.positions, broker.account),
    [broker.positions, broker.account],
  );
  const realized = useMemo(() => buildDailyRealized(broker.fills), [broker.fills]);
  const journalCurve = useMemo(
    () => trimSeries(journal?.equityCurrency ?? [], 60),
    [journal],
  );

  return { ...broker, todayPnl, exposure, realized, journal, journalCurve, journalLoading };
}
