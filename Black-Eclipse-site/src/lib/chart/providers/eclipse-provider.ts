'use client';

// ── Eclipse Chart Provider — native ECharts financial chart engine ──────────
// The BlackEclipse-controlled chart. Renders candlestick/OHLC/line/area with a
// volume pane, crosshair, zoom/pan, and a frosted terminal look. Phase 2 adds
// the registry-driven indicator engine with multiple panes (overlay + separate).
// It implements the ChartProvider contract so the ChartWidget can swap it for
// TradingView without changing anything else.

import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { brandUpDown, cssVarToHex } from '@/lib/chart-colors';
import { calculateIndicator } from '@/lib/chart/indicators/registry';
import type {
  ChartData, ChartDrawing, ChartIndicatorConfig, ChartProvider, ChartState, ChartType,
  IndicatorResult, Timeframe,
} from '@/lib/chart/types';

const GRID = 'rgba(255,255,255,0.04)';
const AXIS = 'rgba(160,160,160,0.8)';

interface Pane {
  id: string;
  type: 'main' | 'volume' | 'indicator';
  indicatorId?: string;
  height: number; // fraction of chart height
}

export class EclipseChartProvider implements ChartProvider {
  readonly id = 'eclipse' as const;
  readonly label = 'Eclipse Chart';

  private chart: echarts.ECharts | null = null;
  private container: HTMLElement | null = null;
  private ro: ResizeObserver | null = null;

  private state: ChartState;
  private data: ChartData | null = null;
  private indicatorResults = new Map<string, IndicatorResult>();

  constructor(initial: ChartState) {
    this.state = { ...initial };
  }

  /** Expose the live ECharts instance for the drawing overlay. */
  getEChartsInstance(): echarts.ECharts | null {
    return this.chart;
  }

  initialize(container: HTMLElement): void {
    this.container = container;
    this.chart = echarts.init(container, undefined, { renderer: 'canvas' });
    this.ro = new ResizeObserver(() => this.chart?.resize());
    this.ro.observe(container);
    this.render();
  }

  destroy(): void {
    this.ro?.disconnect();
    this.ro = null;
    this.chart?.dispose();
    this.chart = null;
    this.container = null;
  }

  setSymbol(symbol: string, market: string): void {
    this.state.symbol = symbol;
    this.state.market = market;
  }

  setTimeframe(timeframe: Timeframe): void {
    this.state.timeframe = timeframe;
  }

  setData(data: ChartData): void {
    this.data = data;
    this.recomputeIndicators();
    this.render();
  }
  addIndicator(config: ChartIndicatorConfig): void {
    if (this.state.indicators.some((i) => i.id === config.id)) return;
    this.state.indicators = [...this.state.indicators, config];
    this.recomputeIndicators();
    this.render();
  }

  removeIndicator(id: string): void {
    this.state.indicators = this.state.indicators.filter((i) => i.id !== id);
    this.indicatorResults.delete(id);
    this.render();
  }

  addDrawing(drawing: ChartDrawing): void {
    this.state.drawings = [...this.state.drawings, drawing];
    this.render();
  }
  removeDrawing(id: string): void {
    this.state.drawings = this.state.drawings.filter((d) => d.id !== id);
    this.render();
  }

  setChartType(type: ChartType): void {
    this.state.chartType = type;
    this.render();
  }

  resize(): void {
    this.chart?.resize();
  }

  getState(): ChartState {
    return { ...this.state };
  }

  restoreState(state: ChartState): void {
    this.state = { ...state };
    this.recomputeIndicators();
    this.render();
  }

  private recomputeIndicators(): void {
    this.indicatorResults.clear();
    if (!this.data) return;
    for (const cfg of this.state.indicators) {
      const result = calculateIndicator(cfg.id, this.data.bars, cfg.settings);
      if (result) this.indicatorResults.set(cfg.id, result);
    }
  }

  private render(): void {
    if (!this.chart) return;
    const data = this.data;
    if (!data || data.bars.length === 0) {
      this.chart.clear();
      return;
    }
    try {
      this.chart.setOption(this.buildOption(data), true);
    } catch (err) {
      console.error('[EclipseChart] setOption failed:', err);
    }
  }

  // Build the pane layout: main + volume + any separate-pane indicators.
  private buildPanes(): Pane[] {
    const gap = 0.02;
    const panes: Pane[] = [{ id: 'main', type: 'main', height: 0 }];
    // Volume always present.
    panes.push({ id: 'volume', type: 'volume', height: 0.16 });
    for (const cfg of this.state.indicators) {
      const result = this.indicatorResults.get(cfg.id);
      if (result && result.pane === 'separate') {
        panes.push({ id: `ind-${cfg.id}`, type: 'indicator', indicatorId: cfg.id, height: result.paneHeight ?? 0.2 });
      }
    }
    // Main takes the remaining height, minus the inter-pane gaps so the
    // stacked grids never overflow the container.
    const fixed = panes.slice(1).reduce((a, p) => a + p.height, 0);
    const gaps = (panes.length - 1) * gap;
    panes[0].height = Math.max(0.3, 1 - fixed - gaps);
    return panes;
  }

