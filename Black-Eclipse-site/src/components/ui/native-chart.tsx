'use client';

import React, { useRef, useState, useEffect } from 'react';
import { Candle, Position, JournalTrade } from '@/lib/backtest/engine';
import { 
  Activity, MousePointer, Trash2, ArrowUpRight, Type, Circle, 
  Maximize, Check, ChevronDown, Square, Minus, ArrowRight, Grid, Play, Pause, ChevronRight, RotateCcw, PenTool, Slash, TrendingUp,
  Percent, Ruler, ZoomIn, ZoomOut, SkipForward
} from 'lucide-react';

interface NativeChartProps {
  candles: Candle[];
  activePositions?: Position[];
  closedTrades?: JournalTrade[];
  
  // Replay Props
  replayIndex?: number;
  maxReplayIndex?: number;
  isPlaying?: boolean;
  playSpeed?: number;
  onPlayPause?: () => void;
  onStepForward?: () => void;
  onReset?: () => void;
  onSetSpeed?: (speed: number) => void;
  onSetReplayIndex?: (index: number) => void;
}

interface Drawing {
  id: string;
  type: 'trend' | 'horizontal' | 'vertical' | 'fib' | 'rect' | 'arrow' | 'text' | 'circle' | 'ray' | 'ruler';
  points: { index: number; price: number }[];
  text?: string;
  color?: string;
  style?: 'solid' | 'dashed' | 'dotted';
  weight?: number;
  opacity?: number; 
  fibLevels?: number[];
}

const PALETTE = [
  { name: 'Yellow', value: '#eab308' },
  { name: 'Green', value: '#7aff78' },
  { name: 'Red', value: '#ff4a4a' },
  { name: 'Sky Blue', value: '#38bdf8' },
  { name: 'Purple', value: '#c084fc' },
  { name: 'White', value: '#ffffff' },
];

