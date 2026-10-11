// ── ECharts instance registry ─────────────────────────────────────────────────
// ResponseChart registers its live ECharts instance here on mount so the export
// helpers can capture a chart as PNG (getDataURL) without threading refs through
// the whole render tree. Instances are unregistered on unmount — no leaks.

import type { ECharts } from 'echarts';

const instances = new Map<string, ECharts>();

export function registerChart(id: string, instance: ECharts): void {
  instances.set(id, instance);
}

export function unregisterChart(id: string): void {
  instances.delete(id);
}

export function getChart(id: string): ECharts | null {
  return instances.get(id) ?? null;
}
