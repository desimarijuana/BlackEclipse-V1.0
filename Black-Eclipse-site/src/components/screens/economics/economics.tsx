'use client';

import React, { useState } from 'react';
import { Globe } from 'lucide-react';
import { ECON_SOURCES } from '@/lib/economics/sources';
import { EconPanel } from './panel';
import { SnapshotView } from './snapshot';
import { CalendarView } from './calendar';

type View = 'snapshot' | 'explorer' | 'calendar';

const VIEWS: { id: View; label: string }[] = [
  { id: 'snapshot', label: 'Snapshot' },
  { id: 'explorer', label: 'Explorer' },
  { id: 'calendar', label: 'Calendar' },
];

export function EconomicsScreen() {
  const [view, setView] = useState<View>('snapshot');
  const [activeSource, setActiveSource] = useState(ECON_SOURCES[0].id);

  return (
    <div className="w-full max-w-7xl mx-auto px-4 md:px-8 py-8 h-full overflow-y-auto pb-20 select-none">
      <div className="animate-fade-in-up flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border/10 pb-3">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <Globe className="text-primary" size={30} />
          </div>
          <div>
            <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Economics</h1>
            <p className="text-muted-foreground text-xs mt-0.5">Global macro intelligence — 30+ statistical agencies, central-bank rates, releases calendar and AI research.</p>
          </div>
        </div>

        {/* Source badge bar */}
        <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1 -mb-1">
          {ECON_SOURCES.map((s) => {
            const active = s.id === activeSource && view === 'explorer';
            return (
              <button
                key={s.id}
                onClick={() => { setActiveSource(s.id); setView('explorer'); }}
                title={s.description || s.label}
                className={`h-8 px-3 shrink-0 rounded-lg text-[11px] font-bold whitespace-nowrap border cursor-pointer transition-all ${
                  active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground border-border/30 bg-accent/20 hover:bg-accent/50'
                }`}
                style={active ? { background: `${s.color}22`, borderColor: `${s.color}66`, color: s.color } : undefined}
              >
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle"
                  style={{ background: s.color, boxShadow: active ? `0 0 6px ${s.color}` : undefined }}
                />
                {s.label}
                {s.keyRequired && <span className="ml-1 text-[8px] opacity-60">KEY</span>}
              </button>
            );
          })}
        </div>

        {/* View switcher */}
        <div className="flex items-center gap-1 p-1 rounded-xl bg-accent/20 border border-border/20 w-fit">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`h-8 px-4 rounded-lg text-[12px] font-bold cursor-pointer transition-all ${
                view === v.id ? 'bg-primary/15 text-primary border border-primary/25' : 'text-muted-foreground hover:text-foreground border border-transparent'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* Views */}
        {view === 'snapshot' && <SnapshotView />}
        {view === 'explorer' && (
          <EconPanel key={activeSource} source={ECON_SOURCES.find((s) => s.id === activeSource) ?? ECON_SOURCES[0]} />
        )}
        {view === 'calendar' && <CalendarView />}
      </div>
    </div>
  );
}