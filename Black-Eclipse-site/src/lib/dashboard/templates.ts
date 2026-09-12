// ── Dashboard persona templates ──────────────────────────────────────────────
// Onboarding picks a persona → a starting template. Templates are generic: they
// take the dashboard registry's canonical widget ids and arrange them into
// sections/columns. Missing ids are skipped. The template is ONLY a starting
// point — the user can fully modify it (spec §26, §28).

import { cloneLayout, normalizeLayout } from '@/lib/workspace/ops';
import { newId, type WorkspaceLayout } from '@/lib/workspace/types';

export interface DashboardTemplate {
  id: string;
  name: string;
  desc: string;
  /** widgetIds in the dashboard registry's canonical order → layout */
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
      return { id: newId('sec'), columns };
    })
    .filter(s => s.columns.length > 0);
  return normalizeLayout({ version: 1, sections }) ?? cloneLayout({ version: 1, sections: [] });
}

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'trader',
    name: 'Trader',
    desc: 'TradingView chart on top, indices, movers, watchlist, portfolio, news, intelligence.',
    build: ids => buildFromSpec([
      [{ widgets: [44] }],
      [{ widgets: [53] }],
      [{ widgets: [0] }, { widgets: [5] }, { widgets: [18] }],
      [{ widgets: [20], weight: 1 }, { widgets: [22], weight: 1 }, { widgets: [19], weight: 1 }],
      [{ widgets: [47] }, { widgets: [54] }],
      [{ widgets: [48], weight: 1 }, { widgets: [49], weight: 1 }, { widgets: [50], weight: 1 }],
      [{ widgets: [51], weight: 1 }, { widgets: [12], weight: 2 }, { widgets: [16], weight: 1 }],
      [{ widgets: [13], weight: 1 }, { widgets: [23], weight: 1 }],
    ], ids),
  },
  {
    id: 'investor',
    name: 'Investor',
    desc: 'Indices, portfolio, risk, news, economic calendar.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [20], weight: 1 }, { widgets: [21], weight: 1 }],
      [{ widgets: [47] }, { widgets: [54] }],
      [{ widgets: [16], weight: 1 }, { widgets: [12], weight: 2 }],
    ], ids),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Crypto markets, movers, watchlist, news.',
    build: ids => buildFromSpec([
      [{ widgets: [2] }, { widgets: [5] }],
      [{ widgets: [18], weight: 1 }, { widgets: [12], weight: 2 }],
      [{ widgets: [8], weight: 2 }, { widgets: [9], weight: 1 }],
    ], ids),
  },
  {
    id: 'forex',
    name: 'Forex',
    desc: 'Forex pairs, commodities, economic calendar, news.',
    build: ids => buildFromSpec([
      [{ widgets: [1], weight: 1 }, { widgets: [3], weight: 1 }],
      [{ widgets: [16], weight: 1 }, { widgets: [12], weight: 2 }],
    ], ids),
  },
  {
    id: 'quant',
    name: 'Quant',
    desc: 'Indices, screener, risk, movers.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }],
      [{ widgets: [15], weight: 2 }, { widgets: [21], weight: 1 }],
      [{ widgets: [5], weight: 2 }, { widgets: [4], weight: 1 }],
    ], ids),
  },
  {
    id: 'macro',
    name: 'Macro',
    desc: 'Economic calendar, indices, commodities, news.',
    build: ids => buildFromSpec([
      [{ widgets: [16] }, { widgets: [0] }],
      [{ widgets: [3], weight: 1 }, { widgets: [12], weight: 2 }],
    ], ids),
  },
];

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  return DASHBOARD_TEMPLATES.find(t => t.id === id);
}
