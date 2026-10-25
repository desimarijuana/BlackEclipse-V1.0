'use client';

// ── Node library / palette ───────────────────────────────────────────────────
// Searchable list of every registered node, grouped by category. Items are both
// click-to-add and drag-to-place. It reads the registry directly, so a new node
// type appears here with no edit to this file.

import { useMemo, useState, type DragEvent } from 'react';
import { cn } from '@/lib/utils';
import { Search, GitBranch } from '@/lib/icons';
import { listNodeDefinitions } from '@/lib/graph-studio/registry';
import { sideEffectColor } from '@/lib/graph-studio/port-style';
import type { NodeCategory, NodeDefinition } from '@/lib/graph-studio/types';
import { nodeIcon } from './node-icons';

const CATEGORY_LABELS: Record<NodeCategory, string> = {
  trigger: 'Triggers',
  data: 'Data',
  transform: 'Transform',
  logic: 'Logic',
  integration: 'Integrations',
  finance: 'Market data',
  quant: 'Quant',
  agent: 'Agents',
  research: 'Research & Evidence',
  trading: 'Paper trading',
  output: 'Output',
};

export function NodePalette({ onAdd }: { onAdd: (type: string, version: string) => void }) {
  const [query, setQuery] = useState('');
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const defs = listNodeDefinitions().filter(
      (d) => !q || d.label.toLowerCase().includes(q) || d.type.toLowerCase().includes(q) || d.description.toLowerCase().includes(q),
    );
    const byCat = new Map<NodeCategory, NodeDefinition[]>();
    for (const def of defs) {
      (byCat.get(def.category) ?? byCat.set(def.category, []).get(def.category)!).push(def);
    }
    return [...byCat.entries()];
  }, [query]);

  const onDragStart = (event: DragEvent, def: NodeDefinition) => {
    event.dataTransfer.setData('application/eclipse-node', JSON.stringify({ type: def.type, version: def.version }));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="flex h-full flex-col">
      <div className="relative mb-2">
        <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search nodes…"
          className="w-full rounded-lg border border-white/10 bg-background/60 py-1.5 pl-8 pr-2 text-[12px] outline-none focus:border-sky-400/50"
        />
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {groups.length === 0 && <p className="px-1 py-4 text-[12px] text-muted-foreground">No matching nodes.</p>}
        {groups.map(([category, defs]) => (
          <div key={category}>
            <div className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {CATEGORY_LABELS[category]}
            </div>
            <div className="space-y-1">
              {defs.map((def) => {
                const Icon = nodeIcon(def.icon, def.category);
                return (
                  <button
                    key={`${def.type}@${def.version}`}
                    type="button"
                    draggable
                    onDragStart={(e) => onDragStart(e, def)}
                    onClick={() => onAdd(def.type, def.version)}
                    title={def.description}
                    className={cn(
                      'glass-card-subtle group flex w-full items-center gap-2 rounded-lg border border-white/10 px-2.5 py-2 text-left transition-colors hover:border-sky-400/40 hover:bg-white/5',
                    )}
                  >
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md"
                      style={{ background: `${sideEffectColor(def.sideEffects)}22`, color: sideEffectColor(def.sideEffects) }}
                    >
                      <Icon size={13} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] font-medium text-foreground">{def.label}</span>
                      <span className="block truncate text-[10px] text-muted-foreground">{def.type}</span>
                    </span>
                    <GitBranch size={11} className="shrink-0 text-muted-foreground opacity-0 group-hover:opacity-60" />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
