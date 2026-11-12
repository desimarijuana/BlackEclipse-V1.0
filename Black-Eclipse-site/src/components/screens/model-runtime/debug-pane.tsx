'use client';

// ── Routing debug pane ───────────────────────────────────────────────────────
// "Why was this model selected?" The user picks a task (or types an explicit
// model) and the runtime returns the full decision trace: candidates with
// per-dimension scores, excluded models with the reason, the selected model and
// the ordered fallbacks. Pure computation; no provider is called.

import { useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import { ArrowRight, Search } from '@/lib/icons';
import { routeModel, dynKey, type RuntimeRouteDecisionView, type RuntimeRoutingView } from '@/lib/harness/clients/model-runtime-browser';

interface Props {
  routing: RuntimeRoutingView | null;
}

export function DebugPane({ routing }: Props) {
  const t = useT();
  const profiles = routing?.taskProfiles ?? [];
  const [task, setTask] = useState(profiles[0] ?? 'default');
  const [model, setModel] = useState('');
  const [decision, setDecision] = useState<RuntimeRouteDecisionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function explain() {
    setBusy(true);
    setError(null);
    try {
      const result = await routeModel({
        task: model.trim() ? undefined : task,
        model: model.trim() || undefined,
      });
      setDecision(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('modelRuntime.debug.error'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <section className="glass-card flex flex-wrap items-end gap-3 rounded-2xl p-4">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('modelRuntime.debug.task')}
          </label>
          <select
            value={task}
            onChange={(e) => setTask(e.target.value)}
            disabled={Boolean(model.trim())}
            className="glass-card-subtle rounded-lg px-2 py-1.5 text-[12px] text-foreground outline-none disabled:opacity-50"
          >
            {profiles.map((p) => (
              <option key={p} value={p}>{dynKey(t, `modelRuntime.task.${p}`)}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('modelRuntime.debug.explicitModel')}
          </label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="provider/model-id"
            className="glass-card-subtle w-56 rounded-lg px-2 py-1.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/50"
          />
        </div>
        <button
          type="button"
          onClick={() => void explain()}
          disabled={busy}
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] text-foreground"
        >
          <Search size={13} />
          {t('modelRuntime.debug.explain')}
        </button>
      </section>

      {error && (
        <div className="glass-card-subtle rounded-xl border border-amber-500/30 p-3 text-[12px] text-amber-200">
          {error}
        </div>
      )}

      {decision && <DecisionTrace decision={decision} />}
    </div>
  );
}

function DecisionTrace({ decision }: { decision: RuntimeRouteDecisionView }) {
  const t = useT();
  const selected = decision.selected;
  const excluded = decision.candidates.filter((c) => c.excludedReason);
  const ranked = decision.candidates.filter((c) => !c.excludedReason).slice(0, 8);

  return (
    <div className="space-y-3">
      <section className="glass-card rounded-2xl p-4">
        <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <span>{t('modelRuntime.debug.task')}</span>
          <code className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-foreground">{decision.task}</code>
          {decision.alias && (
            <>
              <span>{t('modelRuntime.debug.alias')}</span>
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-primary">{decision.alias}</code>
            </>
          )}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[14px] font-semibold text-foreground">
          {t('modelRuntime.debug.selected')}
          <ArrowRight size={13} className="text-muted-foreground/60" />
          <code className="rounded bg-primary/10 px-2 py-0.5 text-[13px] text-primary">
            {selected ? selected.model : t('modelRuntime.debug.none')}
          </code>
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground">{decision.reason}</p>
        {decision.fallbacks.length > 0 && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {t('modelRuntime.debug.fallbacks')}: {decision.fallbacks.map((f) => f.model).join(' → ')}
          </p>
        )}
      </section>

      <section className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.debug.candidates')}</h3>
        <div className="space-y-1.5">
          {ranked.map((c) => (
            <div key={c.model} className="flex items-center gap-3 text-[12px]">
              <code className="w-64 shrink-0 truncate text-foreground">{c.model}</code>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-emerald-500/50"
                  style={{ width: `${Math.min(100, Math.round(((c.score ?? 0) / 4) * 100))}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right text-muted-foreground">
                {c.score === null ? '—' : c.score.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {excluded.length > 0 && (
        <section className="glass-card rounded-2xl p-4">
          <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.debug.excluded')}</h3>
          <div className="space-y-1">
            {excluded.slice(0, 12).map((c) => (
              <div key={c.model} className="flex items-center gap-3 text-[12px]">
                <code className="w-64 shrink-0 truncate text-muted-foreground">{c.model}</code>
                <span className="text-amber-300/80">{c.excludedReason}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
