"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import { ChartNoAxesCombined, RotateCcw } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DEFAULT_CHART_PALETTE,
  normalizeChartColor,
  type HeatmapColors,
  type LineColors,
  type CandleColors,
} from "@/lib/chart-palette";
import { useChartPalette, useChartPaletteStore } from "@/lib/chart-palette-store";
import { useThrottledCommit } from "@/hooks/use-throttled-commit";

const CANDLE_PRESETS: { name: string; colors: CandleColors }[] = [
  { name: "Eclipse", colors: DEFAULT_CHART_PALETTE.candles },
  { name: "Black & white", colors: { up: "#ffffff", down: "#525252", neutral: "#a3a3a3" } },
  { name: "Blue & orange", colors: { up: "#38bdf8", down: "#fb923c", neutral: "#94a3b8" } },
  { name: "Violet & teal", colors: { up: "#2dd4bf", down: "#fb7185", neutral: "#a1a1aa" } },
  { name: "Sunset", colors: { up: "#fbbf24", down: "#f472b6", neutral: "#a8a29e" } },
  { name: "Neon", colors: { up: "#22d3ee", down: "#f43f5e", neutral: "#94a3b8" } },
];

const LINE_PRESETS: { name: string; colors: LineColors }[] = [
  { name: "Eclipse", colors: DEFAULT_CHART_PALETTE.lines },
  { name: "Ocean & amber", colors: { primary: "#38bdf8", series: ["#38bdf8", "#fbbf24", "#a78bfa", "#fb7185", "#2dd4bf", "#e879f9"] } },
  { name: "Violet & teal", colors: { primary: "#c084fc", series: ["#c084fc", "#2dd4bf", "#fbbf24", "#60a5fa", "#fb7185", "#fb923c"] } },
  { name: "Black & white", colors: { primary: "#fafafa", series: ["#fafafa", "#525252", "#d4d4d4", "#737373", "#b3b3b3", "#929292"] } },
  { name: "Silver", colors: { primary: "#cbd5e1", series: ["#e2e8f0", "#64748b", "#cbd5e1", "#7c8da6", "#b0bfd3", "#94a3b8"] } },
  { name: "Sunset", colors: { primary: "#fb923c", series: ["#fb923c", "#f472b6", "#fcd34d", "#c084fc", "#fb7185", "#fdba74"] } },
  { name: "Arctic", colors: { primary: "#67e8f9", series: ["#67e8f9", "#c4b5fd", "#93c5fd", "#5eead4", "#a5b4fc", "#bae6fd"] } },
  { name: "Forest", colors: { primary: "#4ade80", series: ["#4ade80", "#fb923c", "#a3e635", "#2dd4bf", "#fde047", "#bef264"] } },
  { name: "Candy", colors: { primary: "#f9a8d4", series: ["#f9a8d4", "#a5f3fc", "#d8b4fe", "#fde68a", "#bbf7d0", "#fda4af"] } },
  { name: "Neon", colors: { primary: "#a3e635", series: ["#a3e635", "#22d3ee", "#e879f9", "#facc15", "#818cf8", "#fb7185"] } },
  { name: "Blue & orange", colors: { primary: "#60a5fa", series: ["#60a5fa", "#fb923c", "#2dd4bf", "#fbbf24", "#c084fc", "#f472b6"] } },
];

const HEATMAP_PRESETS: { name: string; colors: HeatmapColors }[] = [
  { name: "Eclipse", colors: DEFAULT_CHART_PALETTE.heatmap },
  { name: "Black & white", colors: { up: "#f5f5f5", mid: "#3f3f46", down: "#525252" } },
  { name: "Red green", colors: { up: "#22c55e", mid: "#27272a", down: "#dc2626" } },
  { name: "Teal rose", colors: { up: "#2dd4bf", mid: "#27272a", down: "#fb7185" } },
  { name: "Amber slate", colors: { up: "#fbbf24", mid: "#27272a", down: "#64748b" } },
  { name: "Ocean", colors: { up: "#38bdf8", mid: "#27272a", down: "#fb7185" } },
];

