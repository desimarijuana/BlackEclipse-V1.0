'use client';

// ── Model Control Center ─────────────────────────────────────────────────────
// The UI for the provider-agnostic Model Runtime. It shows the registered
// providers/models, the task routing, usage/cost, health and the routing debug
// view. Everything is read from `/api/harness/model-runtime/**` (which proxies
// to the Python runtime); this screen adds no model logic and never sees a
// credential. Plain, human sentences are i18n keys.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Boxes, Gauge, GitBranch, Layers, RefreshCw } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { TabBar, type TabItem } from '@/components/ui/tab-bar';
import {
  getRuntimeHealth,
  getRuntimeRouting,
  getRuntimeUsage,
  listRuntimeModels,
  listRuntimeProviders,
  type RuntimeHealthView,
  type RuntimeModelView,
  type RuntimeProviderView,
  type RuntimeRoutingView,
  type RuntimeUsageView,
} from '@/lib/harness/clients/model-runtime-browser';
import { ProvidersPane } from './providers-pane';
import { ModelsPane } from './models-pane';
import { RoutingPane } from './routing-pane';
import { UsagePane } from './usage-pane';
import { HealthPane } from './health-pane';
import { DebugPane } from './debug-pane';

type PaneId = 'providers' | 'models' | 'routing' | 'usage' | 'health' | 'debug';

export function ModelRuntimeScreen() {
  const t = useT();
  const [pane, setPane] = useState<PaneId>('providers');
  const [providers, setProviders] = useState<RuntimeProviderView[]>([]);
  const [models, setModels] = useState<RuntimeModelView[]>([]);
  const [routing, setRouting] = useState<RuntimeRoutingView | null>(null);
  const [usage, setUsage] = useState<RuntimeUsageView | null>(null);
  const [health, setHealth] = useState<RuntimeHealthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, m, r, u, h] = await Promise.all([
        listRuntimeProviders(),
        listRuntimeModels(),
        getRuntimeRouting(),
        getRuntimeUsage(),
        getRuntimeHealth(),
      ]);
      setProviders(p);
      setModels(m);
      setRouting(r);
      setUsage(u);
      setHealth(h);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('modelRuntime.error.load'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const items: TabItem[] = useMemo(
    () => [
      { id: 'providers', label: t('modelRuntime.tab.providers'), icon: Boxes },
      { id: 'models', label: t('modelRuntime.tab.models'), icon: Layers },
      { id: 'routing', label: t('modelRuntime.tab.routing'), icon: GitBranch },
      { id: 'usage', label: t('modelRuntime.tab.usage'), icon: Gauge },
      { id: 'health', label: t('modelRuntime.tab.health'), icon: Activity },
      { id: 'debug', label: t('modelRuntime.tab.debug'), icon: GitBranch },
    ],
    [t],
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t('modelRuntime.title')}</h1>
          <p className="text-[12px] text-muted-foreground">{t('modelRuntime.description')}</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] text-foreground"
          disabled={loading}
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : undefined} />
          {t('modelRuntime.refresh')}
        </button>
      </header>

      {error && (
        <div className="glass-card-subtle mb-3 rounded-xl border border-amber-500/30 p-3 text-[12px] text-amber-200">
          {error}
        </div>
      )}

      <TabBar items={items} activeId={pane} onChange={(id) => setPane(id as PaneId)} variant="glass" />

      {pane === 'providers' && (
        <ProvidersPane providers={providers} models={models} health={health?.providers ?? []} />
      )}
      {pane === 'models' && <ModelsPane providers={providers} models={models} />}
      {pane === 'routing' && <RoutingPane routing={routing} />}
      {pane === 'usage' && <UsagePane usage={usage} />}
      {pane === 'health' && <HealthPane health={health} providers={providers} />}
      {pane === 'debug' && <DebugPane routing={routing} />}
    </div>
  );
}
