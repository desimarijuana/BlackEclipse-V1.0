// ── Curated workspace templates ──────────────────────────────────────────────
// Templates are generic: each takes the page's widget ids in its canonical
// registry order and arranges them into sections/columns. Missing ids are
// skipped, so a page can safely pass a shorter registry.

import { cloneLayout, normalizeLayout } from './ops';
import { newId, type WorkspaceLayout } from './types';

export interface WorkspaceTemplate {
  id: string;
  name: string;
  desc: string;
  /** widgetIds in the page's canonical order → layout */
  build: (widgetIds: string[]) => WorkspaceLayout;
}

type ColSpec = number[];
type SectionSpec = ColSpec[];

function buildFromSpec(spec: SectionSpec[], widgetIds: string[]): WorkspaceLayout {
  const sections = spec
    .map(row => {
      const columns = row
        .map(col => {
          const widgets = col
            .map(i => widgetIds[i])
            .filter((id): id is string => Boolean(id))
            .map(widgetId => ({ id: newId('wid'), widgetId, height: null as number | null }));
          return { id: newId('col'), weight: 3, widgets };
        })
        .filter(c => c.widgets.length > 0);
      return { id: newId('sec'), columns };
    })
    .filter(s => s.columns.length > 0);
  // Round-trip through the validator so every template ships structurally clean.
  return normalizeLayout({ version: 1, sections }) ?? cloneLayout({ version: 1, sections: [] });
}

export const WORKSPACE_TEMPLATES: WorkspaceTemplate[] = [
  {
    id: 'classic',
    name: 'Classic',
    desc: 'KPIs on top, allocation & holdings mid, ledger below.',
    build: ids => buildFromSpec([[[0, 1], [2]], [[3], [4]], [[5], [6]], [[7], [8]]], ids),
  },
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Full-width performance strip, three-column live stats.',
    build: ids => buildFromSpec([[[0]], [[1], [2], [3]], [[4], [5]], [[6], [7], [8]]], ids),
  },
  {
    id: 'analyst',
    name: 'Analyst',
    desc: 'Risk-first: metrics & health up top, deep dives below.',
    build: ids => buildFromSpec([[[0, 1]], [[2], [3]], [[4], [5], [6]], [[7], [8]]], ids),
  },
  {
    id: 'minimal',
    name: 'Minimal',
    desc: 'Just the essentials, two-up.',
    build: ids => buildFromSpec([[[0], [1]], [[2], [3]]], ids),
  },
  {
    id: 'executive',
    name: 'Executive',
    desc: 'Command-center: KPI strip, performance + allocation, holdings + AI, risk + health, ledger + projection.',
    build: ids => buildFromSpec([[[0]], [[1], [2]], [[3], [9]], [[6], [7]], [[5], [8]], [[4]]], ids),
  },
  {
    id: 'deep-dive',
    name: 'Deep Dive',
    desc: 'Full-width performance, then allocation + holdings, risk trio, ledger, insights + rebalance.',
    build: ids => buildFromSpec([[[0]], [[1]], [[2], [3]], [[6], [7], [8]], [[5]], [[9], [4]]], ids),
  },
  {
    id: 'projection',
    name: 'Projection',
    desc: 'Future-focused: Monte Carlo front and center, allocation + risk beside it.',
    build: ids => buildFromSpec([[[0]], [[8], [2]], [[1], [6]], [[3], [9]], [[5], [7]], [[4]]], ids),
  },
  {
    id: 'compact',
    name: 'Compact',
    desc: 'Dense two-up grid — everything visible without scrolling much.',
    build: ids => buildFromSpec([[[0], [1]], [[2], [3]], [[6], [7]], [[5], [9]], [[8], [4]]], ids),
  },
  {
    id: 'overview',
    name: 'Overview',
    desc: 'Balanced read: KPIs, performance + allocation, holdings + ledger, risk + health, insights + rebalance.',
    build: ids => buildFromSpec([[[0]], [[1], [2]], [[3], [5]], [[6], [7]], [[9], [4]], [[8]]], ids),
  },
];