function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setDraft(null);
    setInvalid(false);
  }, [value]);
  const commit = () => {
    if (draft === null) return;
    const color = normalizeChartColor(draft);
    if (!color) {
      setInvalid(true);
      return;
    }
    onChange(color);
    setDraft(null);
    setInvalid(false);
  };
  // The native picker fires on every drag tick; rate-limit the store write so
  // charts don't re-render faster than they can paint. `flush` applies the last
  // value on blur without losing it.
  const { emit, flush } = useThrottledCommit<string>(onChange, 100);
  return (
    <div className="space-y-1.5 min-w-0">
      <Label htmlFor={id} className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          type="color"
          aria-label={`${label} color picker`}
          value={value}
          className="h-9 w-11 shrink-0 cursor-pointer p-1"
          onChange={(event) => {
            emit(event.target.value);
            setDraft(null);
            setInvalid(false);
          }}
          onBlur={flush}
        />
        <Input
          id={id}
          value={draft ?? value}
          className="font-mono h-9"
          aria-invalid={invalid}
          aria-describedby={invalid ? `${id}-error` : undefined}
          spellCheck={false}
          autoComplete="off"
          onChange={(event) => { setDraft(event.target.value); setInvalid(false); }}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); commit(); }
            if (event.key === "Escape") { setDraft(null); setInvalid(false); }
          }}
        />
      </div>
      {invalid && <p id={`${id}-error`} role="alert" className="text-xs text-destructive">Use #RGB or #RRGGBB. The applied color is unchanged.</p>}
    </div>
  );
}

function PreviewFrame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <figure className="glass-card-subtle h-[124px] overflow-hidden rounded-lg border border-border/20 px-3 py-2">
      <figcaption className="mb-1 text-[10px] tracking-wide text-muted-foreground">Illustrative preview · not financial data</figcaption>
      <svg viewBox="0 0 600 90" preserveAspectRatio="none" role="img" aria-label={label} className="h-[90px] w-full text-muted-foreground">
        {children}
      </svg>
    </figure>
  );
}

function PreviewGrid() {
  return (
    <g fill="none" stroke="currentColor" strokeWidth="0.5">
      {[18, 38, 58].map((y) => <path key={y} d={`M8 ${y}H592`} opacity="0.12" vectorEffect="non-scaling-stroke" />)}
      {[104, 202, 300, 398, 496].map((x) => <path key={x} d={`M${x} 8V82`} opacity="0.08" vectorEffect="non-scaling-stroke" />)}
      <path d="M8 82H592" opacity="0.25" vectorEffect="non-scaling-stroke" />
    </g>
  );
}

function CandlePreview({ colors }: { colors: CandleColors }) {
  const closes = [51, 46, 49, 40, 35, 39, 39, 32, 27, 31, 36, 29, 24, 26, 20, 24, 24, 18, 22, 16, 21, 25, 19, 14];
  return (
    <PreviewFrame label="Candlestick preview">
      <PreviewGrid />
      {closes.map((close, i) => {
        const open = i === 0 ? 57 : closes[i - 1];
        const color = close < open ? colors.up : close > open ? colors.down : colors.neutral;
        const x = 20 + i * 24;
        const volume = 4 + Math.abs(close - open);
        return (
          <g key={i}>
            <line x1={x} y1={Math.min(open, close) - 4} x2={x} y2={Math.max(open, close) + 4} stroke={color} strokeWidth="0.8" strokeOpacity="0.8" vectorEffect="non-scaling-stroke" />
            <rect x={x - 2.5} y={Math.min(open, close)} width={5} height={Math.max(1, Math.abs(close - open))} fill={color} fillOpacity="0.85" />
            <rect x={x - 2.5} y={81 - volume} width={5} height={volume} fill={color} fillOpacity="0.22" />
          </g>
        );
      })}
    </PreviewFrame>
  );
}

