'use client';

// ── AI / Agent widgets — real agent state from JDDS ───────────────────────────
// Shows actual ResearchReport / AgentRun / ResearchFinding rows. Never
// fabricates execution — only surfaces what really ran.

import React from 'react';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';

interface Report { id: string; query: string; ticker: string | null; status: string; verdict: string | null; confidence: number | null; createdAt: string; }
interface Run { id: string; agent: string; status: string; toolCalls: number; toolErrors: number; startedAt: string; }
interface Finding { id: string; agent: string; kind: string; ticker: string | null; title: string; createdAt: string; }
interface Activity { reports: Report[]; runs: Run[]; findings: Finding[]; activeRuns: number; runningReports: number; totalReports: number; }

function WidgetHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs text-muted-foreground/70 italic">{children}</p>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  running: 'text-sky-400',
  done: 'text-emerald-400',
  failed: 'text-rose-400',
};

// ── Agent Activity ────────────────────────────────────────────────────────────

export function AgentActivityWidget() {
  const t = useTopic<Activity>('agent:activity');
  const runs = t.data?.runs ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Agent Activity" hint={`${t.data?.activeRuns ?? 0} RUNNING`} />
      {runs.length === 0 ? <EmptyNote>No agent runs yet — ask the Eclipse Agent to research something.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {runs.slice(0, 8).map(r => (
            <div key={r.id} className="flex items-center justify-between text-[10px] py-0.5">
              <span className="font-mono font-bold text-foreground capitalize">{r.agent}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-muted-foreground">{r.toolCalls} calls</span>
                {r.toolErrors > 0 && <span className="font-mono text-rose-400">{r.toolErrors} err</span>}
                <span className={cn('font-mono capitalize', STATUS_TONE[r.status] ?? 'text-muted-foreground')}>{r.status}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Recent Research ─────────────────────────────────────────────────────────

export function RecentResearchWidget() {
  const t = useTopic<Activity>('agent:activity');
  const reports = t.data?.reports ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Recent Research" hint={`${t.data?.totalReports ?? 0}`} />
      {reports.length === 0 ? <EmptyNote>No research reports yet.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {reports.slice(0, 8).map(r => (
            <div key={r.id} className="rounded-lg border border-border/10 glass-card-subtle px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-foreground truncate">{r.query}</span>
                <span className={cn('font-mono text-[9px] capitalize shrink-0', STATUS_TONE[r.status] ?? 'text-muted-foreground')}>{r.status}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[9px] text-muted-foreground">
                {r.ticker && <span className="font-mono text-primary">{r.ticker}</span>}
                {r.verdict && <span className="font-mono capitalize">{r.verdict}</span>}
                {r.confidence != null && <span className="font-mono">{Math.round(r.confidence * 100)}%</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AI Insights (findings feed) ────────────────────────────────────────────

export function AIInsightsWidget() {
  const t = useTopic<Activity>('agent:activity');
  const findings = t.data?.findings ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="AI Insights" hint="FINDINGS" />
      {findings.length === 0 ? <EmptyNote>No agent findings yet.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {findings.slice(0, 8).map(f => (
            <div key={f.id} className="flex items-start gap-2 text-[10px] py-0.5">
              <span className="font-mono text-primary shrink-0">{f.ticker ?? f.agent}</span>
              <span className="text-muted-foreground leading-snug">{f.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
