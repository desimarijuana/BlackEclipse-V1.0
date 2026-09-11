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
  ChartCompareSeries, ChartData, ChartDrawing, ChartIndicatorConfig, ChartProvider,
  ChartState, ChartType,
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
  // Persisted dataZoom window so re-renders (indicator add, resize, etc.)
  // don't snap the user's pan/zoom back to the full range.
  private zoomStart = 0;
  private zoomEnd = 100;
  // False until the user pans/zooms. While false, new data loads show the most
  // recent window (like TradingView) instead of the entire history, so there is
  // room to pan left.
  private userAdjustedZoom = false;
  // Live last price from /api/quote — drawn as a dashed line + tag on the main pane.
  private livePrice: number | null = null;
  // Compare overlays — extra symbols rebased to % change on the main pane.
  private compareSeries: ChartCompareSeries[] = [];
  // Right gutter (px) reserved for the live-price tag; shared with the badge.
  private readonly rightGutter = 54;

  constructor(initial: ChartState) {
    this.state = { ...initial };
  }

  /** Show the most recent ~90 bars on first load (TradingView-style). */
  private defaultZoom(bars: { length: number }): { start: number; end: number } {
    const total = bars.length;
    const visible = Math.min(90, total);
    if (total <= visible) return { start: 0, end: 100 };
    return { start: +(((total - visible) / total) * 100).toFixed(2), end: 100 };
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
    // Track the user's zoom window so re-renders preserve it.
    this.chart.on('datazoom', (e: unknown) => {
      const batch = (e as { batch?: Array<{ start?: number; end?: number }> }).batch;
      const first = batch?.[0] ?? (e as { start?: number; end?: number });
      if (first && typeof first.start === 'number') this.zoomStart = first.start;
      if (first && typeof first.end === 'number') this.zoomEnd = first.end;
      this.userAdjustedZoom = true;
    });
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
    if (this.state.symbol !== symbol || this.state.market !== market) {
      this.zoomStart = 0;
      this.zoomEnd = 100;
      this.userAdjustedZoom = false;
      this.livePrice = null;
    }
    this.state.symbol = symbol;
    this.state.market = market;
  }

  setTimeframe(timeframe: Timeframe): void {
    if (this.state.timeframe !== timeframe) {
      this.zoomStart = 0;
      this.zoomEnd = 100;
      this.userAdjustedZoom = false;
    }
    this.state.timeframe = timeframe;
  }

  setData(data: ChartData): void {
    this.data = data;
    if (!this.userAdjustedZoom) {
      const z = this.defaultZoom(data.bars);
      this.zoomStart = z.start;
      this.zoomEnd = z.end;
    }
    this.recomputeIndicators();
    this.render();
  }

  setLivePrice(price: number | null): void {
    if (price === this.livePrice) return;
    this.livePrice = price;
    this.render();
  }

  setCompare(series: ChartCompareSeries[]): void {
    this.compareSeries = series;
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

  /** Zoom the visible window in/out by a multiplicative factor around center. */
  zoomBy(factor: number): void {
    const span = this.zoomEnd - this.zoomStart;
    const center = (this.zoomStart + this.zoomEnd) / 2;
    const nextSpan = Math.max(1, Math.min(100, span * factor));
    let start = center - nextSpan / 2;
    let end = center + nextSpan / 2;
    if (start < 0) { end -= start; start = 0; }
    if (end > 100) { start -= end - 100; end = 100; }
    start = Math.max(0, start);
    this.zoomStart = start;
    this.zoomEnd = end;
    this.chart?.dispatchAction({ type: 'dataZoom', start, end });
  }

  /** Pan the visible window left/right by a fraction of the current span. */
  panBy(fraction: number): void {
    const span = this.zoomEnd - this.zoomStart;
    let start = this.zoomStart + span * fraction;
    let end = this.zoomEnd + span * fraction;
    if (start < 0) { end -= start; start = 0; }
    if (end > 100) { start -= end - 100; end = 100; }
    this.zoomStart = Math.max(0, start);
    this.zoomEnd = end;
    this.chart?.dispatchAction({ type: 'dataZoom', start: this.zoomStart, end: this.zoomEnd });
  }

  /** Reset the visible window to the full range. */
  resetZoom(): void {
    this.zoomStart = 0;
    this.zoomEnd = 100;
    this.userAdjustedZoom = true;
    this.chart?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
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
  // Heights are fractions of the AVAILABLE area (container minus top/bottom
  // margins), and are normalised so the stacked grids never overflow.
  private buildPanes(): Pane[] {
    const separate = this.state.indicators.filter((cfg) => {
      const r = this.indicatorResults.get(cfg.id);
      return r && r.pane === 'separate';
    });

    const panes: Pane[] = [{ id: 'main', type: 'main', height: 0 }];
    panes.push({ id: 'volume', type: 'volume', height: 0.14 });
    for (const cfg of separate) {
      const result = this.indicatorResults.get(cfg.id);
      panes.push({ id: `ind-${cfg.id}`, type: 'indicator', indicatorId: cfg.id, height: result?.paneHeight ?? 0.22 });
    }

    // Main pane takes whatever is left after the fixed panes, with a floor so
    // it stays the dominant pane. If there are many sub-panes, shrink them
    // proportionally so everything fits.
    const fixed = panes.slice(1).reduce((a, p) => a + p.height, 0);
    const minMain = 0.4;
    if (fixed > 1 - minMain) {
      const scale = (1 - minMain) / fixed;
      for (let i = 1; i < panes.length; i++) panes[i].height *= scale;
    }
    panes[0].height = 1 - panes.slice(1).reduce((a, p) => a + p.height, 0);
    return panes;
  }

  private buildOption(data: ChartData): EChartsOption {
    const bars = data.bars;
    // Category labels: intraday bars share a calendar date, so append the
    // bar's time to keep the axis (and hover readout) unambiguous.
    const intraday = (['1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H'] as Timeframe[]).includes(this.state.timeframe);
    const barLabel = (b: ChartData['bars'][number]): string => {
      if (!intraday || b.time == null) return b.date;
      const t = new Date(b.time);
      return `${b.date} ${String(t.getUTCHours()).padStart(2, '0')}:${String(t.getUTCMinutes()).padStart(2, '0')}`;
    };
    const dates = bars.map(barLabel);
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

    // Fold the live quote into the currently-forming (last) candle so the last
    // price line, tag, and candle body all sit at the same level — TradingView
    // does this. Without it the quote (fresher than the delayed candle) floats
    // above the last bar.
    if (this.livePrice != null && Number.isFinite(this.livePrice) && bars.length > 0) {
      const i = bars.length - 1;
      const c = candleData[i];
      candleData[i] = [
        c[0],
        this.livePrice,
        Math.min(c[2], this.livePrice),
        Math.max(c[3], this.livePrice),
      ];
      closes[i] = this.livePrice;
    }
    // ── Grids: one per pane, stacked vertically ────────────────────────────
    const grids: EChartsOption['grid'] = [];
    const xAxes: EChartsOption['xAxis'] = [];
    const yAxes: EChartsOption['yAxis'] = [];
    const series: echarts.SeriesOption[] = [];
    const dataZoomX: number[] = [];
    const titles: NonNullable<EChartsOption['title']>[] = [];

    // Vertical region available to the stacked grids: leave a small top margin
    // and reserve the bottom for the dataZoom slider so nothing overlaps.
    const topMargin = 0.03;
    const bottomMargin = 0.06;
    const available = 1 - topMargin - bottomMargin;
    const gap = 0.02;
    // Right gutter reserved for the live-price tag (TradingView-style). Applied
    // to every pane so their x-axes stay aligned.
    const rightGutter = this.rightGutter;

    let cursor = topMargin;
    panes.forEach((pane, idx) => {
      const h = pane.height * available;
      const gridIdx = idx;
      grids.push({
        left: 8, right: rightGutter, top: `${cursor * 100}%`, height: `${Math.max(0.05, h - gap * available) * 100}%`, containLabel: true,
      });
      xAxes.push({
        type: 'category', data: dates, gridIndex: gridIdx, boundaryGap: true,
        axisLine: { lineStyle: { color: GRID } },
        axisLabel: idx === panes.length - 1
          ? { color: AXIS, fontSize: 9, fontFamily: 'monospace' }
          : { show: false },
        axisTick: { show: false },
      });
      dataZoomX.push(gridIdx);

      // Pane label (small, top-left of each sub-pane) so indicators are
      // identifiable at a glance.
      const paneLabel = pane.type === 'volume'
        ? 'Volume'
        : pane.type === 'indicator' && pane.indicatorId
          ? this.indicatorResults.get(pane.indicatorId)?.series[0]?.label
          : null;
      if (paneLabel) {
        titles.push({
          text: paneLabel,
          left: 12,
          top: `${(cursor + 0.005) * 100}%`,
          textStyle: { color: 'rgba(160,160,160,0.75)', fontSize: 9, fontFamily: 'monospace', fontWeight: 'normal' },
        });
      }

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
          const liveMark = this.livePriceMarkLine(closes, up, down);
          if (liveMark) {
            const existing = (priceSeries[0] as { markLine?: { data?: unknown[] } }).markLine;
            priceSeries[0] = {
              ...priceSeries[0],
              markLine: (existing
                ? { ...existing, data: [...(existing.data ?? []), liveMark] }
                : { silent: true, symbol: 'none', data: [liveMark] }) as echarts.SeriesOption['markLine'],
            };
          }
        }
        series.push(...priceSeries);
        // Compare overlays — extra symbols rebased to the primary's first close
        // so they share the main price axis (TradingView-style relative chart).
        const primaryBase = bars[0]?.close ?? 0;
        if (primaryBase > 0) {
          for (const cmp of this.compareSeries) {
            const base = cmp.values.find((v): v is number => v != null);
            if (base == null || base === 0) continue;
            const mapped = cmp.values.map((v) => (v == null ? null : +(primaryBase * (v / base)).toFixed(4)));
            series.push({
              name: cmp.symbol, type: 'line', xAxisIndex: gridIdx, yAxisIndex: gridIdx,
              data: mapped, showSymbol: false, connectNulls: true, z: 5,
              lineStyle: { color: cmp.color, width: 1.4 },
              itemStyle: { color: cmp.color },
            });
          }
        }
        // Overlay indicators (EMA/SMA/Bollinger/VWAP…) draw on the main pane.
        for (const cfg of this.state.indicators) {
          const result = this.indicatorResults.get(cfg.id);
          if (!result || result.pane !== 'overlay') continue;
          series.push(...this.indicatorSeries(result, gridIdx, gridIdx, up, down));
        }
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
          // Attach any mark overlays the indicator declares (e.g. RSI 30/70 guides).
          const firstIdx = series.length - result.series.length;
          if (firstIdx >= 0 && series[firstIdx] && result.marks) {
            const first = series[firstIdx] as Record<string, unknown>;
            if (result.marks.markLine?.length) {
              first.markLine = { silent: true, symbol: 'none', data: result.marks.markLine };
            }
            if (result.marks.markArea?.length) {
              first.markArea = { silent: true, data: result.marks.markArea };
            }
          }
        } else {
          yAxes.push({ type: 'value', gridIndex: gridIdx, splitLine: { show: false }, axisLabel: { show: false } });
        }
      }
      cursor += h;
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
      title: titles.length > 0 ? titles : undefined,
      dataZoom: [
        { type: 'inside', xAxisIndex: dataZoomX, start: this.zoomStart, end: this.zoomEnd, zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
        { type: 'slider', xAxisIndex: dataZoomX, start: this.zoomStart, end: this.zoomEnd, height: 14, bottom: 2, borderColor: 'transparent', backgroundColor: 'rgba(255,255,255,0.02)', fillerColor: 'rgba(122,255,120,0.08)', handleStyle: { color: 'rgba(160,160,160,0.6)' } },
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

  /**
   * TradingView-style live last-price line: a dashed horizontal line at the
   * latest price with a filled price tag on the right axis.
   */
  private livePriceMarkLine(closes: number[], up: string, down: string): Record<string, unknown> | null {
    const price = this.livePrice ?? closes[closes.length - 1];
    if (price == null || !Number.isFinite(price)) return null;
    // `closes` already has the live price folded into its last slot, so compare
    // against the previous bar to decide the up/down tint.
    const ref = closes.length >= 2 ? closes[closes.length - 2] : closes[closes.length - 1];
    const color = price >= ref ? up : down;
    return {
      yAxis: price,
      lineStyle: { color, type: 'dashed', width: 1, opacity: 0.9 },
      // TradingView-style axis tag: dark pill with green/red text + border so the
      // price stays readable against the bright fill.
      label: {
        show: true,
        position: 'end',
        formatter: this.fmt(price),
        color,
        backgroundColor: 'rgba(16,16,18,0.92)',
        borderColor: color,
        borderWidth: 1,
        fontSize: 10,
        fontFamily: 'monospace',
        fontWeight: 'bold',
        padding: [3, 6],
        borderRadius: 3,
      },
    };
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
    const arr = (params as Array<{ dataIndex?: number; axisValue?: string; seriesName: string; data: unknown }>);
    const first = arr[0];
    if (!first) return '';
    // Prefer the hovered dataIndex so intraday bars (which share a date) resolve
    // to the exact candle, not the first bar of that day.
    const idx = typeof first.dataIndex === 'number' ? first.dataIndex : bars.findIndex((b) => b.date === first.axisValue);
    const bar = bars[idx];
    if (!bar) return '';
    const fmt = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 4 }));
    let stamp = bar.date;
    if (bar.time != null) {
      const t = new Date(bar.time);
      const hh = String(t.getUTCHours()).padStart(2, '0');
      const mm = String(t.getUTCMinutes()).padStart(2, '0');
      stamp = `${bar.date} ${hh}:${mm} UTC`;
    }
    const lines = [
      `<b>${stamp}</b>`,
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