function LinePreview({ colors }: { colors: LineColors }) {
  const id = useId();
  const path = "M8 55L32 53L56 56L80 47L104 49L128 43L152 45L176 36L200 39L224 32L248 36L272 30L296 33L320 24L344 27L368 22L392 25L416 19L440 24L464 18L488 21L512 14L536 18L560 12L592 15";
  return (
    <PreviewFrame label="Line chart preview">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={colors.primary} stopOpacity="0.12" />
          <stop offset="100%" stopColor={colors.primary} stopOpacity="0" />
        </linearGradient>
      </defs>
      <PreviewGrid />
      <path d={`${path}L592 63H8Z`} fill={`url(#${id})`} />
      <path d={path} fill="none" stroke={colors.primary} strokeWidth="1.25" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {colors.series.map((color, i) => (
        <path key={i} d={`M${8 + i * 98} 75h12l8 -4l8 2h12`} fill="none" stroke={color} strokeWidth="1" strokeOpacity="0.8" vectorEffect="non-scaling-stroke">
          <title>{`Series ${i + 1}`}</title>
        </path>
      ))}
    </PreviewFrame>
  );
}

function HeatmapPreview({ colors }: { colors: HeatmapColors }) {
  const groups = [
    { color: colors.down, x: 8, width: 192, split: 112 },
    { color: colors.mid, x: 202, width: 192, split: 80 },
    { color: colors.up, x: 396, width: 196, split: 118 },
  ];
  return (
    <PreviewFrame label="Heatmap preview">
      {groups.map(({ color, x, width, split }, i) => (
        <g key={i} fill={color}>
          <rect x={x} y={8} width={split} height={48} fillOpacity="0.5" />
          <rect x={x + split + 2} y={8} width={width - split - 2} height={27} fillOpacity="0.35" />
          <rect x={x + split + 2} y={37} width={width - split - 2} height={19} fillOpacity="0.22" />
          <rect x={x} y={63} width={width} height={3} fillOpacity="0.6" />
        </g>
      ))}
      <g fill="currentColor" fontSize="9" opacity="0.7">
        <text x="8" y="81">Negative</text>
        <text x="298" y="81" textAnchor="middle">Midpoint</text>
        <text x="592" y="81" textAnchor="end">Positive</text>
      </g>
    </PreviewFrame>
  );
}

export function ChartSettingsPanel() {
  const palette = useChartPalette();
  const { setSection, setSeriesColor, setPalette, resetSection, storageAvailable } = useChartPaletteStore();

  const matchesCandles = (colors: CandleColors) => JSON.stringify(palette.candles) === JSON.stringify(colors);
  const matchesLines = (colors: LineColors) => JSON.stringify(palette.lines) === JSON.stringify(colors);
  const matchesHeatmap = (colors: HeatmapColors) => JSON.stringify(palette.heatmap) === JSON.stringify(colors);

  return (
    <section className="space-y-5" aria-labelledby="chart-settings-title">
      <div>
        <h2 id="chart-settings-title" className="flex items-center gap-3 font-serif text-lg font-semibold"><ChartNoAxesCombined className="size-5 text-primary" />Charts</h2>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed">Customize chart colors per widget type. Changes apply instantly and save locally in this browser on this device, without an account or server setup.</p>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed">TradingView embeds retain their own color controls. Fund accents and saved drawings are retained.</p>
      </div>
      {!storageAvailable && <p role="status" className="text-xs text-destructive">Browser storage is unavailable. Colors apply for this session but may not survive a reload.</p>}

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium">Candlesticks & volume</h3>
          <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("candles"); }}><RotateCcw />Reset section</Button>
        </div>
        <p className="text-xs text-muted-foreground">Used by the native Eclipse chart candles, volume bars, trade replay, win/loss charts, and calendar heatmaps.</p>
        <CandlePreview colors={palette.candles} />
        <div className="grid gap-4 sm:grid-cols-3">
          <ColorPicker label="Up / positive" value={palette.candles.up} onChange={(value) => setSection("candles", { ...palette.candles, up: value })} />
          <ColorPicker label="Down / negative" value={palette.candles.down} onChange={(value) => setSection("candles", { ...palette.candles, down: value })} />
          <ColorPicker label="Neutral" value={palette.candles.neutral} onChange={(value) => setSection("candles", { ...palette.candles, neutral: value })} />
        </div>
        <CandleSwatches presetColors={CANDLE_PRESETS} onApply={(colors) => { setSection("candles", colors); }} isActive={matchesCandles} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium">Line & area charts</h3>
          <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("lines"); }}><RotateCcw />Reset section</Button>
        </div>
        <p className="text-xs text-muted-foreground">Primary line and the six-color categorical palette for multi-series charts, economic series, benchmarks, indicators, and allocation bars.</p>
        <LinePreview colors={palette.lines} />
        <div className="grid gap-4 sm:grid-cols-3">
          <ColorPicker label="Primary line" value={palette.lines.primary} onChange={(value) => setSection("lines", { ...palette.lines, primary: value })} />
          {palette.lines.series.slice(0, 3).map((color, index) => (
            <ColorPicker key={index} label={`Series ${index + 1}`} value={color} onChange={(value) => setSeriesColor(index, value)} />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {palette.lines.series.slice(3).map((color, index) => (
            <ColorPicker key={index + 3} label={`Series ${index + 4}`} value={color} onChange={(value) => setSeriesColor(index + 3, value)} />
          ))}
        </div>
        <LineSwatches presetColors={LINE_PRESETS} onApply={(colors) => { setSection("lines", colors); }} isActive={matchesLines} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium">Heatmaps & treemaps</h3>
            <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("heatmap"); }}><RotateCcw />Reset section</Button>
          </div>
          <p className="text-xs text-muted-foreground">Diverging gradient for market and portfolio treemaps, correlation matrix, and calendar intensity tiles.</p>
          <HeatmapPreview colors={palette.heatmap} />
          <div className="grid gap-4 sm:grid-cols-3">
            <ColorPicker label="Positive end" value={palette.heatmap.up} onChange={(value) => setSection("heatmap", { ...palette.heatmap, up: value })} />
            <ColorPicker label="Midpoint" value={palette.heatmap.mid} onChange={(value) => setSection("heatmap", { ...palette.heatmap, mid: value })} />
            <ColorPicker label="Negative end" value={palette.heatmap.down} onChange={(value) => setSection("heatmap", { ...palette.heatmap, down: value })} />
          </div>
          <HeatmapSwatches presetColors={HEATMAP_PRESETS} onApply={(colors) => { setSection("heatmap", colors); }} isActive={matchesHeatmap} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
        <h3 className="text-sm font-medium">All chart colors</h3>
        <p className="text-xs text-muted-foreground">Apply a coordinated look across every chart section at once.</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => { setPalette({ candles: CANDLE_PRESETS[0].colors, lines: LINE_PRESETS[0].colors, heatmap: HEATMAP_PRESETS[0].colors }); }}>
            <RotateCcw />Reset everything
          </Button>
        </div>
      </div>
    </section>
  );
}

