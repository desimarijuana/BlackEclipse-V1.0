// ── Curated workspace templates ──────────────────────────────────────────────
// Templates are generic: each takes the page's widget ids in its canonical
// registry order and arranges them into sections/columns. Missing ids are
// skipped, so a page can safely pass a shorter registry. On the track board a
// template's columns are tracks — each section's cards are balanced by the
// masonry packer so a short card never leaves a hole.

import { cloneLayout, normalizeLayout } from './ops';
import { rebalanceColumns } from './pack';
import { newId, WORKSPACE_VERSION, type WorkspaceLayout } from './types';

export interface WorkspaceTemplate {
  id: string;
  name: string;
  desc: string;
  /** widgetIds in the page's canonical order → layout */
  build: (widgetIds: string[]) => WorkspaceLayout;
}

type ColSpec = { widgets: number[]; weight?: number };
type SectionSpec = ColSpec[];

function buildFromSpec(spec: SectionSpec[], widgetIds: string[]): WorkspaceLayout {
  const sections = spec
    .map(row => {
      const columns = row
        .map(col => {
          const widgets = col.widgets
            .map(i => widgetIds[i])
            .filter((id): id is string => Boolean(id))
            .map(widgetId => ({ id: newId('wid'), widgetId, height: null as number | null }));
          return { id: newId('col'), weight: col.weight ?? 3, widgets };
        })
        .filter(c => c.widgets.length > 0);
      rebalanceColumns(columns);
      return { id: newId('sec'), columns };
    })
    .filter(s => s.columns.length > 0);
  // Round-trip through the validator so every template ships structurally clean.
  return normalizeLayout({ version: WORKSPACE_VERSION, sections }) ?? cloneLayout({ version: WORKSPACE_VERSION, sections: [] });
}

export const WORKSPACE_TEMPLATES: WorkspaceTemplate[] = [
  {
    id: 'classic',
    name: 'Classic',
    desc: 'KPIs on top, allocation & holdings mid, ledger below.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 2 }],
      [{ widgets: [1] }],
      [{ widgets: [5], weight: 2 }, { widgets: [4], weight: 1 }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
    ], ids),
  },
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Full-width performance strip, three-column live stats.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [1] }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 1 }, { widgets: [6], weight: 1 }],
      [{ widgets: [5], weight: 2 }, { widgets: [8], weight: 1 }],
      [{ widgets: [4], weight: 1 }, { widgets: [7], weight: 1 }, { widgets: [9], weight: 1 }],
    ], ids),
  },
  {
    id: 'analyst',
    name: 'Analyst',
    desc: 'Risk-first: metrics & health up top, deep dives below.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 2 }],
      [{ widgets: [1] }],
      [{ widgets: [5], weight: 2 }, { widgets: [8], weight: 1 }],
      [{ widgets: [4], weight: 1 }, { widgets: [9], weight: 2 }],
    ], ids),
  },
  {
    id: 'minimal',
    name: 'Minimal',
    desc: 'Just the essentials, two-up.',
    build: ids => buildFromSpec([
      [{ widgets: [0], weight: 2 }, { widgets: [1], weight: 3 }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 2 }],
    ], ids),
  },
  {
    id: 'executive',
    name: 'Executive',
    desc: 'Command-center: KPI strip, performance + allocation, holdings + AI, risk + health, ledger + projection.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [1], weight: 2 }, { widgets: [2], weight: 1 }],
      [{ widgets: [3], weight: 2 }, { widgets: [9], weight: 1 }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
      [{ widgets: [5], weight: 2 }, { widgets: [8], weight: 1 }],
      [{ widgets: [4] }],
    ], ids),
  },
  {
    id: 'deep-dive',
    name: 'Deep Dive',
    desc: 'Full-width performance, then allocation + holdings, risk trio, ledger, insights + rebalance.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [1] }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 2 }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }, { widgets: [8], weight: 1 }],
      [{ widgets: [5] }],
      [{ widgets: [9], weight: 2 }, { widgets: [4], weight: 1 }],
    ], ids),
  },
  {
    id: 'projection',
    name: 'Projection',
    desc: 'Future-focused: Monte Carlo front and center, allocation + risk beside it.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [8], weight: 2 }, { widgets: [2], weight: 1 }],
      [{ widgets: [1], weight: 2 }, { widgets: [6], weight: 1 }],
      [{ widgets: [3], weight: 2 }, { widgets: [9], weight: 1 }],
      [{ widgets: [5], weight: 2 }, { widgets: [7], weight: 1 }],
      [{ widgets: [4] }],
    ], ids),
  },
  {
    id: 'compact',
    name: 'Compact',
    desc: 'Dense two-up grid — everything visible without scrolling much.',
    build: ids => buildFromSpec([
      [{ widgets: [0], weight: 2 }, { widgets: [1], weight: 3 }],
      [{ widgets: [2], weight: 1 }, { widgets: [3], weight: 2 }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
      [{ widgets: [5], weight: 2 }, { widgets: [9], weight: 1 }],
      [{ widgets: [8], weight: 2 }, { widgets: [4], weight: 1 }],
    ], ids),
  },
  {
    id: 'overview',
    name: 'Overview',
    desc: 'Balanced read: KPIs, performance + allocation, holdings + ledger, risk + health, insights + rebalance.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [1], weight: 2 }, { widgets: [2], weight: 1 }],
      [{ widgets: [3], weight: 2 }, { widgets: [5], weight: 1 }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
      [{ widgets: [9], weight: 2 }, { widgets: [4], weight: 1 }],
      [{ widgets: [8] }],
    ], ids),
  },
];
