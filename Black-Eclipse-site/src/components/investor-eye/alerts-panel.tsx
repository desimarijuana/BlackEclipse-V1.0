'use client';

// ── Investor Eye — Alert Rules panel ─────────────────────────────────────────
// Lets the operator express "tell me when…" over the world-event feed. Rules are
// evaluated server-side against the same cached world state the map reads, and
// every fired rule shows WHY it fired (the matched reasons), so an alert is
// never an unexplained badge.
//
// Reuses the existing settings/alerts conventions: persisted as SystemConfig
// JSON, mutated through a guarded POST/DELETE.

import { useCallback, useEffect, useState } from 'react';
import { Bell, Plus, Trash2, Loader2, ChevronDown, ChevronRight } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { EventAlertRule, RuleMatch } from '@/lib/investor-eye/alert-rules';
import { RULE_PRESETS, ALERT_SEVERITIES } from '@/lib/investor-eye/alert-rules';
import type { NormalizedEvent } from '@/lib/investor-eye/types';

interface AlertsResponse {
  rules?: EventAlertRule[];
  evaluation?: { matches: RuleMatch[]; triggeredRuleIds: string[]; evaluated: number } | null;
  events?: NormalizedEvent[];
}

export function AlertsPanel() {
  const [rules, setRules] = useState<EventAlertRule[]>([]);
  const [evaluation, setEvaluation] = useState<AlertsResponse['evaluation']>(null);
  const [events, setEvents] = useState<NormalizedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [showPresets, setShowPresets] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/investor-eye/alerts?evaluate=1&hours=24');
      const json = (await res.json()) as AlertsResponse;
      setRules(json.rules ?? []);
      setEvaluation(json.evaluation ?? null);
      setEvents(json.events ?? []);
    } catch {
      setRules([]);
      setEvaluation(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const addRule = useCallback(async (draft: Partial<EventAlertRule>) => {
    setBusy(true);
    try {
      const res = await fetch('/api/investor-eye/alerts', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ rule: { ...draft, id: undefined } }),
      });
      const json = (await res.json()) as AlertsResponse;
      if (json.rules) setRules(json.rules);
      setShowPresets(false);
      await load();
    } finally {
      setBusy(false);
    }
  }, [load]);

  const removeRule = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const res = await fetch(`/api/investor-eye/alerts?id=${encodeURIComponent(id)}`, { method: 'DELETE' });
      const json = (await res.json()) as AlertsResponse;
      if (json.rules) setRules(json.rules);
      await load();
    } finally {
      setBusy(false);
    }
  }, [load]);

  const eventById = new Map(events.map((e) => [e.id ?? e.dedupKey, e]));
  const matchCount = evaluation?.matches.length ?? 0;

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          {open ? <ChevronDown size={12} className="text-muted-foreground" /> : <ChevronRight size={12} className="text-muted-foreground" />}
          <Bell size={12} className={cn(matchCount > 0 ? 'text-amber-400' : 'text-muted-foreground')} />
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Alerts</span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[9px]">
          {loading && <Loader2 size={11} className="animate-spin text-muted-foreground" />}
          <span className={cn(matchCount > 0 ? 'text-amber-300' : 'text-muted-foreground/70')}>
            {rules.length} rules{matchCount > 0 ? ` · ${matchCount} firing` : ''}
          </span>
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-border/10 px-3 py-2">
          {matchCount === 0 && rules.length > 0 && !loading && (
            <div className="text-[10px] italic text-muted-foreground/70">
              No rule is firing in the current 24h window.
            </div>
          )}

          {evaluation && matchCount > 0 && (
            <div className="space-y-1.5">
              {evaluation.matches.slice(0, 12).map((m, i) => {
                const rule = rules.find((r) => r.id === m.ruleId);
                const ev = eventById.get(m.eventId);
                return (
                  <div key={`${m.ruleId}-${m.eventId}-${i}`} className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2 py-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold text-amber-200">{rule?.name ?? 'Rule'}</span>
                      {m.distanceKm !== undefined && (
                        <span className="font-mono text-[9px] text-muted-foreground">{m.distanceKm} km</span>
                      )}
                    </div>
                    {ev && <div className="mt-0.5 truncate text-[10px] text-foreground">{ev.title}</div>}
                    <div className="mt-0.5 text-[9px] text-muted-foreground/80">{m.reasons.join(' · ')}</div>
                  </div>
                );
              })}
              {evaluation.matches.length > 12 && (
                <div className="text-[9px] text-muted-foreground/60">
                  +{evaluation.matches.length - 12} more matches
                </div>
              )}
            </div>
          )}

          {/* Saved rules */}
          {rules.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1.5">
              <div className="min-w-0">
                <div className="truncate text-[10px] font-medium text-foreground">{r.name}</div>
                <div className="truncate font-mono text-[9px] text-muted-foreground/70">
                  {[
                    r.eventTypes.length ? r.eventTypes.join('/') : 'any type',
                    `≥${r.minSeverity}`,
                    r.countries.length ? r.countries.join(',') : null,
                    r.near ? `${r.near.radiusKm}km` : null,
                    r.keywords.length ? `"${r.keywords[0]}"` : null,
                  ].filter(Boolean).join(' · ')}
                </div>
              </div>
              <button
                onClick={() => void removeRule(r.id)}
                disabled={busy}
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-rose-400 disabled:opacity-40 cursor-pointer"
                aria-label={`Delete rule ${r.name}`}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}

          {rules.length === 0 && !loading && (
            <div className="text-[10px] text-muted-foreground/70">
              No alerts yet. Start from a preset:
            </div>
          )}

          <button
            onClick={() => setShowPresets((v) => !v)}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-primary/25 bg-primary/10 px-2 py-1.5 text-[10px] font-semibold text-foreground disabled:opacity-50 cursor-pointer"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
            Add alert rule
          </button>

          {showPresets && (
            <div className="space-y-1">
              {RULE_PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => void addRule(p.rule)}
                  disabled={busy}
                  className="w-full rounded-lg border border-border/25 px-2 py-1.5 text-left text-[10px] text-foreground hover:border-primary/30 hover:bg-accent/40 disabled:opacity-50 cursor-pointer"
                >
                  <div className="font-medium">{p.label}</div>
                  <div className="font-mono text-[9px] text-muted-foreground/70">
                    {[
                      (p.rule.eventTypes ?? []).join('/') || 'any type',
                      p.rule.minSeverity ? `≥${p.rule.minSeverity}` : null,
                      p.rule.minRelevance ? `rel≥${p.rule.minRelevance}` : null,
                      (p.rule.commodities ?? []).join(', ') || null,
                    ].filter(Boolean).join(' · ')}
                  </div>
                </button>
              ))}
              <div className="pt-0.5 text-[9px] leading-relaxed text-muted-foreground/60">
                Severities: {ALERT_SEVERITIES.join(' < ')}. Rules are evaluated against the same
                world state the map reads — no separate data path.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
