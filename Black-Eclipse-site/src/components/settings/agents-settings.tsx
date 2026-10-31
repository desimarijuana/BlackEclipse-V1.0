'use client';

// ── Settings › Agents ────────────────────────────────────────────────────────
// Operator-authored agent presets for Graph Studio. The runtime owns validation
// and versioning; this panel is a thin CRUD surface plus the tool allowlist.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Bot, Plus, Save, Search, Trash2 } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Field, Panel, SubSection, Toggle } from '@/components/screens/settings-ui';
import {
  AgentPresetApiError,
  archiveAgentPreset,
  createAgentPreset,
  getAgentPreset,
  listAgentPresets,
  listAgentTools,
  updateAgentPreset,
  type AgentPreset,
  type AgentPresetEffect,
  type AgentPresetInput,
  type AgentPresetSummary,
} from '@/lib/agent-presets/client';

interface Draft {
  id: string | null;
  name: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  maxSteps: number;
  allowMcpTools: boolean;
  allowPluginTools: boolean;
  allowEffectful: boolean;
}

const EMPTY: Draft = {
  id: null,
  name: '',
  description: '',
  systemPrompt: '',
  tools: [],
  maxSteps: 8,
  allowMcpTools: false,
  allowPluginTools: false,
  allowEffectful: false,
};

function toDraft(preset: AgentPreset): Draft {
  return {
    id: preset.id,
    name: preset.name,
    description: preset.description,
    systemPrompt: preset.systemPrompt,
    tools: [...preset.tools],
    maxSteps: preset.maxSteps,
    allowMcpTools: preset.allowMcpTools,
    allowPluginTools: preset.allowPluginTools,
    allowEffectful: preset.allowEffectful,
  };
}

const inputClass =
  'w-full rounded-lg border border-white/10 bg-background/60 px-2.5 py-1.5 text-[12px] text-foreground outline-none focus:border-primary/50';

