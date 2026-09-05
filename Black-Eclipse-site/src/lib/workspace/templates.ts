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
];