function CandleSwatches({ presetColors, onApply, isActive }: { presetColors: typeof CANDLE_PRESETS; onApply: (colors: CandleColors) => void; isActive: (colors: CandleColors) => boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {presetColors.map((preset) => (
        <Button key={preset.name} variant="outline" size="sm" className="rounded-xl cursor-pointer" aria-pressed={isActive(preset.colors)} onClick={() => onApply(preset.colors)}>
          <span aria-hidden="true" className="flex -space-x-1">
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.up }} />
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.down }} />
          </span>
          {preset.name}
        </Button>
      ))}
    </div>
  );
}

function LineSwatches({ presetColors, onApply, isActive }: { presetColors: typeof LINE_PRESETS; onApply: (colors: LineColors) => void; isActive: (colors: LineColors) => boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {presetColors.map((preset) => (
        <Button key={preset.name} variant="outline" size="sm" className="rounded-xl cursor-pointer" aria-pressed={isActive(preset.colors)} onClick={() => onApply(preset.colors)}>
          <span aria-hidden="true" className="flex -space-x-1">
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.primary }} />
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.series[0] }} />
          </span>
          {preset.name}
        </Button>
      ))}
    </div>
  );
}

function HeatmapSwatches({ presetColors, onApply, isActive }: { presetColors: typeof HEATMAP_PRESETS; onApply: (colors: HeatmapColors) => void; isActive: (colors: HeatmapColors) => boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {presetColors.map((preset) => (
        <Button key={preset.name} variant="outline" size="sm" className="rounded-xl cursor-pointer" aria-pressed={isActive(preset.colors)} onClick={() => onApply(preset.colors)}>
          <span aria-hidden="true" className="flex -space-x-1">
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.up }} />
            <span className="size-2.5 rounded-full border border-border" style={{ backgroundColor: preset.colors.down }} />
          </span>
          {preset.name}
        </Button>
      ))}
    </div>
  );
}