export function NativeChart({
  candles,
  activePositions = [],
  closedTrades = [],
  replayIndex = 0,
  maxReplayIndex = 0,
  isPlaying = false,
  playSpeed = 1000,
  onPlayPause,
  onStepForward,
  onReset,
  onSetSpeed,
  onSetReplayIndex
}: NativeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartAreaRef = useRef<HTMLDivElement>(null);

  // Interaction variables stored in refs to drive 60FPS animation frames
  const candleWidthRef = useRef(8);
  const scrollOffsetRef = useRef(0);
  const crosshairRef = useRef<{ x: number; y: number } | null>(null);
  const activeToolRef = useRef<'select' | 'trend' | 'horizontal' | 'vertical' | 'fib' | 'rect' | 'arrow' | 'text' | 'circle' | 'ray' | 'ruler'>('select');
  const drawingsRef = useRef<Drawing[]>([]);
  const selectedDrawingIdRef = useRef<string | null>(null);
  const activeDragHandleIndexRef = useRef<number | null>(null);

  // Temporary drawing refs
  const drawingStartRef = useRef<{ index: number; price: number } | null>(null);
  const drawingTempRef = useRef<{ index: number; price: number }[]>([]);


  // Panning variables
  const isPanning = useRef(false);
  const panStart = useRef({ mouseX: 0, scrollOffset: 0 });

  // React states (only for toolbar boundaries to trigger clean React updates)
  const [activeTool, setActiveToolState] = useState<'select' | 'trend' | 'horizontal' | 'vertical' | 'fib' | 'rect' | 'arrow' | 'text' | 'circle' | 'ray' | 'ruler'>('select');
  const [selectedColor, setSelectedColor] = useState('#eab308');
  const [colorPickerOpen, setColorPickerOpen] = useState(false);
  const [lineMenuOpen, setLineMenuOpen] = useState(false);
  const [geomMenuOpen, setGeomMenuOpen] = useState(false);
  const [showSMA20, setShowSMA20] = useState(false);
  const [showEMA9, setShowEMA9] = useState(false);
  const [selectedDrawingIdState, setSelectedDrawingIdState] = useState<string | null>(null);
  const [localReplayIndex, setLocalReplayIndex] = useState(replayIndex);
  const localReplayIndexRef = useRef(replayIndex);

  useEffect(() => {
    setLocalReplayIndex(replayIndex);
    localReplayIndexRef.current = replayIndex;
  }, [replayIndex]);

  const marginRight = 70;
  const marginBottom = 30;

  // Track state changes to sync into refs
  useEffect(() => {
    drawingsRef.current = [];
    setScrollOffset(candles.length - 1);
    requestRender();
  }, [candles]);

  const setActiveTool = (tool: typeof activeTool) => {
    activeToolRef.current = tool;
    setActiveToolState(tool);
    // Clear temp drawings
    drawingStartRef.current = null;
    drawingTempRef.current = [];
  };

  const setSelectedDrawingId = (id: string | null) => {
    selectedDrawingIdRef.current = id;
    setSelectedDrawingIdState(id);
  };

  const setScrollOffset = (val: number) => {
    scrollOffsetRef.current = Math.min(candles.length - 1, Math.max(10, val));
  };

  // Projection math references (updated on each render cycle)
  const projRef = useRef<{
    priceToY: (p: number) => number;
    yToPrice: (y: number) => number;
    indexToX: (i: number) => number;
    xToIndex: (x: number) => number;
    plotWidth: number;
    plotHeight: number;
  }>({
    priceToY: (p) => 0,
    yToPrice: (y) => 0,
    indexToX: (i) => 0,
    xToIndex: (x) => 0,
    plotWidth: 0,
    plotHeight: 0
  });

  // Calculate technical indicators
  const sma20 = React.useMemo(() => {
    if (candles.length < 20) return [];
    const sma: number[] = new Array(candles.length).fill(NaN);
    for (let i = 19; i < candles.length; i++) {
      const sum = candles.slice(i - 19, i + 1).reduce((acc, c) => acc + c.close, 0);
      sma[i] = sum / 20;
    }
    return sma;
  }, [candles]);

  const ema9 = React.useMemo(() => {
    if (candles.length < 9) return [];
    const ema: number[] = new Array(candles.length).fill(NaN);
    let prev = candles[0].close;
    ema[0] = prev;
    const k = 2 / 10;
    for (let i = 1; i < candles.length; i++) {
      const cur = candles[i].close * k + prev * (1 - k);
      ema[i] = cur;
      prev = cur;
    }
    return ema;
  }, [candles]);

  // Buttery-smooth rAF draw loop
  const renderPending = useRef(false);
  const requestRender = () => {
    if (renderPending.current) return;
    renderPending.current = true;
    requestAnimationFrame(() => {
      renderPending.current = false;
      drawCanvas();
    });
  };

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas || candles.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas dimensions
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;

    const plotWidth = canvas.width - marginRight;
    const plotHeight = canvas.height - marginBottom;

    const candleWidth = candleWidthRef.current;
    const scrollOffset = scrollOffsetRef.current;
    const drawings = drawingsRef.current;
    const selectedDrawingId = selectedDrawingIdRef.current;
    const drawingStart = drawingStartRef.current;
    const drawingTemp = drawingTempRef.current;
    const crosshair = crosshairRef.current;
    const activeTool = activeToolRef.current;

    // Coordinate Math
    const maxVisibleCandles = Math.ceil(plotWidth / candleWidth);
    const endIdx = Math.min(candles.length - 1, Math.max(0, Math.floor(scrollOffset)));
    const startIdx = Math.max(0, endIdx - maxVisibleCandles);

    const visibleCandles = candles.slice(startIdx, endIdx + 1);
    if (visibleCandles.length === 0) return;

    const maxPrice = Math.max(...visibleCandles.map(c => c.high)) * 1.002;
    const minPrice = Math.min(...visibleCandles.map(c => c.low)) * 0.998;
    const priceRange = maxPrice - minPrice;

    const priceToY = (price: number) => {
      return plotHeight - ((price - minPrice) / (priceRange || 1)) * (plotHeight - 30) - 15;
    };

    const yToPrice = (y: number) => {
      return maxPrice - ((y - 15) / (plotHeight - 30)) * priceRange;
    };

    const indexToX = (idx: number) => {
      return plotWidth - (endIdx - idx) * candleWidth - candleWidth / 2;
    };

    const xToIndex = (x: number) => {
      return endIdx - (plotWidth - x - candleWidth / 2) / candleWidth;
    };

    projRef.current = { priceToY, yToPrice, indexToX, xToIndex, plotWidth, plotHeight };

    // Background fill
    ctx.fillStyle = '#070707';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid lines
    ctx.strokeStyle = '#141414';
    ctx.lineWidth = 1;

    // Horizontal Price Lines
    const gridRows = 7;
    for (let i = 0; i <= gridRows; i++) {
      const y = (plotHeight / gridRows) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotWidth, y);
      ctx.stroke();

      // Label price scale
      ctx.fillStyle = '#555';
      ctx.font = '9px monospace';
      ctx.fillText(yToPrice(y).toFixed(2), plotWidth + 6, y + 3);
    }

    // Vertical Time Grid Lines
    const visibleCount = endIdx - startIdx;
    const step = Math.max(1, Math.floor(visibleCount / 8));
    for (let i = startIdx; i <= endIdx; i += step) {
      const x = indexToX(i);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, plotHeight);
      ctx.stroke();

      ctx.fillStyle = '#555';
      ctx.font = '9px monospace';
      const label = candles[i]?.date || '';
      ctx.fillText(label, x - 20, plotHeight + 15);
    }

    // Render Candles
    for (let i = startIdx; i <= endIdx; i++) {
      const c = candles[i];
      const x = indexToX(i);
      const yOpen = priceToY(c.open);
      const yClose = priceToY(c.close);
      const yHigh = priceToY(c.high);
      const yLow = priceToY(c.low);

      const isBullish = c.close >= c.open;
      const color = isBullish ? '#7aff78' : '#ff4a4a';

      // Wicks
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, yHigh);
      ctx.lineTo(x, yLow);
      ctx.stroke();

      // Bodies
      ctx.fillStyle = color;
      const bodyWidth = Math.max(2, candleWidth - 2);
      ctx.fillRect(x - bodyWidth / 2, Math.min(yOpen, yClose), bodyWidth, Math.max(1, Math.abs(yClose - yOpen)));

      // Volume histogram
      const maxVol = Math.max(...visibleCandles.map(v => v.volume)) || 1;
      const volHeight = (c.volume / maxVol) * (plotHeight * 0.12);
      ctx.fillStyle = isBullish ? 'rgba(122, 255, 120, 0.05)' : 'rgba(255, 74, 74, 0.05)';
      ctx.fillRect(x - bodyWidth / 2, plotHeight - volHeight, bodyWidth, volHeight);
    }

    // SMA 20
    if (showSMA20 && sma20.length > 0) {
      ctx.strokeStyle = '#eab308';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let first = true;
      for (let i = startIdx; i <= endIdx; i++) {
        if (isNaN(sma20[i])) continue;
        const x = indexToX(i);
        const y = priceToY(sma20[i]);
        if (first) { ctx.moveTo(x, y); first = false; }
        else { ctx.lineTo(x, y); }
      }
      ctx.stroke();
    }

    // EMA 9
    if (showEMA9 && ema9.length > 0) {
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let first = true;
      for (let i = startIdx; i <= endIdx; i++) {
        if (isNaN(ema9[i])) continue;
        const x = indexToX(i);
        const y = priceToY(ema9[i]);
        if (first) { ctx.moveTo(x, y); first = false; }
        else { ctx.lineTo(x, y); }
      }
      ctx.stroke();
    }

    // Render Active Positions Brackets
    activePositions.forEach((pos, idx) => {
      const yEntry = priceToY(pos.entryPrice);
      const isLong = pos.direction === 'LONG';
      const themeColor = isLong ? '#7aff78' : '#ff4a4a';

      // TP Range Shading
      if (pos.takeProfit) {
        const yTP = priceToY(pos.takeProfit);
        ctx.fillStyle = isLong ? 'rgba(122, 255, 120, 0.03)' : 'rgba(255, 74, 74, 0.03)';
        ctx.fillRect(0, Math.min(yEntry, yTP), plotWidth, Math.abs(yEntry - yTP));

        ctx.strokeStyle = isLong ? 'rgba(122, 255, 120, 0.25)' : 'rgba(255, 74, 74, 0.25)';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(0, yTP);
        ctx.lineTo(plotWidth, yTP);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = isLong ? '#7aff78' : '#ff4a4a';
        ctx.font = '8px monospace';
        ctx.fillText(`TP ${idx + 1}: $${pos.takeProfit.toFixed(2)}`, 10, yTP - 4);
      }

      // SL Range Shading
      if (pos.stopLoss) {
        const ySL = priceToY(pos.stopLoss);
        ctx.fillStyle = isLong ? 'rgba(255, 74, 74, 0.03)' : 'rgba(122, 255, 120, 0.03)';
        ctx.fillRect(0, Math.min(yEntry, ySL), plotWidth, Math.abs(yEntry - ySL));

        ctx.strokeStyle = isLong ? 'rgba(255, 74, 74, 0.25)' : 'rgba(122, 255, 120, 0.25)';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(0, ySL);
        ctx.lineTo(plotWidth, ySL);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = isLong ? '#ff4a4a' : '#7aff78';
        ctx.font = '8px monospace';
        ctx.fillText(`SL ${idx + 1}: $${pos.stopLoss.toFixed(2)}${pos.trailingStopEnabled ? ' (TSL)' : ''}`, 10, ySL - 4);
      }

      // Entry Horizontal line
      ctx.strokeStyle = themeColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, yEntry);
      ctx.lineTo(plotWidth, yEntry);
      ctx.stroke();
    });

    // Render Closed Trades Map
    closedTrades.forEach((trade) => {
      const entryIdx = candles.findIndex(c => c.date === trade.entryDate);
      const exitIdx = candles.findIndex(c => c.date === trade.exitDate);

      if (entryIdx !== -1 && exitIdx !== -1 && entryIdx >= startIdx && exitIdx <= endIdx) {
        const x1 = indexToX(entryIdx);
        const y1 = priceToY(trade.entryPrice);
        const x2 = indexToX(exitIdx);
        const y2 = priceToY(trade.exitPrice);

        const isWin = trade.pnl >= 0;
        const color = isWin ? '#7aff78' : '#ff4a4a';

        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.setLineDash([]);

        // Entry Triangle
        ctx.fillStyle = trade.direction === 'LONG' ? '#7aff78' : '#ff4a4a';
        ctx.beginPath();
        ctx.moveTo(x1, y1 + 5);
        ctx.lineTo(x1 - 4, y1 + 12);
        ctx.lineTo(x1 + 4, y1 + 12);
        ctx.closePath();
        ctx.fill();

        // Exit Triangle
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x2, y2 - 5);
        ctx.lineTo(x2 - 4, y2 - 12);
        ctx.lineTo(x2 + 4, y2 - 12);
        ctx.closePath();
        ctx.fill();
      }
    });

    // Render Drawings
    drawings.forEach((draw) => {
      const isSelected = draw.id === selectedDrawingId;
      const drawColor = isSelected ? (draw.color || selectedColor) : '#666666';
      ctx.strokeStyle = drawColor;
      ctx.lineWidth = draw.weight || 2;
      ctx.fillStyle = drawColor;

      if (draw.style === 'dashed') ctx.setLineDash([6, 6]);
      else if (draw.style === 'dotted') ctx.setLineDash([2, 3]);
      else ctx.setLineDash([]);

      const drawItem = (item: { index: number; price: number }) => {
        const x = indexToX(item.index);
        const y = priceToY(item.price);
        return { x, y };
      };

      if (draw.type === 'horizontal') {
        const pt = drawItem(draw.points[0]);
        ctx.beginPath();
        ctx.moveTo(0, pt.y);
        ctx.lineTo(plotWidth, pt.y);
        ctx.stroke();
      } else if (draw.type === 'vertical') {
        const pt = drawItem(draw.points[0]);
        ctx.beginPath();
        ctx.moveTo(pt.x, 0);
        ctx.lineTo(pt.x, plotHeight);
        ctx.stroke();
      } else if (draw.type === 'trend' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        ctx.beginPath();
        ctx.moveTo(pt1.x, pt1.y);
        ctx.lineTo(pt2.x, pt2.y);
        ctx.stroke();
      } else if (draw.type === 'ray' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        const angle = Math.atan2(pt2.y - pt1.y, pt2.x - pt1.x);
        ctx.beginPath();
        ctx.moveTo(pt1.x, pt1.y);
        ctx.lineTo(pt1.x + Math.cos(angle) * plotWidth * 2, pt1.y + Math.sin(angle) * plotWidth * 2);
        ctx.stroke();
      } else if (draw.type === 'arrow' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        ctx.beginPath();
        ctx.moveTo(pt1.x, pt1.y);
        ctx.lineTo(pt2.x, pt2.y);
        ctx.stroke();
        const angle = Math.atan2(pt2.y - pt1.y, pt2.x - pt1.x);
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(pt2.x, pt2.y);
        ctx.lineTo(pt2.x - 12 * Math.cos(angle - Math.PI / 6), pt2.y - 12 * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(pt2.x - 12 * Math.cos(angle + Math.PI / 6), pt2.y - 12 * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fill();
      } else if (draw.type === 'rect' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        let op = '13';
        if (draw.opacity === 1) op = '06';
        if (draw.opacity === 3) op = '40';
        ctx.fillStyle = drawColor + op;
        const x = Math.min(pt1.x, pt2.x);
        const y = Math.min(pt1.y, pt2.y);
        const w = Math.abs(pt2.x - pt1.x);
        const h = Math.abs(pt2.y - pt1.y);
        ctx.fillRect(x, y, w, h);
        ctx.strokeRect(x, y, w, h);
      } else if (draw.type === 'circle' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        const radius = Math.sqrt(Math.pow(pt2.x - pt1.x, 2) + Math.pow(pt2.y - pt1.y, 2));
        ctx.beginPath();
        ctx.arc(pt1.x, pt1.y, radius, 0, 2 * Math.PI);
        ctx.stroke();
      } else if (draw.type === 'text') {
        const pt = drawItem(draw.points[0]);
        ctx.fillStyle = '#ffffff';
        ctx.font = '12px monospace';
        ctx.fillText(draw.text || '', pt.x + 8, pt.y - 4);
        ctx.fillStyle = draw.color || selectedColor;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, 2 * Math.PI);
        ctx.fill();
      } else if (draw.type === 'fib' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        const diff = draw.points[1].price - draw.points[0].price;
        const levels = draw.fibLevels || [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
        levels.forEach((lvl) => {
          const y = priceToY(draw.points[0].price + diff * lvl);
          ctx.strokeStyle = drawColor + '55';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(Math.min(pt1.x, pt2.x), y);
          ctx.lineTo(plotWidth, y);
          ctx.stroke();
          ctx.fillStyle = drawColor;
          ctx.font = '8px monospace';
          ctx.fillText(`${(lvl * 100).toFixed(1)}% ($${(draw.points[0].price + diff * lvl).toFixed(2)})`, Math.min(pt1.x, pt2.x) + 4, y - 2);
        });
      } else if (draw.type === 'ruler' && draw.points.length === 2) {
        const pt1 = drawItem(draw.points[0]);
        const pt2 = drawItem(draw.points[1]);
        
        // Shading box
        ctx.fillStyle = 'rgba(122, 255, 120, 0.06)';
        const rx = Math.min(pt1.x, pt2.x);
        const ry = Math.min(pt1.y, pt2.y);
        const rw = Math.abs(pt2.x - pt1.x);
        const rh = Math.abs(pt2.y - pt1.y);
        ctx.fillRect(rx, ry, rw, rh);
        
        // Dotted borders
        ctx.strokeStyle = drawColor;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([3, 3]);
        ctx.strokeRect(rx, ry, rw, rh);
        ctx.setLineDash([]);
        
        // Calculations
        const p1 = draw.points[0].price;
        const p2 = draw.points[1].price;
        const pDiff = p2 - p1;
        const pPct = (pDiff / p1) * 100;
        const bars = Math.abs(draw.points[1].index - draw.points[0].index);
        
        // Floating card in center
        ctx.fillStyle = '#0c0c0c';
        const textW = 105;
        const textH = 32;
        const centerX = rx + rw / 2 - textW / 2;
        const centerY = ry + rh / 2 - textH / 2;
        
        ctx.beginPath();
        // Safe check for Canvas roundRect support
        if ((ctx as any).roundRect) {
          (ctx as any).roundRect(centerX, centerY, textW, textH, 4);
        } else {
          ctx.rect(centerX, centerY, textW, textH);
        }
        ctx.fill();
        ctx.strokeStyle = drawColor;
        ctx.lineWidth = 1;
        ctx.stroke();
        
        ctx.fillStyle = '#ffffff';
        ctx.font = '8px monospace';
        ctx.fillText(`${pDiff >= 0 ? '+' : ''}${pDiff.toFixed(2)} (${pDiff >= 0 ? '+' : ''}${pPct.toFixed(2)}%)`, centerX + 6, centerY + 12);
        ctx.fillStyle = '#777';
        ctx.fillText(`${bars} Bars`, centerX + 6, centerY + 24);
      }

      ctx.setLineDash([]);

      // Selected Draw handles
      if (draw.id === selectedDrawingId) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.fillStyle = '#00f0ff';
        draw.points.forEach((pt) => {
          const sPt = drawItem(pt);
          ctx.fillRect(sPt.x - 3, sPt.y - 3, 6, 6);
          ctx.strokeRect(sPt.x - 3, sPt.y - 3, 6, 6);
        });
      }
    });

    // Preview
    if (drawingStart && drawingTemp.length === 2) {
      const pt1 = indexToX(drawingTemp[0].index);
      const pt1Y = priceToY(drawingTemp[0].price);
      const pt2 = indexToX(drawingTemp[1].index);
      const pt2Y = priceToY(drawingTemp[1].price);

      ctx.strokeStyle = selectedColor;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);

      if (activeTool === 'trend' || activeTool === 'ray') {
        ctx.beginPath();
        ctx.moveTo(pt1, pt1Y);
        ctx.lineTo(pt2, pt2Y);
        ctx.stroke();
      } else if (activeTool === 'rect' || activeTool === 'ruler') {
        const x = Math.min(pt1, pt2);
        const y = Math.min(pt1Y, pt2Y);
        const w = Math.abs(pt2 - pt1);
        const h = Math.abs(pt2Y - pt1Y);
        ctx.strokeRect(x, y, w, h);
      } else if (activeTool === 'circle') {
        const radius = Math.sqrt(Math.pow(pt2 - pt1, 2) + Math.pow(pt2Y - pt1Y, 2));
        ctx.beginPath();
        ctx.arc(pt1, pt1Y, radius, 0, 2 * Math.PI);
        ctx.stroke();
      }

      ctx.setLineDash([]);
    }

    // Crosshairs
    if (crosshair && crosshair.x < plotWidth && crosshair.y < plotHeight) {
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);

      ctx.beginPath();
      ctx.moveTo(crosshair.x, 0);
      ctx.lineTo(crosshair.x, plotHeight);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(0, crosshair.y);
      ctx.lineTo(plotWidth, crosshair.y);
      ctx.stroke();

      ctx.setLineDash([]);

      const hoveredIdx = Math.round(xToIndex(crosshair.x));
      const hoveredPrice = yToPrice(crosshair.y);

      if (candles[hoveredIdx]) {
        ctx.fillStyle = '#141414';
        ctx.fillRect(crosshair.x - 45, plotHeight, 90, 16);
        ctx.fillStyle = '#fff';
        ctx.font = '9px monospace';
        ctx.fillText(candles[hoveredIdx].date, crosshair.x - 40, plotHeight + 11);
      }

      ctx.fillStyle = '#141414';
      ctx.fillRect(plotWidth, crosshair.y - 8, marginRight, 16);
      ctx.fillStyle = '#fff';
      ctx.font = '9px monospace';
      ctx.fillText(hoveredPrice.toFixed(2), plotWidth + 6, crosshair.y + 3);
    }
  };

  // Interaction Events Handler
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleMouseDown = (e: MouseEvent) => {
      if (!canvas.contains(e.target as Node)) return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const { priceToY, yToPrice, indexToX, xToIndex, plotWidth, plotHeight } = projRef.current;

      if (x > plotWidth || y > plotHeight) return;

      const activeTool = activeToolRef.current;
      const drawings = drawingsRef.current;
      const selectedDrawingId = selectedDrawingIdRef.current;

      // Handle dragging resize handles
      if (selectedDrawingId) {
        const draw = drawings.find(d => d.id === selectedDrawingId);
        if (draw) {
          for (let i = 0; i < draw.points.length; i++) {
            const hPt = draw.points[i];
            const hX = indexToX(hPt.index);
            const hY = priceToY(hPt.price);
            const dist = Math.sqrt(Math.pow(x - hX, 2) + Math.pow(y - hY, 2));
            if (dist < 8) {
              activeDragHandleIndexRef.current = i;
              return;
            }
          }
        }
      }

      if (activeTool === 'select') {
        // Find segment click hit
        let clickedId: string | null = null;
        for (const draw of drawings) {
          if (draw.points.length > 0) {
            const pt1X = indexToX(draw.points[0].index);
            const pt1Y = priceToY(draw.points[0].price);
            const dStart = Math.sqrt(Math.pow(x - pt1X, 2) + Math.pow(y - pt1Y, 2));
            if (dStart < 12) {
              clickedId = draw.id;
              break;
            }

            if (draw.points.length === 2) {
              const pt2X = indexToX(draw.points[1].index);
              const pt2Y = priceToY(draw.points[1].price);
              
              const A = x - pt1X;
              const B = y - pt1Y;
              const C = pt2X - pt1X;
              const D = pt2Y - pt1Y;
              const dot = A * C + B * D;
              const lenSq = C * C + D * D;
              let param = -1;
              if (lenSq !== 0) param = dot / lenSq;

              let xx, yy;
              if (param < 0) {
                xx = pt1X; yy = pt1Y;
              } else if (param > 1) {
                xx = pt2X; yy = pt2Y;
              } else {
                xx = pt1X + param * C;
                yy = pt1Y + param * D;
              }

              const distSegment = Math.sqrt(Math.pow(x - xx, 2) + Math.pow(y - yy, 2));
              if (distSegment < 8) {
                clickedId = draw.id;
                break;
              }
            }
          }
        }

        setSelectedDrawingId(clickedId);
        if (clickedId) {
          requestRender();
          return;
        }

        // Trigger pan scroll
        isPanning.current = true;
        panStart.current = { mouseX: e.clientX, scrollOffset: scrollOffsetRef.current };
      } else {
        // Draw creation
        const index = Math.round(xToIndex(x));
        const price = yToPrice(y);

        if (activeTool === 'horizontal') {
          const newD: Drawing = { id: `horiz-${Date.now()}`, type: 'horizontal', points: [{ index, price }], color: selectedColor, style: 'solid', weight: 2 };
          drawingsRef.current = [...drawings, newD];
          setActiveTool('select');
          setSelectedDrawingId(newD.id);
        } else if (activeTool === 'vertical') {
          const newD: Drawing = { id: `vert-${Date.now()}`, type: 'vertical', points: [{ index, price }], color: selectedColor, style: 'solid', weight: 2 };
          drawingsRef.current = [...drawings, newD];
          setActiveTool('select');
          setSelectedDrawingId(newD.id);
        } else if (activeTool === 'text') {
          const text = prompt('Enter annotation:') || '';
          if (text) {
            const newD: Drawing = { id: `text-${Date.now()}`, type: 'text', points: [{ index, price }], text, color: selectedColor };
            drawingsRef.current = [...drawings, newD];
            setSelectedDrawingId(newD.id);
          }
          setActiveTool('select');
        } else {
          if (!drawingStartRef.current) {
            drawingStartRef.current = { index, price };
            drawingTempRef.current = [{ index, price }, { index, price }];
          } else {
            const newD: Drawing = { id: `${activeTool}-${Date.now()}`, type: activeTool, points: [drawingStartRef.current, { index, price }], color: selectedColor, style: 'solid', weight: 2 };
            drawingsRef.current = [...drawings, newD];
            drawingStartRef.current = null;
            drawingTempRef.current = [];
            setActiveTool('select');
            setSelectedDrawingId(newD.id);
          }
        }
        requestRender();
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!canvas.contains(e.target as Node)) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      crosshairRef.current = { x, y };

      const { priceToY, yToPrice, indexToX, xToIndex, plotWidth, plotHeight } = projRef.current;

      // Handle hover cursor pointer feedback
      if (canvas) {
        let matched = false;
        
        // 1. Check resize handle hover cursor
        if (selectedDrawingIdRef.current) {
          const draw = drawingsRef.current.find(d => d.id === selectedDrawingIdRef.current);
          if (draw) {
            for (const hPt of draw.points) {
              const hX = indexToX(hPt.index);
              const hY = priceToY(hPt.price);
              if (Math.sqrt(Math.pow(x - hX, 2) + Math.pow(y - hY, 2)) < 8) {
                canvas.style.cursor = 'move';
                matched = true;
                break;
              }
            }
          }
        }

        // 2. Check shapes boundary hover cursor
        if (!matched && activeToolRef.current === 'select') {
          for (const draw of drawingsRef.current) {
            if (draw.points.length > 0) {
              const pt1X = indexToX(draw.points[0].index);
              const pt1Y = priceToY(draw.points[0].price);
              if (Math.sqrt(Math.pow(x - pt1X, 2) + Math.pow(y - pt1Y, 2)) < 12) {
                canvas.style.cursor = 'pointer';
                matched = true;
                break;
              }
            }
          }
        }

        if (!matched) {
          canvas.style.cursor = 'crosshair';
        }
      }

      // Handle dragging handle points
      if (selectedDrawingIdRef.current && activeDragHandleIndexRef.current !== null) {
        const index = Math.round(xToIndex(x));
        const price = yToPrice(y);
        const idx = activeDragHandleIndexRef.current;

        drawingsRef.current = drawingsRef.current.map(d => {
          if (d.id === selectedDrawingIdRef.current) {
            const pts = [...d.points];
            pts[idx] = { index, price };
            return { ...d, points: pts };
          }
          return d;
        });
        requestRender();
        return;
      }

      // Handle panning scroll
      if (isPanning.current) {
        const deltaX = e.clientX - panStart.current.mouseX;
        const deltaIndex = deltaX / candleWidthRef.current;
        setScrollOffset(panStart.current.scrollOffset - deltaIndex);
        requestRender();
        return;
      }

      // Handle temporary drawing preview update
      if (drawingStartRef.current) {
        const index = Math.round(xToIndex(x));
        const price = yToPrice(y);
        drawingTempRef.current = [drawingStartRef.current, { index, price }];
        requestRender();
        return;
      }

      requestRender();
    };

    const handleMouseUp = () => {
      isPanning.current = false;
      activeDragHandleIndexRef.current = null;
    };

    const handleWheel = (e: WheelEvent) => {
      if (!canvas.contains(e.target as Node)) return;
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
      candleWidthRef.current = Math.min(50, Math.max(3, candleWidthRef.current * zoomFactor));
      requestRender();
    };

    window.addEventListener('mousedown', handleMouseDown, true);
    window.addEventListener('mousemove', handleMouseMove, true);
    window.addEventListener('mouseup', handleMouseUp, true);
    canvas.addEventListener('wheel', handleWheel, { passive: false });

    return () => {
      window.removeEventListener('mousedown', handleMouseDown, true);
      window.removeEventListener('mousemove', handleMouseMove, true);
      window.removeEventListener('mouseup', handleMouseUp, true);
      canvas.removeEventListener('wheel', handleWheel);
    };
  }, [candles, activePositions, closedTrades, selectedColor]);



  const handleUpdateDrawingProperty = (prop: keyof Drawing, val: any) => {
    const selId = selectedDrawingIdRef.current;
    if (!selId) return;
    drawingsRef.current = drawingsRef.current.map(d => {
      if (d.id === selId) return { ...d, [prop]: val };
      return d;
    });
    requestRender();
  };

  const handleDeleteSelectedDrawing = () => {
    const selId = selectedDrawingIdRef.current;
    if (!selId) return;
    drawingsRef.current = drawingsRef.current.filter(d => d.id !== selId);
    setSelectedDrawingId(null);
    requestRender();
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch((err) => {
        console.error("Error attempting to enable fullscreen:", err);
      });
    } else {
      document.exitFullscreen();
    }
  };

  const activeSelectedDraw = drawingsRef.current.find(d => d.id === selectedDrawingIdState);

  return (
    <div ref={containerRef} className="w-full h-full relative select-none rounded-xl overflow-hidden bg-[#070707] border border-border/40 flex flex-col font-sans text-xs">
      
      {/* Top Controls Ribbon */}
      <div className="h-10 border-b border-border/30 px-3 bg-[#0c0c0c] flex items-center justify-between text-[10px] tracking-wide text-muted-foreground uppercase shrink-0 font-mono">
        <div className="flex items-center space-x-4">
          <span className="font-extrabold text-primary flex items-center tracking-widest">
            <Activity className="h-3.5 w-3.5 mr-1 animate-pulse" /> ORBIT ENGINE PRO
          </span>
          <div className="h-3 w-[1px] bg-border/40" />
          
          <button 
            onClick={() => { setShowSMA20(!showSMA20); requestRender(); }}
            className={`cursor-pointer px-2 py-0.5 border transition-all ${showSMA20 ? 'border-primary/40 bg-primary/10 text-primary font-bold' : 'border-transparent hover:text-white'}`}
          >
            SMA (20)
          </button>
          <button 
            onClick={() => { setShowEMA9(!showEMA9); requestRender(); }}
            className={`cursor-pointer px-2 py-0.5 border transition-all ${showEMA9 ? 'border-primary/40 bg-primary/10 text-primary font-bold' : 'border-transparent hover:text-white'}`}
          >
            EMA (9)
          </button>
        </div>

        <div className="flex items-center space-x-3 text-muted-foreground">
          {activeTool !== 'select' && (
            <span className="text-[9px] text-[#eab308] border border-amber-500/20 px-2 py-0.5 bg-amber-500/5 uppercase font-bold tracking-wider animate-pulse">
              [DRAWING]: {activeTool} Active
            </span>
          )}
          <button 
            onClick={toggleFullscreen}
            className="flex items-center space-x-1 hover:text-white border border-border/30 px-2 py-0.5 cursor-pointer"
            title="Fullscreen Chart"
          >
            <Maximize className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Playback Controls Bar */}
      {maxReplayIndex > 0 && onPlayPause && (
        <div className="h-9 border-b border-border/30 px-3 bg-[#0a0a0a] flex items-center gap-3 text-[10px] font-mono text-white shrink-0">
          {/* Play / Pause */}
          <button
            onClick={onPlayPause}
            className="p-1.5 rounded-lg bg-primary/10 border border-primary/25 text-primary hover:bg-primary/20 transition-all cursor-pointer"
            title={isPlaying ? 'Pause Replay' : 'Play Replay'}
          >
            {isPlaying ? <Pause size={13} className="fill-primary" /> : <Play size={13} className="fill-primary" />}
          </button>

          {/* Step Forward */}
          <button
            onClick={onStepForward}
            disabled={isPlaying || replayIndex >= maxReplayIndex}
            className="p-1 text-muted-foreground hover:text-white transition-colors disabled:opacity-35 cursor-pointer"
            title="Forward 1 Candle"
          >
            <SkipForward size={13} />
          </button>

          {/* Reset */}
          <button
            onClick={onReset}
            className="p-1 text-rose-400 hover:text-rose-300 transition-colors cursor-pointer"
            title="Reset Replay"
          >
            <RotateCcw size={11} />
          </button>

          <div className="h-4 w-[1px] bg-border/30" />

          {/* Timeline Slider */}
          <div className="flex-1 flex items-center gap-2.5">
            <input
              type="range"
              min={0}
              max={maxReplayIndex}
              value={localReplayIndex}
              onChange={(e) => {
                const v = Number(e.target.value);
                setLocalReplayIndex(v);
                localReplayIndexRef.current = v;
              }}
              onMouseUp={() => onSetReplayIndex && onSetReplayIndex(localReplayIndexRef.current)}
              onTouchEnd={() => onSetReplayIndex && onSetReplayIndex(localReplayIndexRef.current)}
              className="flex-1 h-4 cursor-ew-resize"
            />
            <span className="text-[9px] text-[#aaa] font-bold min-w-[60px] text-right shrink-0 tabular-nums">
              {localReplayIndex} / {maxReplayIndex}
            </span>
          </div>

          <div className="h-4 w-[1px] bg-border/30" />

          {/* Speed Control */}
          {onSetSpeed && (
            <div className="flex items-center gap-1.5 shrink-0 text-muted-foreground text-[9px] font-bold">
              <span>SPEED</span>
              <select
                value={playSpeed}
                onChange={(e) => onSetSpeed(Number(e.target.value))}
                className="bg-[#141414] border border-border/30 text-[9px] px-1.5 py-0.5 text-foreground rounded-lg cursor-pointer focus:outline-none"
              >
                <option value={2000}>2.0s</option>
                <option value={1000}>1.0s</option>
                <option value={500}>0.5s</option>
                <option value={200}>0.2s</option>
                <option value={100}>0.1s</option>
              </select>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 flex flex-row relative min-h-0">
        
        {/* Left Toolbar Ribbon */}
        <div className="w-[48px] border-r border-border/30 bg-[#070707] flex flex-col items-center py-4 space-y-4 shrink-0 relative z-30">
          
          {/* Select Cursor */}
          <button 
            title="Cursor Select"
            onClick={() => setActiveTool('select')}
            className={`p-2 border transition-all hover:bg-white/5 cursor-pointer ${activeTool === 'select' ? 'border-primary text-primary bg-primary/10 shadow-[0_0_8px_rgba(122,255,120,0.25)]' : 'border-transparent text-muted-foreground'}`}
          >
            <MousePointer className="h-4 w-4" />
          </button>
 
          {/* Line Tools Dropdown */}
          <div className="relative">
            <button 
              title="Lines & Rays"
              onClick={() => {
                setLineMenuOpen(!lineMenuOpen);
                setGeomMenuOpen(false);
                setColorPickerOpen(false);
              }}
              className={`p-2 border transition-all hover:bg-white/5 cursor-pointer flex items-center justify-center ${['trend', 'ray', 'arrow', 'horizontal', 'vertical', 'ruler'].includes(activeTool) ? 'border-primary text-primary bg-primary/10' : 'border-transparent text-muted-foreground'}`}
            >
              <PenTool className="h-4 w-4" />
            </button>
            
            {lineMenuOpen && (
              <div className="absolute left-12 top-0 bg-[#0d0d0d] border border-border/40 p-1 flex flex-col space-y-1 w-36 shadow-[0_4px_16px_rgba(0,0,0,0.6)] z-50 rounded-xl">
                <button 
                  onClick={() => { setActiveTool('trend'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Slash className="h-3.5 w-3.5" />
                  <span>Trend Line</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('ray'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <TrendingUp className="h-3.5 w-3.5" />
                  <span>Ray Indicator</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('arrow'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <ArrowRight className="h-3.5 w-3.5" />
                  <span>Arrow Line</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('horizontal'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Minus className="h-3.5 w-3.5" />
                  <span>Horizontal Line</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('vertical'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Minus className="h-3.5 w-3.5 rotate-90" />
                  <span>Vertical Line</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('ruler'); setLineMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Ruler className="h-3.5 w-3.5" />
                  <span>Ruler Measure</span>
                </button>
              </div>
            )}
          </div>
 
          {/* Fibonacci */}
          <button 
            title="Fibonacci Retracement"
            onClick={() => {
              setActiveTool('fib');
              setLineMenuOpen(false);
              setGeomMenuOpen(false);
              setColorPickerOpen(false);
            }}
            className={`p-2 border transition-all hover:bg-white/5 cursor-pointer ${activeTool === 'fib' ? 'border-primary text-primary bg-primary/10' : 'border-transparent text-muted-foreground'}`}
          >
            <Percent className="h-4 w-4" />
          </button>
 
          {/* Shapes Dropdown */}
          <div className="relative">
            <button 
              title="Shapes & Regions"
              onClick={() => {
                setGeomMenuOpen(!geomMenuOpen);
                setLineMenuOpen(false);
                setColorPickerOpen(false);
              }}
              className={`p-2 border transition-all hover:bg-white/5 cursor-pointer flex items-center justify-center ${['rect', 'circle'].includes(activeTool) ? 'border-primary text-primary bg-primary/10' : 'border-transparent text-muted-foreground'}`}
            >
              <Square className="h-4 w-4" />
            </button>
            
            {geomMenuOpen && (
              <div className="absolute left-12 top-0 bg-[#0d0d0d] border border-border/40 p-1 flex flex-col space-y-1 w-32 shadow-[0_4px_16px_rgba(0,0,0,0.6)] z-50 rounded-xl">
                <button 
                  onClick={() => { setActiveTool('rect'); setGeomMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Square className="h-3.5 w-3.5" />
                  <span>Rectangle</span>
                </button>
                <button 
                  onClick={() => { setActiveTool('circle'); setGeomMenuOpen(false); }}
                  className="flex items-center space-x-2 p-1.5 hover:bg-white/5 text-left text-[10px] w-full text-muted-foreground hover:text-white"
                >
                  <Circle className="h-3.5 w-3.5" />
                  <span>Circle</span>
                </button>
              </div>
            )}
          </div>
 
          {/* Text Tool */}
          <button 
            title="Text Label"
            onClick={() => {
              setActiveTool('text');
              setLineMenuOpen(false);
              setGeomMenuOpen(false);
              setColorPickerOpen(false);
            }}
            className={`p-2 border transition-all hover:bg-white/5 cursor-pointer ${activeTool === 'text' ? 'border-primary text-primary bg-primary/10' : 'border-transparent text-muted-foreground'}`}
          >
            <Type className="h-4 w-4" />
          </button>
 
          <div className="h-[1px] w-8 bg-border/20 my-1" />
 
          {/* Zoom In Tool */}
          <button 
            title="Zoom In"
            onClick={() => {
              candleWidthRef.current = Math.min(50, candleWidthRef.current * 1.25);
              requestRender();
            }}
            className="p-2 border border-transparent text-muted-foreground hover:text-white hover:bg-white/5 cursor-pointer"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
 
          {/* Zoom Out Tool */}
          <button 
            title="Zoom Out"
            onClick={() => {
              candleWidthRef.current = Math.max(3, candleWidthRef.current * 0.75);
              requestRender();
            }}
            className="p-2 border border-transparent text-muted-foreground hover:text-white hover:bg-white/5 cursor-pointer"
          >
            <ZoomOut className="h-4 w-4" />
          </button>

          <div className="h-[1px] w-8 bg-border/20 my-1" />

          {/* Color Settings Popover Trigger */}
          <div className="relative">
            <button
              title="Tool Color Picker"
              onClick={() => {
                setColorPickerOpen(!colorPickerOpen);
                setLineMenuOpen(false);
                setGeomMenuOpen(false);
              }}
              className="w-5 h-5 rounded-full border border-white/30 cursor-pointer flex items-center justify-center hover:scale-110 transition-transform shadow-[0_0_8px_rgba(255,255,255,0.1)]"
              style={{ backgroundColor: selectedColor }}
            />

            {colorPickerOpen && (
              <div className="absolute left-12 bottom-0 bg-[#0c0c0c] border border-border/40 p-2 grid grid-cols-3 gap-1.5 w-28 shadow-2xl z-50 animate-fade-in">
                {PALETTE.map((c) => (
                  <button
                    key={c.name}
                    onClick={() => {
                      setSelectedColor(c.value);
                      handleUpdateDrawingProperty('color', c.value);
                      setColorPickerOpen(false);
                    }}
                    className="w-6 h-6 rounded-full border border-black cursor-pointer flex items-center justify-center hover:scale-110 transition-all"
                    style={{ backgroundColor: c.value }}
                    title={c.name}
                  >
                    {selectedColor === c.value && (
                      <Check className="h-3 w-3 text-black font-extrabold" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Chart Canvas Screen */}
        <div ref={chartAreaRef} className="flex-1 relative bg-black/40 min-h-0">
          <canvas
            ref={canvasRef}
            className="absolute inset-0 w-full h-full block"
          />



          {/* Floating settings for selected shapes */}
          {activeSelectedDraw && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 p-2 bg-[#0c0c0c]/90 backdrop-blur-md border border-border/40 shadow-xl flex items-center gap-3 rounded-xl text-[10px] text-white font-mono z-40 select-none animate-fade-in">
              <span className="text-[9px] text-primary uppercase border-r border-border/20 pr-2 tracking-wide font-extrabold">
                {activeSelectedDraw.type} SETTINGS
              </span>
              
              <div className="flex items-center gap-1">
                <span className="text-[8px] text-muted-foreground">STYLE:</span>
                <select
                  value={activeSelectedDraw.style || 'solid'}
                  onChange={(e) => handleUpdateDrawingProperty('style', e.target.value)}
                  className="bg-[#141414] border border-border/30 px-1 py-0.5 text-[9px] rounded-xl focus:outline-none"
                >
                  <option value="solid">Solid</option>
                  <option value="dashed">Dashed</option>
                  <option value="dotted">Dotted</option>
                </select>
              </div>

              <div className="flex items-center gap-1">
                <span className="text-[8px] text-muted-foreground">WEIGHT:</span>
                <select
                  value={activeSelectedDraw.weight || 2}
                  onChange={(e) => handleUpdateDrawingProperty('weight', Number(e.target.value))}
                  className="bg-[#141414] border border-border/30 px-1 py-0.5 text-[9px] rounded-xl focus:outline-none"
                >
                  <option value={1}>1px</option>
                  <option value={2}>2px</option>
                  <option value={3}>3px</option>
                  <option value={4}>4px</option>
                </select>
              </div>

              {activeSelectedDraw.type === 'rect' && (
                <div className="flex items-center gap-1">
                  <span className="text-[8px] text-muted-foreground">OPACITY:</span>
                  <select
                    value={activeSelectedDraw.opacity || 2}
                    onChange={(e) => handleUpdateDrawingProperty('opacity', Number(e.target.value))}
                    className="bg-[#141414] border border-border/30 px-1 py-0.5 text-[9px] rounded-xl focus:outline-none"
                  >
                    <option value={1}>5% Fill</option>
                    <option value={2}>10% Fill</option>
                    <option value={3}>30% Fill</option>
                  </select>
                </div>
              )}

              {activeSelectedDraw.type === 'fib' && (
                <div className="flex items-center gap-2 border-l border-border/20 pl-2">
                  <span className="text-[8px] text-muted-foreground">LEVELS:</span>
                  {[0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0].map((lvl) => {
                    const levels = activeSelectedDraw.fibLevels || [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
                    const active = levels.includes(lvl);
                    return (
                      <label key={lvl} className="flex items-center gap-0.5 cursor-pointer text-[9px] text-muted-foreground hover:text-white">
                        <input
                          type="checkbox"
                          checked={active}
                          onChange={(e) => {
                            const nextLevels = e.target.checked
                              ? [...levels, lvl].sort((a, b) => a - b)
                              : levels.filter(l => l !== lvl);
                            handleUpdateDrawingProperty('fibLevels', nextLevels);
                          }}
                          className="accent-primary h-3 w-3"
                        />
                        <span>{lvl}</span>
                      </label>
                    );
                  })}
                </div>
              )}

              <button
                onClick={handleDeleteSelectedDrawing}
                className="p-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 font-bold px-2 transition-colors cursor-pointer text-[9px]"
              >
                Delete
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
