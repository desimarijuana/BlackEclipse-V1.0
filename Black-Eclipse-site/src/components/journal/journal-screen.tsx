'use client';

// ── JournalScreen — the Journal tab shell ─────────────────────────────────────
// Hosts the sub-tab navigation (Overview / Calendar / Trades / Analytics /
// Playbook / Reviews / Insights) and loads the shared analytics bundle once,
// passing it down to each sub-screen. Keeps the analytics fetch in one place
// so sub-screens stay pure and fast.

import React, { useCallback, useEffect, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { BookOpen, Brain, CalendarDays, LayoutDashboard, LineChart, ListChecks, MessageSquareText, Sparkles, StickyNote } from '@/lib/icons';
import { TabBar } from '@/components/ui/tab-bar';
import { useSubroute } from '@/hooks/use-subroute';
import type { JournalAnalytics, TradeRecord } from '@/lib/journal/types';
import { JournalOverview } from './overview';
import { JournalCalendar } from './calendar';
import { JournalTrades } from './trades';
import { JournalAnalyticsView } from './analytics-view';
import { JournalPsychology } from './psychology';
import { JournalPlaybook } from './playbook';
import { JournalReviews } from './reviews';
import { JournalInsights } from './insights';
import { DailyJournal } from './daily-journal';
import { DemoDataBanner } from './demo-banner';
import { QuickAddTrade } from './quick-add-trade';
import { JournalSettings } from './journal-settings';
import { JournalNotebook } from './notebook';

export type JournalTab = 'overview' | 'calendar' | 'trades' | 'analytics' | 'psychology' | 'playbook' | 'reviews' | 'insights' | 'notebook';

const TABS: { id: JournalTab; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'calendar', label: 'Calendar', icon: CalendarDays },
  { id: 'trades', label: 'Trades', icon: ListChecks },
  { id: 'analytics', label: 'Analytics', icon: LineChart },
  { id: 'psychology', label: 'Psychology', icon: Brain },
  { id: 'playbook', label: 'Playbook', icon: BookOpen },
  { id: 'reviews', label: 'Reviews', icon: MessageSquareText },
  { id: 'insights', label: 'Insights', icon: Sparkles },
  { id: 'notebook', label: 'Notebook', icon: StickyNote },
];

export function JournalScreen() {
  const [tab, setTab] = useState<JournalTab>('overview');
  const [analytics, setAnalytics] = useState<JournalAnalytics | null>(null);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [dailyOpen, setDailyOpen] = useState(false);
  const [quickAddOpen, setQuickAddOpen] = useState(false);

  // Global search: 'journal.<tab>' sub-pages (e.g. 'journal.analytics').
  useSubroute('journal', (req) => {
    const target = req.subroute as JournalTab;
    if (TABS.some((t) => t.id === target)) setTab(target);
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [aRes, tRes] = await Promise.all([
        fetch('/api/journal/analytics'),
        fetch('/api/journal/trades'),
      ]);
      const aData = await aRes.json();
      const tData = await tRes.json();
      if (aData.error) throw new Error(aData.error);
      setAnalytics(aData.analytics);
      setTrades(tData.trades ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load journal');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(() => {
    void load();
  }, [load]);

  const rootRef = useRef<HTMLDivElement>(null);
  const selectTab = useCallback((index: number) => {
    const target = TABS[index];
    if (target) setTab(target.id);
  }, []);
  usePageShortcuts(rootRef, [
    { id: 'journal.refresh', label: 'Refresh journal', keys: 'R', run: refresh, enabled: !loading && !dailyOpen },
    { id: 'journal.new-trade', label: 'Add trade', keys: 'Shift+N', run: () => setQuickAddOpen(true), enabled: !dailyOpen && !quickAddOpen },
    ...TABS.slice(0, 9).map((t, i) => ({
      id: `journal.tab.${t.id}`,
      label: t.label,
      keys: `Alt+${i + 1}`,
      run: () => setTab(t.id),
      enabled: !dailyOpen,
    })),
    { id: 'journal.tab.last', label: TABS[TABS.length - 1].label, keys: 'Alt+0', run: () => selectTab(TABS.length - 1), enabled: !dailyOpen },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Trading journal" className="animate-fade-in-up w-full">
      {/* Header — the Add-Trade action lives here so it is reachable from every
          sub-tab, not just Trades/Calendar. */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <BookOpen className="text-primary" size={22} />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Trading Journal</h1>
          <p className="text-muted-foreground text-xs mt-0.5">Every trade becomes data. Every day becomes behavioral data.</p>
        </div>
        {!dailyOpen && (
          <div className="flex items-center gap-2">
            <JournalSettings onChanged={refresh} />
            <QuickAddTrade
              onAdded={refresh}
              defaultDate={selectedDate ?? undefined}
              open={quickAddOpen}
              onOpenChange={setQuickAddOpen}
            />
          </div>
        )}
      </div>

      {/* Sub-tab navigation */}
      <TabBar
        items={TABS.map((t) => ({ id: t.id, label: t.label, icon: t.icon }))}
        activeId={tab}
        onChange={(id) => setTab(id as JournalTab)}
      />

      {error && (
        <div className="mb-4 rounded-2xl border border-rose-500/20 bg-rose-500/5 p-3.5 text-xs text-rose-400 font-semibold">
          {error}
        </div>
      )}

      <DemoDataBanner onChanged={refresh} />

      {loading && !analytics ? (
        <div className="rounded-3xl glass-card p-12 flex flex-col items-center gap-3">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
          <span className="text-xs text-muted-foreground font-mono">loading journal…</span>
        </div>
      ) : (
        <div className="w-full">
          {dailyOpen && selectedDate ? (
            <DailyJournal date={selectedDate} onBack={() => setDailyOpen(false)} />
          ) : (
            <>
              {tab === 'overview' && <JournalOverview analytics={analytics} trades={trades} onOpenTrades={() => setTab('trades')} onAddTrade={() => setQuickAddOpen(true)} onOpenCalendar={(d) => { if (d) { setSelectedDate(d); setDailyOpen(true); } else setTab('calendar'); }} />}
              {tab === 'calendar' && <JournalCalendar trades={trades} onSelectDay={(d) => { setSelectedDate(d); setDailyOpen(true); }} onChanged={refresh} />}
              {tab === 'trades' && <JournalTrades trades={trades} analytics={analytics} onChanged={refresh} selectedDate={selectedDate} />}
              {tab === 'analytics' && <JournalAnalyticsView analytics={analytics} trades={trades} />}
              {tab === 'psychology' && <JournalPsychology analytics={analytics} trades={trades} />}
              {tab === 'playbook' && <JournalPlaybook />}
              {tab === 'reviews' && <JournalReviews />}
              {tab === 'insights' && <JournalInsights analytics={analytics} />}
              {tab === 'notebook' && <JournalNotebook />}
            </>
          )}
        </div>
      )}
    </div>
  );
}
