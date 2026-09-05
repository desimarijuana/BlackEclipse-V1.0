// ── Fund-page customization definition (kernel-driven, section model) ───────
// Presets are section templates: [columnCount, ...widgetIds] per section.
// Widgets not listed in a preset append into a trailing overflow section.
import type { PageDefinition, PresetDefinition, WidgetMeta, ColumnCount } from './types';

export type FundWidgetId =
  | 'kpi-board' | 'performance' | 'allocation' | 'ai-insights'
  | 'risk-metrics' | 'health' | 'risk-radar' | 'exposure-map'
  | 'changes' | 'rebalance' | 'holdings' | 'watchlist' | 'transactions'
  | 'stress' | 'correlation' | 'tools' | 'monte-carlo' | 'cost-basis';

export const FUND_WIDGET_META: Record<FundWidgetId, WidgetMeta> = {
  'kpi-board': { label: 'KPI Board', desc: 'NAV, P/L, cash tiles', defaultSpan: 4 },
  'performance': { label: 'Performance', desc: 'NAV curve vs benchmark', defaultSpan: 3 },
  'allocation': { label: 'Allocation', desc: 'Holdings donut + list', defaultSpan: 2 },
  'ai-insights': { label: 'AI Insights', desc: 'Position signals + discuss', defaultSpan: 2 },
  'risk-metrics': { label: 'Risk Metrics', desc: 'Beta, vol, Sharpe, drawdown', defaultSpan: 3 },
  'health': { label: 'Portfolio Health', desc: 'Score gauge + breakdown', defaultSpan: 2 },
  'risk-radar': { label: 'Risk Radar', desc: 'Five-dimension posture chart', defaultSpan: 2 },
  'exposure-map': { label: 'Exposure Map', desc: 'Category treemap + brief', defaultSpan: 3 },
  'changes': { label: 'What Changed', desc: 'Recent portfolio shifts', defaultSpan: 4 },
  'rebalance': { label: 'Rebalancing', desc: 'Drift vs model targets', defaultSpan: 4 },
  'holdings': { label: 'Active Holdings', desc: 'Full holdings table', defaultSpan: 4 },
  'watchlist': { label: 'Watchlist', desc: 'Starred positions', defaultSpan: 2 },
  'transactions': { label: 'Transactions', desc: 'Recent trade ledger', defaultSpan: 3 },
  'stress': { label: 'Stress Test', desc: 'Scenario shock model', defaultSpan: 3 },
  'correlation': { label: 'Correlation', desc: 'Pearson matrix heatmap', defaultSpan: 2 },
  'tools': { label: 'Trading Tools', desc: 'What-if, sizing, alerts', defaultSpan: 4 },
  'monte-carlo': { label: 'Monte Carlo', desc: 'Projection + attribution', defaultSpan: 4 },
  'cost-basis': { label: 'Cost Basis & DCA', desc: 'Entry vs live spread', defaultSpan: 4 },
};

function fundPreset(
  id: string, name: string, desc: string,
  preview: Array<{ span: number; hidden?: boolean }>,
  sections: Array<[ColumnCount, ...string[]]>,
): PresetDefinition {
  return { id, name, desc, preview, sections };
}

