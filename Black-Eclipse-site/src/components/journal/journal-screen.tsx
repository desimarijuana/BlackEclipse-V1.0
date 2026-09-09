'use client';

// ── JournalScreen — the Journal tab shell ─────────────────────────────────────
// Hosts the sub-tab navigation (Overview / Calendar / Trades / Analytics /
// Playbook / Reviews / Insights) and loads the shared analytics bundle once,
// passing it down to each sub-screen. Keeps the analytics fetch in one place
// so sub-screens stay pure and fast.

import React, { useCallback, useEffect, useState } from 'react';
import { BookOpen, Brain, CalendarDays, LayoutDashboard, LineChart, ListChecks, MessageSquareText, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
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

export type JournalTab = 'overview' | 'calendar' | 'trades' | 'analytics' | 'psychology' | 'playbook' | 'reviews' | 'insights';

const TABS: { id: JournalTab; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'calendar', label: 'Calendar', icon: CalendarDays },
  { id: 'trades', label: 'Trades', icon: ListChecks },
  { id: 'analytics', label: 'Analytics', icon: LineChart },
  { id: 'psychology', label: 'Psychology', icon: Brain },
  { id: 'playbook', label: 'Playbook', icon: BookOpen },
  { id: 'reviews', label: 'Reviews', icon: MessageSquareText },
  { id: 'insights', label: 'Insights', icon: Sparkles },
];

export function JournalScreen() {
  const [tab, setTab] = useState<JournalTab>('overview');
  const [analytics, setAnalytics] = useState<JournalAnalytics | null>(null);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [dailyOpen, setDailyOpen] = useState(false);

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

  return (
    <div className="animate-fade-in-up w-full">
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <BookOpen className="text-primary" size={22} />
        </div>
        <div className="min-w-0">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Trading Journal</h1>
          <p className="text-muted-foreground text-xs mt-0.5">Every trade becomes data. Every day becomes behavioral data.</p>
        </div>
      </div>

      {/* Sub-tab navigation */}
      <div className="mb-5 flex items-center gap-1 overflow-x-auto scrollbar-hide rounded-2xl bg-[#0f0f0f]/60 p-1 backdrop-blur-xl">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer',
                active ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-accent/40',
              )}
            >
              <Icon size={13} />
              {t.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="mb-4 rounded-2xl border border-rose-500/20 bg-rose-500/5 p-3.5 text-xs text-rose-400 font-semibold">
          {error}
        </div>
      )}

      {loading && !analytics ? (
        <div className="rounded-3xl bg-[#0f0f0f]/60 p-12 flex flex-col items-center gap-3">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
          <span className="text-xs text-muted-foreground font-mono">loading journal…</span>
        </div>
      ) : (
        <div className="w-full">
          {dailyOpen && selectedDate ? (
            <DailyJournal date={selectedDate} onBack={() => setDailyOpen(false)} />
          ) : (
            <>
              {tab === 'overview' && <JournalOverview analytics={analytics} trades={trades} onOpenTrades={() => setTab('trades')} onOpenCalendar={(d) => { if (d) { setSelectedDate(d); setDailyOpen(true); } else setTab('calendar'); }} />}
              {tab === 'calendar' && <JournalCalendar trades={trades} onSelectDay={(d) => { setSelectedDate(d); setDailyOpen(true); }} onChanged={refresh} />}
              {tab === 'trades' && <JournalTrades trades={trades} analytics={analytics} onChanged={refresh} selectedDate={selectedDate} />}
              {tab === 'analytics' && <JournalAnalyticsView analytics={analytics} trades={trades} />}
              {tab === 'psychology' && <JournalPsychology analytics={analytics} trades={trades} />}
              {tab === 'playbook' && <JournalPlaybook />}
              {tab === 'reviews' && <JournalReviews />}
              {tab === 'insights' && <JournalInsights analytics={analytics} />}
            </>
          )}
        </div>
      )}
    </div>
  );
}