export function AgentsSettingsPanel() {
  const [presets, setPresets] = useState<AgentPresetSummary[]>([]);
  const [tools, setTools] = useState<AgentPresetEffect[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [next, catalog] = await Promise.all([listAgentPresets(), listAgentTools()]);
      setPresets(next);
      setTools(catalog);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent presets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const open = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      setDraft(toDraft(await getAgentPreset(id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load the preset');
    } finally {
      setBusy(false);
    }
  };

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const toggleTool = (name: string) => {
    setDraft((current) => ({
      ...current,
      tools: current.tools.includes(name)
        ? current.tools.filter((item) => item !== name)
        : [...current.tools, name],
    }));
  };

  const filteredTools = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = q
      ? tools.filter((tool) => tool.name.toLowerCase().includes(q) || tool.description.toLowerCase().includes(q))
      : tools;
    return list.slice(0, 200);
  }, [tools, search]);

  const effectfulSelected = useMemo(
    () => draft.tools.filter((name) => tools.find((tool) => tool.name === name)?.permission !== 'read'),
    [draft.tools, tools],
  );

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const payload: AgentPresetInput = {
      name: draft.name,
      description: draft.description,
      systemPrompt: draft.systemPrompt,
      tools: draft.tools,
      maxSteps: draft.maxSteps,
      allowMcpTools: draft.allowMcpTools,
      allowPluginTools: draft.allowPluginTools,
      allowEffectful: draft.allowEffectful,
    };
    try {
      const saved = draft.id
        ? await updateAgentPreset(draft.id, payload)
        : await createAgentPreset(payload);
      setDraft(toDraft(saved));
      setNotice(`${saved.name} saved as v${saved.version}`);
      await refresh();
    } catch (err) {
      setError(err instanceof AgentPresetApiError ? err.message : err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!draft.id || !window.confirm(`Archive “${draft.name}”? Existing pinned runs keep their version.`)) return;
    setBusy(true);
    try {
      await archiveAgentPreset(draft.id);
      setDraft(EMPTY);
      setNotice('Preset archived');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <SubSection
        icon={Bot}
        title="Agent presets"
        description="The three built-ins always exist. A custom preset pins a system prompt and an explicit tool list; a graph node pins its version, so editing a preset never changes an old run."
      >
        <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
          <Panel className="p-2">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Your presets
              </span>
              <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(EMPTY)} className="gap-1">
                <Plus size={12} /> New
              </Button>
            </div>
            <div className="max-h-[420px] space-y-1 overflow-y-auto">
              {loading && <p className="px-2 py-3 text-[11px] text-muted-foreground">Loading…</p>}
              {!loading && presets.length === 0 && (
                <p className="px-2 py-3 text-[11px] text-muted-foreground">
                  No custom presets yet. Create one and select it in an agent node.
                </p>
              )}
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => void open(preset.id)}
                  className={cn(
                    'w-full rounded-lg border px-2 py-1.5 text-left transition-colors',
                    draft.id === preset.id
                      ? 'border-primary/40 bg-primary/10'
                      : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]',
                  )}
                >
                  <span className="block truncate text-[12px] font-medium text-foreground">{preset.name}</span>
                  <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                    v{preset.version} · {preset.toolCount} tools
                    {preset.effects.some((effect) => effect !== 'read') ? ' · effectful' : ''}
                  </span>
                </button>
              ))}
            </div>
          </Panel>

          <Panel className="space-y-3 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-semibold text-foreground">
                {draft.id ? `${draft.name || 'Preset'} editor` : 'New preset'}
              </span>
              <div className="flex items-center gap-1.5">
                {draft.id && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => void remove()}
                    disabled={busy}
                    className="gap-1 text-rose-300 hover:text-rose-200"
                  >
                    <Trash2 size={12} /> Archive
                  </Button>
                )}
                <Button type="button" size="sm" onClick={() => void save()} disabled={busy} className="gap-1">
                  <Save size={12} /> Save
                </Button>
              </div>
            </div>

            {error && (
              <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-200">
                {error}
              </p>
            )}
            {notice && (
              <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-200">
                {notice}
              </p>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name">
                <input
                  value={draft.name}
                  onChange={(event) => update('name', event.target.value)}
                  className={inputClass}
                  placeholder="Gold scalper analyst"
                />
              </Field>
              <Field label="Max steps" hint="One bounded run may use at most this many model turns.">
                <input
                  type="number"
                  min={1}
                  max={32}
                  value={draft.maxSteps}
                  onChange={(event) => update('maxSteps', Number(event.target.value))}
                  className={inputClass}
                />
              </Field>
            </div>

            <Field label="Description">
              <input
                value={draft.description}
                onChange={(event) => update('description', event.target.value)}
                className={inputClass}
                placeholder="What this agent is for"
              />
            </Field>

            <Field label="System prompt" hint="The runtime pins this prompt with the preset version.">
              <textarea
                value={draft.systemPrompt}
                onChange={(event) => update('systemPrompt', event.target.value)}
                rows={6}
                className={cn(inputClass, 'resize-y font-mono text-[11px]')}
                placeholder="You are a disciplined intraday analyst. ..."
              />
            </Field>

            <div className="flex flex-wrap gap-4 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2">
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Toggle checked={draft.allowMcpTools} onChange={(value) => update('allowMcpTools', value)} />
                Allow registered MCP tools
              </label>
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Toggle checked={draft.allowPluginTools} onChange={(value) => update('allowPluginTools', value)} />
                Allow plugin tools
              </label>
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Toggle checked={draft.allowEffectful} onChange={(value) => update('allowEffectful', value)} />
                Allow effectful tools
              </label>
            </div>

            {effectfulSelected.length > 0 && !draft.allowEffectful && (
              <p className="flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                {effectfulSelected.length} selected tool(s) write or act externally. Tick “Allow effectful
                tools” to save this preset.
              </p>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-foreground">
                  Tools ({draft.tools.length})
                </span>
                <div className="flex min-w-0 items-center gap-1.5 rounded-lg border border-white/10 bg-background/60 px-2">
                  <Search size={12} className="text-muted-foreground" />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search tools…"
                    className="w-40 bg-transparent py-1 text-[11px] outline-none"
                  />
                </div>
              </div>
              <div className="max-h-[260px] overflow-y-auto rounded-lg border border-white/10">
                {filteredTools.map((tool) => {
                  const selected = draft.tools.includes(tool.name);
                  return (
                    <button
                      key={tool.name}
                      type="button"
                      onClick={() => toggleTool(tool.name)}
                      className={cn(
                        'flex w-full items-start gap-2 border-b border-white/[0.04] px-2.5 py-1.5 text-left last:border-0',
                        selected ? 'bg-primary/10' : 'hover:bg-white/[0.04]',
                      )}
                    >
                      <span
                        className={cn(
                          'mt-0.5 h-3 w-3 shrink-0 rounded border',
                          selected ? 'border-primary bg-primary' : 'border-white/25',
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="truncate font-mono text-[10.5px] text-foreground">{tool.name}</span>
                          <span
                            className={cn(
                              'rounded px-1 text-[9px]',
                              tool.permission === 'read'
                                ? 'bg-white/5 text-muted-foreground'
                                : 'bg-amber-500/15 text-amber-200',
                            )}
                          >
                            {tool.permission}
                          </span>
                        </span>
                        <span className="mt-0.5 block line-clamp-1 text-[10px] text-muted-foreground">
                          {tool.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
                {filteredTools.length === 0 && (
                  <p className="px-2 py-4 text-center text-[11px] text-muted-foreground">No tools match.</p>
                )}
              </div>
            </div>
          </Panel>
        </div>
      </SubSection>
    </div>
  );
}
