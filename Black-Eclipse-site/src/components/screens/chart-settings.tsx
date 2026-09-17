"use client";

import { useEffect, useId, useState } from "react";
import { ChartNoAxesCombined, RotateCcw } from "lucide-react";
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
            onChange(event.target.value);
            setDraft(null);
            setInvalid(false);
          }}
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

function CandlePreview({ colors }: { colors: CandleColors }) {
  return (
    <svg viewBox="0 0 240 120" role="img" aria-label="Candlestick preview" className="w-full h-auto">
      {[[20, 45, 75, true], [60, 30, 85, true], [100, 50, 70, false], [140, 25, 90, true], [180, 55, 65, false], [220, 35, 80, true]].map(([x, top, bottom, isUp], i) => (
        <g key={i}>
          <line x1={Number(x)} y1={Number(top) - 12} x2={Number(x)} y2={Number(top)} stroke={isUp ? colors.up : colors.down} />
          <line x1={Number(x)} y1={Number(bottom)} x2={Number(x)} y2={Math.min(110, Number(bottom) + 12)} stroke={isUp ? colors.up : colors.down} />
          <rect x={Number(x) - 8} y={Number(top)} width={16} height={Number(bottom) - Number(top)} fill={isUp ? colors.up : colors.down} />
        </g>
      ))}
    </svg>
  );
}

function LinePreview({ colors }: { colors: LineColors }) {
  return (
    <svg viewBox="0 0 240 120" role="img" aria-label="Line chart preview" className="w-full h-auto">
      <path d="M20 95L65 70L110 80L155 40L200 55L225 20" fill="none" stroke={colors.primary} strokeWidth="3" />
      <path d="M20 95L65 80L110 92L155 65L200 80L225 55" fill="none" stroke={colors.series[0]} strokeWidth="2" />
      <path d="M20 100L65 90L110 100L155 85L200 98L225 85" fill="none" stroke={colors.series[1]} strokeWidth="2" strokeDasharray="4 4" />
    </svg>
  );
}

function HeatmapPreview({ colors }: { colors: HeatmapColors }) {
  const cells = [
    [colors.down, colors.mid, colors.up, colors.mid],
    [colors.mid, colors.up, colors.up, colors.down],
    [colors.down, colors.up, colors.mid, colors.up],
    [colors.mid, colors.down, colors.mid, colors.up],
  ];
  return (
    <svg viewBox="0 0 120 120" role="img" aria-label="Heatmap preview" className="w-full h-auto">
      {cells.flatMap((row, y) => row.map((color, x) => (
        <rect key={`${x}-${y}`} x={x * 30} y={y * 30} width={28} height={28} rx={4} fill={color} />
      )))}
    </svg>
  );
}

export function ChartSettingsPanel() {
  const palette = useChartPalette();
  const { setSection, setSeriesColor, setPalette, resetSection, storageAvailable } = useChartPaletteStore();
  const [revision, setRevision] = useState(0);
  const touch = () => setRevision((value) => value + 1);

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
          <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("candles"); touch(); }}><RotateCcw />Reset section</Button>
        </div>
        <p className="text-xs text-muted-foreground">Used by the native Eclipse chart candles, volume bars, trade replay, win/loss charts, and calendar heatmaps.</p>
        <CandlePreview colors={palette.candles} />
        <div className="grid gap-4 sm:grid-cols-3">
          <ColorPicker label="Up / positive" value={palette.candles.up} onChange={(value) => setSection("candles", { ...palette.candles, up: value })} />
          <ColorPicker label="Down / negative" value={palette.candles.down} onChange={(value) => setSection("candles", { ...palette.candles, down: value })} />
          <ColorPicker label="Neutral" value={palette.candles.neutral} onChange={(value) => setSection("candles", { ...palette.candles, neutral: value })} />
        </div>
        <CandleSwatches presetColors={CANDLE_PRESETS} onApply={(colors) => { setSection("candles", colors); touch(); }} isActive={matchesCandles} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium">Line & area charts</h3>
          <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("lines"); touch(); }}><RotateCcw />Reset section</Button>
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
        <LineSwatches presetColors={LINE_PRESETS} onApply={(colors) => { setSection("lines", colors); touch(); }} isActive={matchesLines} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium">Heatmaps & treemaps</h3>
            <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => { resetSection("heatmap"); touch(); }}><RotateCcw />Reset section</Button>
          </div>
          <p className="text-xs text-muted-foreground">Diverging gradient for market and portfolio treemaps, correlation matrix, and calendar intensity tiles.</p>
          <HeatmapPreview colors={palette.heatmap} />
          <div className="grid gap-4 sm:grid-cols-3">
            <ColorPicker label="Positive end" value={palette.heatmap.up} onChange={(value) => setSection("heatmap", { ...palette.heatmap, up: value })} />
            <ColorPicker label="Midpoint" value={palette.heatmap.mid} onChange={(value) => setSection("heatmap", { ...palette.heatmap, mid: value })} />
            <ColorPicker label="Negative end" value={palette.heatmap.down} onChange={(value) => setSection("heatmap", { ...palette.heatmap, down: value })} />
          </div>
          <HeatmapSwatches presetColors={HEATMAP_PRESETS} onApply={(colors) => { setSection("heatmap", colors); touch(); }} isActive={matchesHeatmap} />
      </div>

      <div className="glass-card rounded-2xl border border-border/20 p-5 space-y-4">
        <h3 className="text-sm font-medium">All chart colors</h3>
        <p className="text-xs text-muted-foreground">Apply a coordinated look across every chart section at once.</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={() => { setPalette({ candles: CANDLE_PRESETS[0].colors, lines: LINE_PRESETS[0].colors, heatmap: HEATMAP_PRESETS[0].colors }); touch(); }}>
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
