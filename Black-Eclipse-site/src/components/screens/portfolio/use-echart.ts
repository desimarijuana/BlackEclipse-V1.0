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
  const getOptionRef = useRef(getOption);
  getOptionRef.current = getOption;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    const option = getOptionRef.current();
    if (option) chart.setOption(option);

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}

/** Shared tooltip/grid styling matching the terminal's frosted look. */
export function baseChartOption(): EChartsOption {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans, sans-serif)' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15,15,15,0.92)',
      borderWidth: 0,
      textStyle: { color: '#e5e7eb', fontSize: 11 },
    },
  } as EChartsOption;
}