  private buildOption(data: ChartData): EChartsOption {
    const bars = data.bars;
    const dates = bars.map((b) => b.date);
    const { up, down } = brandUpDown();
    const primary = cssVarToHex('--primary', up);
    const type = this.state.chartType;
    const panes = this.buildPanes();

    // Candlestick data: [open, close, low, high] per ECharts convention.
    const candleData = bars.map((b) => [
      b.open ?? b.close,
      b.close,
      b.low ?? b.close,
      b.high ?? b.close,
    ]);
    const closes = bars.map((b) => b.close);
    const volumes = bars.map((b) => b.volume ?? 0);

    // ── Grids: one per pane, stacked vertically ────────────────────────────
    const grids: EChartsOption['grid'] = [];
    const xAxes: EChartsOption['xAxis'] = [];
    const yAxes: EChartsOption['yAxis'] = [];
    const series: echarts.SeriesOption[] = [];
    const dataZoomX: number[] = [];

    let top = 0.06;
    const gap = 0.02;
    panes.forEach((pane, idx) => {
      const h = pane.height;
      const gridIdx = idx;
      grids.push({
        left: 8, right: 8, top: `${top * 100}%`, height: `${(h - gap) * 100}%`, containLabel: true,
      });      xAxes.push({
        type: 'category', data: dates, gridIndex: gridIdx, boundaryGap: true,
        axisLine: { lineStyle: { color: GRID } },
        axisLabel: idx === panes.length - 1
          ? { color: AXIS, fontSize: 9, fontFamily: 'monospace' }
          : { show: false },
        axisTick: { show: false },
      });
      dataZoomX.push(gridIdx);

      if (pane.type === 'main') {
        yAxes.push({
          type: 'value', scale: true, gridIndex: gridIdx,
          splitLine: { lineStyle: { color: GRID } },
          axisLabel: { color: AXIS, fontSize: 9, fontFamily: 'monospace', formatter: (v: number) => this.fmt(v) },
        });
        const priceSeries = this.priceSeries(type, candleData, closes, primary, up, down);
        // Attach mark overlays from overlay-pane indicators (e.g. structure).
        if (priceSeries[0]) {
          const marks = this.collectIndicatorMarks();
          if (Object.keys(marks).length > 0) {
            priceSeries[0] = { ...priceSeries[0], ...marks };
          }
        }
        series.push(...priceSeries);
      } else if (pane.type === 'volume') {
        yAxes.push({
          type: 'value', gridIndex: gridIdx, splitNumber: 2,
          splitLine: { show: false },
          axisLabel: { color: 'rgba(160,160,160,0.5)', fontSize: 8, fontFamily: 'monospace', formatter: (v: number) => this.fmtVol(v) },
        });
        series.push({
          name: 'Volume', type: 'bar', xAxisIndex: gridIdx, yAxisIndex: gridIdx, data: volumes,
          itemStyle: { color: (p: { dataIndex: number }) => (closes[p.dataIndex] >= (bars[p.dataIndex].open ?? closes[p.dataIndex]) ? up + '55' : down + '55') },
        });
      } else if (pane.type === 'indicator' && pane.indicatorId) {
        const result = this.indicatorResults.get(pane.indicatorId);
        if (result) {
          yAxes.push({
            type: 'value', gridIndex: gridIdx, scale: true,
            min: result.yMin, max: result.yMax,
            splitLine: { lineStyle: { color: GRID } },
            axisLabel: { color: AXIS, fontSize: 8, fontFamily: 'monospace', formatter: (v: number) => this.fmt(v) },
          });
          series.push(...this.indicatorSeries(result, gridIdx, gridIdx, up, down));
        } else {
          yAxes.push({ type: 'value', gridIndex: gridIdx, splitLine: { show: false }, axisLabel: { show: false } });
        }
      }
      top += h;
    });

    return {
      backgroundColor: 'transparent',
      animation: false,
      textStyle: { fontFamily: 'var(--font-sans, sans-serif)' },
      axisPointer: {
        link: [{ xAxisIndex: 'all' }],
        label: { backgroundColor: 'rgba(15,15,15,0.9)', color: '#e5e7eb', fontSize: 10, fontFamily: 'monospace' },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: 'rgba(15,15,15,0.92)',
        borderColor: 'rgba(122,255,120,0.25)',
        textStyle: { color: '#e5e7eb', fontSize: 11, fontFamily: 'monospace' },
        formatter: (params: unknown) => this.tooltipFormatter(params, bars, data.currency),
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: 'inside', xAxisIndex: dataZoomX, start: 0, end: 100 },
        { type: 'slider', xAxisIndex: dataZoomX, height: 14, bottom: 2, borderColor: 'transparent', backgroundColor: 'rgba(255,255,255,0.02)', fillerColor: 'rgba(122,255,120,0.08)', handleStyle: { color: 'rgba(160,160,160,0.6)' } },
      ],
      series,
    } as EChartsOption;
  }

  private priceSeries(type: ChartType, candleData: number[][], closes: number[], primary: string, up: string, down: string): echarts.SeriesOption[] {
    switch (type) {
      case 'candlestick':
        return [{
          name: 'Price', type: 'candlestick', data: candleData,
          itemStyle: { color: up, color0: down, borderColor: up, borderColor0: down, borderWidth: 1 },
        }];
      case 'ohlc':
        return [{
          name: 'Price', type: 'candlestick', data: candleData,
          itemStyle: { color: 'transparent', color0: 'transparent', borderColor: up, borderColor0: down, borderWidth: 1 },
        }];
      case 'line':
        return [{
          name: 'Close', type: 'line', data: closes, showSymbol: false,
          lineStyle: { color: primary, width: 2 }, itemStyle: { color: primary },
        }];
      case 'area':
        return [{
          name: 'Close', type: 'line', data: closes, showSymbol: false,
          lineStyle: { color: primary, width: 2 }, itemStyle: { color: primary },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: primary + '55' }, { offset: 1, color: primary + '00' },
          ]) },
        }];
      default:
        return [{
          name: 'Price', type: 'candlestick', data: candleData,
          itemStyle: { color: up, color0: down, borderColor: up, borderColor0: down, borderWidth: 1 },
        }];
    }
  }

  /** Merge mark overlays from overlay-pane indicators (e.g. structure layers). */
  private collectIndicatorMarks(): Record<string, unknown> {
    const markLine: unknown[] = [];
    const markPoint: unknown[] = [];
    const markArea: unknown[] = [];
    for (const cfg of this.state.indicators) {
      const result = this.indicatorResults.get(cfg.id);
      if (!result || result.pane !== 'overlay' || !result.marks) continue;
      if (result.marks.markLine) markLine.push(...result.marks.markLine);
      if (result.marks.markPoint) markPoint.push(...result.marks.markPoint);
      if (result.marks.markArea) markArea.push(...result.marks.markArea);
    }
    const out: Record<string, unknown> = {};
    if (markLine.length) out.markLine = { silent: true, symbol: 'none', data: markLine };
    if (markPoint.length) out.markPoint = { silent: true, data: markPoint };
    if (markArea.length) out.markArea = { silent: true, data: markArea };
    return out;
  }

  private indicatorSeries(result: IndicatorResult, xIdx: number, yIdx: number, up: string, down: string): echarts.SeriesOption[] {    return result.series.map((s) => {
      const base = { xAxisIndex: xIdx, yAxisIndex: yIdx, data: s.data, name: s.label };
      if (s.kind === 'bar') {
        return {
          ...base, type: 'bar',
          itemStyle: { color: (p: { dataIndex: number }) => {
            const v = s.data[p.dataIndex];
            return v != null && v >= 0 ? up + '66' : down + '66';
          } },
        } as echarts.SeriesOption;
      }
      if (s.kind === 'band' && s.bandId) {
        // Band: render as a stacked area between this series and its partner.
        return {
          ...base, type: 'line', showSymbol: false,
          lineStyle: { color: s.color ?? '#60a5fa', width: 1 },
          areaStyle: { color: 'rgba(96,165,250,0.08)' },
        } as echarts.SeriesOption;
      }
      return {
        ...base, type: 'line', showSymbol: false,
        lineStyle: { color: s.color ?? '#60a5fa', width: 1.5 },
        itemStyle: { color: s.color ?? '#60a5fa' },
      } as echarts.SeriesOption;
    });
  }

  private tooltipFormatter(params: unknown, bars: ChartData['bars'], currency: string): string {
    const arr = (params as Array<{ axisValue: string; seriesName: string; data: unknown }>);
    const first = arr[0];
    if (!first) return '';
    const bar = bars.find((b) => b.date === first.axisValue);
    if (!bar) return '';
    const fmt = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 4 }));
    const lines = [
      `<b>${bar.date}</b>`,
      `O ${currency} ${fmt(bar.open)}`,
      `H ${currency} ${fmt(bar.high)}`,
      `L ${currency} ${fmt(bar.low)}`,
      `C ${currency} ${fmt(bar.close)}`,
    ];
    if (bar.volume != null) lines.push(`Vol ${bar.volume.toLocaleString('en-US')}`);
    return lines.join('<br/>');
  }

  private fmt(v: number): string {
    return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }
  private fmtVol(v: number): string {
    if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return String(v);
  }
}
