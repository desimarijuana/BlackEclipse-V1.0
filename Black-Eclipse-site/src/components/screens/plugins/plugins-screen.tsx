'use client';

// ─── Plugin Platform screen ──────────────────────────────────────────────────
// Lists installed plugins, shows their health and contributions, and renders
// plugin-contributed UI panels from a SAFE, declarative view spec (markdown /
// keyvalue / table / list / status). It never injects plugin HTML or DOM. All
// data comes from the runtime via `plugins-browser` — never fabricated locally.

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { Plug, Power, RefreshCw, Search } from '@/lib/icons';
import {
  type PluginInspect,
  type PluginRecord,
  type PluginView,
  type UiPanel,
  disablePlugin,
  enablePlugin,
  getPlugin,
  listPlugins,
  renderPanel,
  uiPanels,
} from '@/lib/harness/clients/plugins-browser';

const STATUS_TONE: Record<string, string> = {
  RUNNING: 'text-emerald-300',
  ENABLED: 'text-emerald-300',
  INSTALLED: 'text-sky-300',
  DISABLED: 'text-zinc-400',
  FAILED: 'text-rose-300',
  QUARANTINED: 'text-amber-300',
};

function PluginViewBody({ view }: { view: PluginView }) {
  if (view.type === 'markdown') {
    return <pre className="whitespace-pre-wrap font-sans text-sm text-zinc-200">{view.body}</pre>;
  }
  if (view.type === 'keyvalue') {
    return (
      <dl className="grid grid-cols-[minmax(0,12rem)_1fr] gap-x-4 gap-y-2 text-sm">
        {view.items.map((item, i) => (
          <div key={i} className="contents">
            <dt className="text-zinc-400">{item.label}</dt>
            <dd className="text-zinc-100">{String(item.value)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  if (view.type === 'table') {
    return (
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-zinc-400">
            {view.columns.map((c) => (
              <th key={c} className="px-2 py-1 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {view.rows.map((row, i) => (
            <tr key={i} className="border-t border-white/5">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 text-zinc-100">{String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (view.type === 'list') {
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-200">
        {view.items.map((item, i) => (
          <li key={i}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
        ))}
      </ul>
    );
  }
  if (view.type === 'status') {
    return (
      <div className="text-sm">
        <span className={cn('font-medium', STATUS_TONE[view.status] ?? 'text-zinc-200')}>{view.status}</span>
        {view.detail ? <p className="mt-1 text-zinc-400">{view.detail}</p> : null}
      </div>
    );
  }
  return <p className="text-sm text-zinc-400">{view.body}</p>;
}

export function PluginsScreen() {
  const [plugins, setPlugins] = useState<PluginRecord[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PluginInspect | null>(null);
  const [panels, setPanels] = useState<UiPanel[]>([]);
  const [panelId, setPanelId] = useState<string | null>(null);
  const [view, setView] = useState<PluginView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');

  const refresh = useCallback(async () => {
    try {
      const data = await listPlugins();
      setPlugins(data.plugins);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load plugins');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const select = useCallback(async (id: string) => {
    setSelected(id);
    setDetail(null);
    setPanels([]);
    setPanelId(null);
    setView(null);
    try {
      const [info, panelList] = await Promise.all([getPlugin(id), uiPanels(id)]);
      setDetail(info);
      setPanels(panelList.panels);
      if (panelList.panels[0]) {
        setPanelId(panelList.panels[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load plugin');
    }
  }, []);

  const openPanel = useCallback(
    async (id: string, panel: string) => {
      setPanelId(panel);
      setView(null);
      try {
        const rendered = await renderPanel(id, panel);
        setView(rendered.view);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'failed to render panel');
      }
    },
    [],
  );

  const toggle = useCallback(
    async (record: PluginRecord) => {
      setBusy(true);
      try {
        if (record.enabled) await disablePlugin(record.pluginId);
        else await enablePlugin(record.pluginId);
        await refresh();
        if (selected === record.pluginId) await select(record.pluginId);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'lifecycle action failed');
      } finally {
        setBusy(false);
      }
    },
    [refresh, select, selected],
  );

  const filtered = plugins.filter((p) => {
    const q = query.trim().toLowerCase();
    return !q || p.name.toLowerCase().includes(q) || p.pluginId.includes(q);
  });

  return (
    <div className="flex h-full min-h-0 gap-4 p-4">
      <aside className="glass-card flex w-80 shrink-0 flex-col rounded-lg p-3">
        <div className="mb-3 flex items-center gap-2">
          <Plug className="h-4 w-4 text-zinc-300" weight="fill" />
          <h2 className="text-sm font-semibold text-zinc-100">Plugins</h2>
          <button
            type="button"
            onClick={() => void refresh()}
            className="glass-card-subtle ml-auto rounded-md p-1.5 text-zinc-300 hover:text-white"
            aria-label="Refresh plugins"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="mb-3 flex items-center gap-2 rounded-md border border-white/10 px-2 py-1.5">
          <Search className="h-3.5 w-3.5 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter plugins"
            className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-500"
          />
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="px-2 py-4 text-sm text-zinc-500">No plugins installed.</p>
          ) : (
            filtered.map((record) => (
              <button
                key={record.pluginId}
                type="button"
                onClick={() => void select(record.pluginId)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left',
                  selected === record.pluginId ? 'glass-card-strong' : 'hover:bg-white/5',
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-zinc-100">{record.name}</span>
                  <span className="block truncate text-xs text-zinc-500">
                    v{record.version} · {record.publisher}
                  </span>
                </span>
                <span className={cn('text-xs', STATUS_TONE[record.status] ?? 'text-zinc-400')}>
                  {record.status}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      <main className="glass-card min-h-0 flex-1 overflow-y-auto rounded-lg p-4">
        {error ? (
          <div className="glass-card-subtle mb-4 rounded-md border border-rose-500/30 px-3 py-2 text-sm text-rose-300">
            {error}
          </div>
        ) : null}
        {!selected || !detail ? (
          <p className="text-sm text-zinc-500">Select a plugin to inspect it.</p>
        ) : (
          <div className="space-y-5">
            <header className="flex items-start gap-3">
              <div className="flex-1">
                <h1 className="text-lg font-semibold text-zinc-100">{detail.plugin.name}</h1>
                <p className="text-sm text-zinc-400">
                  {detail.plugin.pluginId} · v{detail.plugin.version} · {detail.plugin.trust} ·{' '}
                  {detail.plugin.verification}
                </p>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void toggle(detail.plugin)}
                className="glass-card-subtle flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
              >
                <Power className="h-3.5 w-3.5" weight="fill" />
                {detail.plugin.enabled ? 'Disable' : 'Enable'}
              </button>
            </header>

            <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(['status', 'toolCalls', 'crashes', 'latencyMs'] as const).map((key) => (
                <div key={key} className="glass-card-subtle rounded-md px-3 py-2">
                  <div className="text-xs text-zinc-500">{key}</div>
                  <div className="text-sm text-zinc-100">{String(detail.health[key])}</div>
                </div>
              ))}
            </section>

            <section>
              <h3 className="mb-2 text-sm font-medium text-zinc-300">Permissions</h3>
              <div className="flex flex-wrap gap-1">
                {detail.plugin.permissions.length === 0 ? (
                  <span className="text-sm text-zinc-500">none</span>
                ) : (
                  detail.plugin.permissions.map((p) => (
                    <span key={p} className="glass-card-subtle rounded px-2 py-0.5 text-xs text-zinc-300">
                      {p}
                    </span>
                  ))
                )}
              </div>
            </section>

            <section>
              <h3 className="mb-2 text-sm font-medium text-zinc-300">
                Contributions ({detail.contributions.length})
              </h3>
              <div className="flex flex-wrap gap-1">
                {detail.contributions.map((c, i) => (
                  <span key={i} className="glass-card-subtle rounded px-2 py-0.5 text-xs text-zinc-300">
                    {c.kind}:{c.name}
                  </span>
                ))}
              </div>
            </section>

            {panels.length > 0 ? (
              <section>
                <div className="mb-2 flex items-center gap-2">
                  {panels.map((panel) => (
                    <button
                      key={panel.id}
                      type="button"
                      onClick={() => void openPanel(detail.plugin.pluginId, panel.id)}
                      className={cn(
                        'rounded-md px-2.5 py-1 text-xs',
                        panelId === panel.id ? 'glass-card-strong text-zinc-100' : 'glass-card-subtle text-zinc-400',
                      )}
                    >
                      {panel.title}
                    </button>
                  ))}
                </div>
                <div className="glass-card-subtle rounded-md p-3">
                  {view ? (
                    <PluginViewBody view={view} />
                  ) : (
                    <p className="text-sm text-zinc-500">Loading panel…</p>
                  )}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
