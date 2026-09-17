'use client';

// ── Minimal ECharts React binding ─────────────────────────────────────────────
// Deterministic: option is applied on mount + whenever deps change; the chart
// resizes with its container and is disposed on unmount. Colors must already
// be chart-safe (use cssVarToHex/toChartColor — zrender can't parse oklch).

import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

export function useEChart(getOption: () => EChartsOption | null, deps: unknown[]) {
  const ref = useRef<HTMLDivElement | null>(null);
  const binding = useRef<{
    el: HTMLDivElement;
    chart: echarts.ECharts;
    observer: ResizeObserver;
    deps: unknown[] | null;
  } | null>(null);

  useEffect(() => () => {
    binding.current?.observer.disconnect();
    binding.current?.chart.dispose();
    binding.current = null;
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (binding.current && binding.current.el !== el) {
      binding.current.observer.disconnect();
      binding.current.chart.dispose();
      binding.current = null;
    }
    if (!el) return;
    if (!binding.current) {
      const chart = echarts.init(el);
      const observer = new ResizeObserver(() => chart.resize());
      observer.observe(el);
      binding.current = { el, chart, observer, deps: null };
    }
    const current = binding.current;
    if (current.deps && current.deps.length === deps.length && deps.every((dep, i) => Object.is(dep, current.deps![i]))) return;
    const option = getOption();
    if (option) current.chart.setOption(option, { replaceMerge: ['series'] });
    else current.chart.clear();
    current.deps = [...deps];
  });

  return ref;
}

/** Shared tooltip/grid styling matching the terminal's frosted look. */
export function baseChartOption(): EChartsOption {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans, sans-serif)' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
      borderColor: 'rgba(255,255,255,0.12)',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#e5e7eb', fontSize: 11 },
      extraCssText:
        'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
    },
  } as EChartsOption;
}

