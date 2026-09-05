// ── Fund-page customization definition (kernel-driven, section model) ───────
// Presets are section templates: [columnCount, ...widgetIds] per section.
// Widgets not listed in a preset append into a trailing overflow section.
import type { PageDefinition, PresetDefinition, WidgetMeta } from './types';

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
  sections: PresetDefinition['sections'],
): PresetDefinition {
  return { id, name, desc, preview, sections };
}

export const FUND_PRESETS: PresetDefinition[] = [
  fundPreset('default', 'Classic', 'KPIs on top, charts below, tables last',
    [{ span: 4 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1, 1], elements: ['performance', 'risk-radar', 'watchlist'] },
    { widths: [1, 1], elements: ['allocation', 'health'] },
    { widths: [1, 1], elements: ['stress', 'correlation'] },
    { widths: [1, 1, 1], elements: ['exposure-map', 'monte-carlo', 'ai-insights'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['transactions', 'changes'] },
    { widths: [1], elements: ['rebalance'] },
    { widths: [1], elements: ['cost-basis'] },
    { widths: [1], elements: ['tools'] },
  ]),
  fundPreset('trader', 'Trader', 'Performance & risk up top, tables at the bottom',
    [{ span: 4 }, { span: 3 }, { span: 1 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1, 1], elements: ['performance', 'risk-radar', 'watchlist'] },
    { widths: [1, 1], elements: ['stress', 'correlation'] },
    { widths: [1], elements: ['risk-metrics'] },
    { widths: [1, 1], elements: ['holdings', 'watchlist'] },
    { widths: [1, 1], elements: ['allocation', 'health'] },
    { widths: [1], elements: ['exposure-map'] },
    { widths: [1, 1], elements: ['changes', 'transactions'] },
    { widths: [1], elements: ['rebalance'] },
    { widths: [1], elements: ['cost-basis'] },
    { widths: [1], elements: ['monte-carlo'] },
    { widths: [1], elements: ['ai-insights'] },
    { widths: [1], elements: ['tools'] },
  ]),
  fundPreset('analyst', 'Analyst', 'Big charts first — performance, exposure, Monte Carlo',
    [{ span: 4 }, { span: 3 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 4 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1, 1], elements: ['performance', 'risk-radar', 'watchlist'] },
    { widths: [1, 1, 1], elements: ['exposure-map', 'monte-carlo', 'stress'] },
    { widths: [1, 1], elements: ['allocation', 'health'] },
    { widths: [1, 1], elements: ['correlation', 'cost-basis'] },
    { widths: [1], elements: ['risk-metrics'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['transactions', 'rebalance'] },
    { widths: [1], elements: ['changes'] },
    { widths: [1], elements: ['tools'] },
    { widths: [1], elements: ['ai-insights'] },
  ]),
  fundPreset('mosaic', 'Mosaic', 'Dense mixed grid — small cards beside charts',
    [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 3 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1], elements: ['performance', 'allocation'] },
    { widths: [1, 1, 1, 1], elements: ['risk-radar', 'correlation', 'watchlist', 'ai-insights'] },
    { widths: [1, 1], elements: ['health', 'stress'] },
    { widths: [1, 1, 1], elements: ['exposure-map', 'monte-carlo', 'cost-basis'] },
    { widths: [1, 1, 1], elements: ['risk-metrics', 'changes', 'rebalance'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['transactions', 'tools'] },
  ]),
  fundPreset('split', 'Split', 'Left rail of small cards + wide chart column',
    [{ span: 4 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 3 }, { span: 3 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1, 1, 1], elements: ['risk-radar', 'health', 'correlation', 'watchlist'] },
    { widths: [1, 1, 1], elements: ['performance', 'exposure-map', 'monte-carlo'] },
    { widths: [1, 1], elements: ['allocation', 'ai-insights'] },
    { widths: [1, 1], elements: ['stress', 'risk-metrics'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['transactions', 'rebalance'] },
    { widths: [1], elements: ['changes'] },
    { widths: [1], elements: ['cost-basis'] },
    { widths: [1], elements: ['tools'] },
  ]),
  fundPreset('rows', 'Rows', 'Alternating wide/narrow — magazine-style rhythm',
    [{ span: 4 }, { span: 1 }, { span: 3 }, { span: 3 }, { span: 1 }, { span: 3 }, { span: 2 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1, 1, 1], elements: ['performance', 'exposure-map', 'allocation', 'risk-radar'] },
    { widths: [1, 1, 1, 1], elements: ['monte-carlo', 'ai-insights', 'risk-metrics', 'health'] },
    { widths: [1, 1], elements: ['stress', 'correlation'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['watchlist', 'transactions'] },
    { widths: [1], elements: ['rebalance'] },
    { widths: [1, 1], elements: ['changes', 'cost-basis'] },
    { widths: [1], elements: ['tools'] },
  ]),
  fundPreset('compact', 'Compact', 'Everything half-width — dense two-column dashboard',
    [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1, 1], elements: ['performance', 'allocation'] },
    { widths: [1, 1], elements: ['health', 'holdings'] },
    { widths: [1, 1], elements: ['watchlist', 'transactions'] },
    { widths: [1, 1], elements: ['risk-metrics', 'risk-radar'] },
    { widths: [1, 1], elements: ['correlation', 'stress'] },
    { widths: [1, 1], elements: ['exposure-map', 'ai-insights'] },
    { widths: [1, 1], elements: ['monte-carlo', 'rebalance'] },
    { widths: [1, 1], elements: ['changes', 'cost-basis'] },
    { widths: [1], elements: ['tools'] },
  ]),
  fundPreset('minimal', 'Minimal', 'Just value, performance & holdings',
    [{ span: 4 }, { span: 4 }, { span: 4 }, { span: 1, hidden: true }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1], elements: ['performance'] },
    { widths: [1], elements: ['holdings'] },
  ]),
  fundPreset('focus', 'Focus', 'Hero chart + small risk cluster, tables tucked at bottom',
    [{ span: 4 }, { span: 4 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 2 }], [
    { widths: [1], elements: ['kpi-board'] },
    { widths: [1], elements: ['performance'] },
    { widths: [1, 1], elements: ['exposure-map', 'allocation'] },
    { widths: [1, 1, 1, 1], elements: ['risk-radar', 'correlation', 'watchlist', 'health'] },
    { widths: [1, 1], elements: ['monte-carlo', 'stress'] },
    { widths: [1, 1], elements: ['risk-metrics', 'ai-insights'] },
    { widths: [1], elements: ['holdings'] },
    { widths: [1, 1], elements: ['transactions', 'rebalance'] },
    { widths: [1], elements: ['changes'] },
    { widths: [1], elements: ['cost-basis'] },
    { widths: [1], elements: ['tools'] },
  ]),
];

export const FUND_PAGE: PageDefinition = {
  pageId: 'portfolio-fund',
  storageKey: 'eclipse_fund_layout_v3', // v3 section→column→element key (older layouts auto-migrate)
  widgets: FUND_WIDGET_META,
  presets: FUND_PRESETS,
};