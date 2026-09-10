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
    desc: 'Market pulse, watchlist, chart, movers, alerts, journal.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }, { widgets: [1] }, { widgets: [10] }],
      [{ widgets: [3], weight: 1 }, { widgets: [4], weight: 2 }],
      [{ widgets: [2], weight: 2 }, { widgets: [11], weight: 1 }],
    ], ids),
  },
  {
    id: 'investor',
    name: 'Investor',
    desc: 'Portfolio, allocation, risk, news, economic calendar.',
    build: ids => buildFromSpec([
      [{ widgets: [5] }],
      [{ widgets: [6], weight: 1 }, { widgets: [7], weight: 1 }],
      [{ widgets: [8], weight: 1 }, { widgets: [9], weight: 2 }],
    ], ids),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Market pulse, watchlist, chart, news, alerts.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }, { widgets: [1] }],
      [{ widgets: [3], weight: 1 }, { widgets: [4], weight: 2 }],
      [{ widgets: [9], weight: 2 }, { widgets: [10], weight: 1 }],
    ], ids),
  },
  {
    id: 'forex',
    name: 'Forex',
    desc: 'Watchlist, chart, economic calendar, news.',
    build: ids => buildFromSpec([
      [{ widgets: [3], weight: 1 }, { widgets: [4], weight: 2 }],
      [{ widgets: [8], weight: 1 }, { widgets: [9], weight: 2 }],
    ], ids),
  },
  {
    id: 'quant',
    name: 'Quant',
    desc: 'Market pulse, movers, risk, journal.',
    build: ids => buildFromSpec([
      [{ widgets: [1] }],
      [{ widgets: [2], weight: 2 }, { widgets: [7], weight: 1 }],
      [{ widgets: [11], weight: 2 }, { widgets: [10], weight: 1 }],
    ], ids),
  },
  {
    id: 'macro',
    name: 'Macro',
    desc: 'Economic calendar, market status, news, risk.',
    build: ids => buildFromSpec([
      [{ widgets: [0] }, { widgets: [8] }],
      [{ widgets: [9], weight: 2 }, { widgets: [7], weight: 1 }],
    ], ids),
  },
];

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  return DASHBOARD_TEMPLATES.find(t => t.id === id);
}