export const FUND_PRESETS: PresetDefinition[] = [
  fundPreset('default', 'Classic', 'KPIs on top, charts below, tables last',
    [{ span: 4 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    [1, 'kpi-board'],
    [3, 'performance', 'risk-radar', 'watchlist'],
    [2, 'allocation', 'health'],
    [2, 'stress', 'correlation'],
    [3, 'exposure-map', 'monte-carlo', 'ai-insights'],
    [1, 'holdings'],
    [2, 'transactions', 'changes'],
    [1, 'rebalance'],
    [1, 'cost-basis'],
    [1, 'tools'],
  ]),
  fundPreset('trader', 'Trader', 'Performance & risk up top, tables at the bottom',
    [{ span: 4 }, { span: 3 }, { span: 1 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    [1, 'kpi-board'],
    [3, 'performance', 'risk-radar', 'watchlist'],
    [2, 'stress', 'correlation'],
    [1, 'risk-metrics'],
    [2, 'holdings', 'watchlist'],
    [2, 'allocation', 'health'],
    [1, 'exposure-map'],
    [2, 'changes', 'transactions'],
    [1, 'rebalance'],
    [1, 'cost-basis'],
    [1, 'monte-carlo'],
    [1, 'ai-insights'],
    [1, 'tools'],
  ]),
  fundPreset('analyst', 'Analyst', 'Big charts first — performance, exposure, Monte Carlo',
    [{ span: 4 }, { span: 3 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    [1, 'kpi-board'],
    [3, 'performance', 'risk-radar', 'watchlist'],
    [3, 'exposure-map', 'monte-carlo', 'stress'],
    [2, 'allocation', 'health'],
    [2, 'correlation', 'cost-basis'],
    [1, 'risk-metrics'],
    [1, 'holdings'],
    [2, 'transactions', 'rebalance'],
    [1, 'changes'],
    [1, 'tools'],
    [1, 'ai-insights'],
  ]),
  fundPreset('mosaic', 'Mosaic', 'Dense mixed grid — small cards beside charts',
    [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 3 }], [
    [1, 'kpi-board'],
    [2, 'performance', 'allocation'],
    [4, 'risk-radar', 'correlation', 'watchlist', 'ai-insights'],
    [2, 'health', 'stress'],
    [3, 'exposure-map', 'monte-carlo', 'cost-basis'],
    [3, 'risk-metrics', 'changes', 'rebalance'],
    [1, 'holdings'],
    [2, 'transactions', 'tools'],
  ]),
  fundPreset('split', 'Split', 'Left rail of small cards + wide chart column',
    [{ span: 4 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 3 }, { span: 3 }], [
    [1, 'kpi-board'],
    [4, 'risk-radar', 'health', 'correlation', 'watchlist'],
    [3, 'performance', 'exposure-map', 'monte-carlo'],
    [2, 'allocation', 'ai-insights'],
    [2, 'stress', 'risk-metrics'],
    [1, 'holdings'],
    [2, 'transactions', 'rebalance'],
    [1, 'changes'],
    [1, 'cost-basis'],
    [1, 'tools'],
  ]),
  fundPreset('rows', 'Rows', 'Alternating wide/narrow — magazine-style rhythm',
    [{ span: 4 }, { span: 1 }, { span: 3 }, { span: 3 }, { span: 1 }, { span: 3 }, { span: 2 }], [
    [1, 'kpi-board'],
    [4, 'performance', 'exposure-map', 'allocation', 'risk-radar'],
    [4, 'monte-carlo', 'ai-insights', 'risk-metrics', 'health'],
    [2, 'stress', 'correlation'],
    [1, 'holdings'],
    [2, 'watchlist', 'transactions'],
    [1, 'rebalance'],
    [2, 'changes', 'cost-basis'],
    [1, 'tools'],
  ]),
  fundPreset('compact', 'Compact', 'Everything half-width — dense two-column dashboard',
    [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }], [
    [1, 'kpi-board'],
    [2, 'performance', 'allocation'],
    [2, 'health', 'holdings'],
    [2, 'watchlist', 'transactions'],
    [2, 'risk-metrics', 'risk-radar'],
    [2, 'correlation', 'stress'],
    [2, 'exposure-map', 'ai-insights'],
    [2, 'monte-carlo', 'rebalance'],
    [2, 'changes', 'cost-basis'],
    [1, 'tools'],
  ]),
  fundPreset('minimal', 'Minimal', 'Just value, performance & holdings',
    [{ span: 4 }, { span: 4 }, { span: 4 }, { span: 1, hidden: true }], [
    [1, 'kpi-board'],
    [1, 'performance'],
    [1, 'holdings'],
  ]),
  fundPreset('focus', 'Focus', 'Hero chart + small risk cluster, tables tucked at bottom',
    [{ span: 4 }, { span: 4 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 2 }], [
    [1, 'kpi-board'],
    [1, 'performance'],
    [2, 'exposure-map', 'allocation'],
    [4, 'risk-radar', 'correlation', 'watchlist', 'health'],
    [2, 'monte-carlo', 'stress'],
    [2, 'risk-metrics', 'ai-insights'],
    [1, 'holdings'],
    [2, 'transactions', 'rebalance'],
    [1, 'changes'],
    [1, 'cost-basis'],
    [1, 'tools'],
  ]),
];

export const FUND_PAGE: PageDefinition = {
  pageId: 'portfolio-fund',
  storageKey: 'eclipse_fund_layout_v2', // new section-schema key (v1 layouts auto-migrate from the legacy key)
  widgets: FUND_WIDGET_META,
  presets: FUND_PRESETS,
};