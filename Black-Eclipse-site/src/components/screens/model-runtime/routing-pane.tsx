'use client';

// ── Routing pane ─────────────────────────────────────────────────────────────
// Shows the task routing: the task profiles, the logical aliases that resolve
// dynamically, and the active scoring policy. The runtime owns the policy; this
// pane explains it. It also lets the operator save simple routing preferences
// ("local only", "don't use paid models") that override the automatic router.

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import { ArrowRight, Save } from '@/lib/icons';
import type { RuntimeRoutingView } from '@/lib/harness/model-runtime-browser';
import { dynKey } from '@/lib/harness/model-runtime-browser';
import { EmptyState } from './providers-pane';

/** The default task → alias story shown in the routing panel (spec §40). */
const TASK_ROUTES: Array<{ task: string; alias: string }> = [
  { task: 'simple_chat', alias: 'eclipse-fast' },
  { task: 'coding', alias: 'eclipse-coder' },
  { task: 'financial_research', alias: 'eclipse-reasoning' },
  { task: 'vision', alias: 'eclipse-vision' },
  { task: 'financial_extraction', alias: 'eclipse-cheap' },
  { task: 'background_task', alias: 'eclipse-local' },
];

interface PolicyState {
  localOnly: boolean;
  preferFree: boolean;
}

export function RoutingPane({ routing }: { routing: RuntimeRoutingView | null }) {
  const t = useT();
  if (!routing) return <EmptyState text={t('modelRuntime.routing.empty')} />;

  const weights = (routing.policy.baseWeights ?? {}) as Record<string, number>;

  return (
    <div className="space-y-3">
      <section className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.routing.taskRoutes')}</h3>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {TASK_ROUTES.filter((r) => routing.taskProfiles.includes(r.task)).map((r) => (
            <div key={r.task} className="flex items-center gap-2 text-[12px] text-foreground">
              <span className="text-muted-foreground">{dynKey(t, `modelRuntime.task.${r.task}`)}</span>
              <ArrowRight size={12} className="text-muted-foreground/60" />
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-primary">{r.alias}</code>
            </div>
          ))}
        </div>
      </section>

      <RoutingPreferences />

      <section className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.routing.aliases')}</h3>
        <div className="flex flex-wrap gap-1.5">
          {routing.aliases.map((a) => (
            <code key={a} className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] text-foreground">{a}</code>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">{t('modelRuntime.routing.aliasesHint')}</p>
      </section>

      <section className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.routing.weights')}</h3>
        <div className="space-y-1.5">
          {Object.entries(weights).map(([key, value]) => (
            <div key={key} className="flex items-center gap-3 text-[12px] text-foreground">
              <span className="w-28 shrink-0 text-muted-foreground">{dynKey(t, `modelRuntime.weight.${key}`)}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-primary/60"
                  style={{ width: `${Math.min(100, Math.round((value / 2) * 100))}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right text-muted-foreground">{value.toFixed(1)}</span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          {t('modelRuntime.routing.fallbackDepth', { depth: String(routing.policy.fallbackDepth ?? 0) })}
          {' · '}
          {routing.policy.fallbackEnabled
            ? t('modelRuntime.routing.fallbackOn')
            : t('modelRuntime.routing.fallbackOff')}
        </p>
      </section>
    </div>
  );
}

/** Operator routing preferences (spec §44) persisted through Settings › AI. */
function RoutingPreferences() {
  const t = useT();
  const [policy, setPolicy] = useState<PolicyState>({ localOnly: false, preferFree: false });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetch('/api/settings')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const p = (data?.llm?.routingPolicy ?? {}) as { localOnly?: boolean; preferFree?: boolean };
        setPolicy({ localOnly: Boolean(p.localOnly), preferFree: Boolean(p.preferFree) });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(next: PolicyState) {
    setSaving(true);
    setSaved(false);
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: { routingPolicy: next } }),
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  function toggle(key: keyof PolicyState) {
    const next = { ...policy, [key]: !policy[key] };
    setPolicy(next);
    void save(next);
  }

  return (
    <section className="glass-card rounded-2xl p-4">
      <h3 className="mb-2 text-[13px] font-semibold text-foreground">{t('modelRuntime.routing.preferences')}</h3>
      <p className="mb-2 text-[11px] text-muted-foreground">{t('modelRuntime.routing.preferencesHint')}</p>
      <div className="space-y-2">
        <Toggle
          label={t('modelRuntime.routing.localOnly')}
          checked={policy.localOnly}
          onChange={() => toggle('localOnly')}
          disabled={saving}
        />
        <Toggle
          label={t('modelRuntime.routing.avoidPaid')}
          checked={policy.preferFree}
          onChange={() => toggle('preferFree')}
          disabled={saving}
        />
      </div>
      {saved && (
        <p className="mt-2 flex items-center gap-1 text-[11px] text-emerald-300">
          <Save size={11} /> {t('modelRuntime.routing.saved')}
        </p>
      )}
    </section>
  );
}

function Toggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[12px] text-foreground">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="h-3.5 w-3.5 accent-[var(--primary)]"
      />
      {label}
    </label>
  );
}
