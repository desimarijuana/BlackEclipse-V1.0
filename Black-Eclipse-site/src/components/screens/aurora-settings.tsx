"use client";

// ── Settings › Aurora ─────────────────────────────────────────────────────
// Lets the user recolor the Aurora glow. Each sentiment state (bearish /
// neutral / bullish) has a bright CORE color (the glow's center) and an EDGE
// color (the deep falloff at both ends of the ribbon). Changes apply live to
// the Aurora rendered behind the whole app and persist in localStorage.
//
// The settings dialog is a modal that covers the shell's app-wide Aurora, so
// edits here would otherwise be invisible until the user closes Settings. To
// make every edit legible in place, the Preview card mounts a REAL <Aurora>
// driven by the live regime score and the same store config, so color, motion,
// softness, detail and style all update as the sliders move.
//
// The sentiment model itself is untouched — this only swaps the palette that
// `resolveAuroraVisuals(score, palette)` interpolates between.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Palette, Sparkles, RotateCcw, Check, TrendingUp, TrendingDown, Minus,
  Spline, Grid3x3, Rows3, BarChart3, Blocks,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { SectionHeader } from "./settings-ui";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { resolveAuroraVisuals } from "@/lib/aurora-sentiment";
import Aurora from "@/components/ui/Aurora";
import { useAuroraSentiment } from "@/components/layout/aurora-glow";
import {
  AURORA_PRESETS, STATE_LABELS, STATE_ORDER,
  isValidHex, paletteMatchesPreset,
  type AuroraColorPair, type AuroraMarketState, type AuroraPalette,
} from "@/lib/aurora/theme";
import {
  AURORA_MOTION_LIMITS, AURORA_SHAPE_LIMITS, AURORA_STYLE_LIMITS, AURORA_STYLES,
  type AuroraStyleId,
} from "@/lib/aurora/config";
import { useAuroraPaletteStore } from "@/lib/aurora/store";
import { useThrottledCommit } from "@/hooks/use-throttled-commit";

const STATE_ICON: Record<AuroraMarketState, React.ElementType> = {
  bullish: TrendingUp,
  neutral: Minus,
  bearish: TrendingDown,
};

const STATE_ACCENT: Record<AuroraMarketState, string> = {
  bullish: "text-emerald-400",
  neutral: "text-muted-foreground",
  bearish: "text-rose-400",
};

const STYLE_ICON: Record<AuroraStyleId, React.ElementType> = {
  ribbon: Spline,
  dots: Grid3x3,
  scanlines: Rows3,
  pillars: BarChart3,
  blocks: Blocks,
};

/** A native color swatch + hex text input pair for one color. */
function ColorField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (hex: string) => void;
}) {
  // Local text buffer so the user can type freely; only valid hex is committed,
  // keeping invalid input from ever reaching the store or the WebGL shader.
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const valid = isValidHex(text);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // Dragging the picker fires continuously; the Aurora is WebGL, so applying on
  // every tick stalls the main thread. Rate-limit to the latest value per tick
  // window and flush on blur.
  const { emit, flush } = useThrottledCommit<string>((hex) => onChangeRef.current(hex), 100);

  const handleText = (next: string) => {
    setText(next);
    if (isValidHex(next)) emit(next.trim().toLowerCase());
  };

  return (
    <div className="flex items-center gap-3 min-w-0">
      <label
        className="relative w-9 h-9 shrink-0 rounded-xl border border-white/15 cursor-pointer overflow-hidden shadow-sm"
        style={{ backgroundColor: valid ? text : value }}
        title={`${label} — click to pick`}
      >
        <input
          type="color"
          value={valid ? text : value}
          onChange={(e) => { setText(e.target.value); emit(e.target.value); }}
          onBlur={flush}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          aria-label={`${label} color picker`}
        />
      </label>
      <div className="flex flex-col min-w-0">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="text-[10px] text-muted-foreground truncate">{hint}</span>
      </div>
      <input
        value={text}
        onChange={(e) => handleText(e.target.value)}
        spellCheck={false}
        className={cn(
          "ml-auto w-[92px] shrink-0 rounded-lg border bg-transparent px-2 py-1 font-mono text-[11px] uppercase outline-none transition-colors",
          valid
            ? "border-border/40 focus-visible:border-primary/50"
            : "border-rose-500/50 text-rose-400"
        )}
        aria-label={`${label} hex value`}
      />
    </div>
  );
}

/** Mini live preview of the resolved aurora color at a given score. */
function AuroraPreview({
  palette,
  scores,
}: {
  palette: { bullish: AuroraColorPair; neutral: AuroraColorPair; bearish: AuroraColorPair };
  scores: number[];
}) {
  return (
    <div className="flex h-16 w-full overflow-hidden rounded-xl border border-white/10">
      {scores.map((score, i) => {
        const { colorStops } = resolveAuroraVisuals(score, palette);
        const [edge, core] = colorStops;
        return (
          <div
            key={i}
            className="flex-1"
            style={{ background: `radial-gradient(120% 130% at 50% 0%, ${core} 0%, ${edge} 70%, transparent 100%)` }}
            title={score.toFixed(2)}
          />
        );
      })}
    </div>
  );
}

/** Compact bearish→neutral→bullish ramp swatch for a preset chip. */
function PresetRamp({ palette }: { palette: AuroraPalette }) {  return (
    <span
      className="h-5 w-12 shrink-0 rounded-md border border-white/15"
      style={{
        background: `linear-gradient(90deg, ${palette.bearish.core} 0%, ${palette.neutral.core} 50%, ${palette.bullish.core} 100%)`,
      }}
      aria-hidden
    />
  );
}

/** Labelled range slider with a live value readout, matching the customization panel. */
function RangeControl({
  label, hint, value, min, max, step, format, onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="text-[10px] font-mono text-muted-foreground">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full cursor-pointer"
        aria-label={label}
      />
      {hint && <span className="text-[10px] text-muted-foreground leading-snug">{hint}</span>}
    </div>
  );
}

export function AuroraSettingsPanel() {
  const palette = useAuroraPaletteStore((s) => s.palette);
  const motion = useAuroraPaletteStore((s) => s.motion);
  const shape = useAuroraPaletteStore((s) => s.shape);
  const style = useAuroraPaletteStore((s) => s.style);
  const setColor = useAuroraPaletteStore((s) => s.setColor);
  const setPalette = useAuroraPaletteStore((s) => s.setPalette);
  const setMotion = useAuroraPaletteStore((s) => s.setMotion);
  const setShape = useAuroraPaletteStore((s) => s.setShape);
  const setStyle = useAuroraPaletteStore((s) => s.setStyle);
  const resetLook = useAuroraPaletteStore((s) => s.resetLook);
  const reset = useAuroraPaletteStore((s) => s.reset);

  // The live market-regime reading, so the preview moves exactly like the real
  // app-wide glow rather than a static swatch.
  const { score, dim } = useAuroraSentiment();

  // Cap the preview box so a tall `Height` setting never blows out the modal;
  // the shader scales to its container, so the look still reads correctly.
  const previewHeight = Math.min(160, Math.max(96, shape.height));

  const previewScores = useMemo(() => [-1, -0.5, 0, 0.5, 1], []);

  // Any motion/shape/style change counts as "custom" — surface a reset
  // affordance in the Motion & Shape card header.
  const knobsCustomized =
    motion.intensity !== 1 || motion.speed !== 1 || motion.response !== 0.04 ||
    shape.height !== 224 || shape.softness !== 1 || shape.noiseScale !== 2 ||
    style.id !== "ribbon" || style.grid !== 22;
  const resetKnobs = () => resetLook();

  return (
    <div className="animate-fade-in-up">
      <SectionHeader
        icon={Palette}
        title="Aurora Colors"
        description={
          <>
            Recolor the ambient glow at the top of the terminal. Each market state has a bright
            <span className="text-foreground"> center </span> and a deep
            <span className="text-foreground"> edge</span> color; Aurora blends between them as sentiment moves.
          </>
        }
      />

      {/* Live preview */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Preview</span>
          <span className="text-[10px] text-muted-foreground font-mono">bearish → bullish</span>
        </div>
        <div className="p-4 space-y-3">
          {/* The real shader, live — so color/motion/softness/detail/style
              changes are visible without leaving the modal. */}
          <div
            className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40"
            style={{ height: previewHeight }}
          >
            <Aurora
              sentiment={score}
              dim={dim}
              palette={palette}
              smoothing={motion.response}
              intensityScale={motion.intensity}
              speedScale={motion.speed}
              softnessScale={shape.softness}
              noiseScale={shape.noiseScale}
              style={style.id}
              grid={style.grid}
            />
            <span className="absolute bottom-1.5 right-2 text-[10px] font-mono text-muted-foreground">
              live · {score >= 0 ? "+" : ""}{score.toFixed(2)}
            </span>
          </div>
          <AuroraPreview palette={palette} scores={previewScores} />
        </div>
      </div>

      {/* Presets */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
            Presets · {AURORA_PRESETS.length}
          </span>
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl h-7" onClick={reset}>
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset
          </Button>
        </div>
        <div className="p-3 grid gap-2 sm:grid-cols-2">
          {AURORA_PRESETS.map((preset) => {
            const active = paletteMatchesPreset(palette, preset.palette);
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => setPalette(preset.palette)}
                aria-pressed={active}
                title={preset.description}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer",
                  active
                    ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                    : "border-border/20 glass-card-subtle hover:border-border/40"
                )}
              >
                <PresetRamp palette={preset.palette} />
                <span className="flex flex-col min-w-0">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    {preset.label}
                    {active && <Check className="w-3 h-3 text-primary shrink-0" />}
                  </span>
                  <span className="text-[10px] text-muted-foreground truncate">{preset.description}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Style */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
            Style
          </span>
          <span className="text-[10px] text-muted-foreground font-mono">{style.id}</span>
        </div>
        <div className="p-3">
          <div className="grid gap-2 grid-cols-2 sm:grid-cols-3">
            {AURORA_STYLES.map((s) => {
              const Icon = STYLE_ICON[s.id];
              const active = style.id === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setStyle({ id: s.id })}
                  aria-pressed={active}
                  title={s.hint}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer",
                    active
                      ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                      : "border-border/20 glass-card-subtle hover:border-border/40"
                  )}
                >
                  <Icon size={16} className={active ? "text-primary" : "text-muted-foreground"} />
                  <span className="flex flex-col min-w-0">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      {s.label}
                      {active && <Check className="w-3 h-3 text-primary shrink-0" />}
                    </span>
                    <span className="text-[10px] text-muted-foreground truncate">{s.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {style.id !== "ribbon" && (
            <div className="px-2 pt-4 pb-1">
              <RangeControl
                label={style.id === "pillars" ? "Bar width" : style.id === "scanlines" ? "Line spacing" : "Cell size"}
                hint="Size of the pattern in pixels."
                value={style.grid}
                min={AURORA_STYLE_LIMITS.grid.min}
                max={AURORA_STYLE_LIMITS.grid.max}
                step={AURORA_STYLE_LIMITS.grid.step}
                format={(v) => `${v}px`}
                onChange={(v) => setStyle({ grid: v })}
              />
            </div>
          )}
        </div>
      </div>

      {/* Motion & Shape */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
            Motion &amp; Shape
          </span>
          {knobsCustomized && (
            <Button variant="outline" size="sm" className="cursor-pointer rounded-xl h-7" onClick={resetKnobs}>
              <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset
            </Button>
          )}
        </div>
        <div className="p-5 grid gap-5 sm:grid-cols-2">
          <RangeControl
            label="Intensity"
            hint="How tall and energetic the glow is."
            value={motion.intensity}
            min={AURORA_MOTION_LIMITS.intensity.min}
            max={AURORA_MOTION_LIMITS.intensity.max}
            step={AURORA_MOTION_LIMITS.intensity.step}
            format={(v) => `${v.toFixed(2)}×`}
            onChange={(v) => setMotion({ intensity: v })}
          />
          <RangeControl
            label="Speed"
            hint="How fast the ribbons drift."
            value={motion.speed}
            min={AURORA_MOTION_LIMITS.speed.min}
            max={AURORA_MOTION_LIMITS.speed.max}
            step={AURORA_MOTION_LIMITS.speed.step}
            format={(v) => `${v.toFixed(2)}×`}
            onChange={(v) => setMotion({ speed: v })}
          />
          <RangeControl
            label="Response"
            hint="How quickly it reacts to new readings."
            value={motion.response}
            min={AURORA_MOTION_LIMITS.response.min}
            max={AURORA_MOTION_LIMITS.response.max}
            step={AURORA_MOTION_LIMITS.response.step}
            format={(v) => v.toFixed(2)}
            onChange={(v) => setMotion({ response: v })}
          />
          <RangeControl
            label="Height"
            hint="Vertical space the glow occupies at the top."
            value={shape.height}
            min={AURORA_SHAPE_LIMITS.height.min}
            max={AURORA_SHAPE_LIMITS.height.max}
            step={AURORA_SHAPE_LIMITS.height.step}
            format={(v) => `${v}px`}
            onChange={(v) => setShape({ height: v })}
          />
          <RangeControl
            label="Softness"
            hint="Wider, hazier ribbons versus a tighter core."
            value={shape.softness}
            min={AURORA_SHAPE_LIMITS.softness.min}
            max={AURORA_SHAPE_LIMITS.softness.max}
            step={AURORA_SHAPE_LIMITS.softness.step}
            format={(v) => `${v.toFixed(2)}×`}
            onChange={(v) => setShape({ softness: v })}
          />
          <RangeControl
            label="Detail"
            hint="Number of ribbons across the width."
            value={shape.noiseScale}
            min={AURORA_SHAPE_LIMITS.noiseScale.min}
            max={AURORA_SHAPE_LIMITS.noiseScale.max}
            step={AURORA_SHAPE_LIMITS.noiseScale.step}
            format={(v) => v.toFixed(1)}
            onChange={(v) => setShape({ noiseScale: v })}
          />
        </div>
      </div>

      {/* Per-state editors */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Custom Colors</span>
        </div>
        <div className="divide-y divide-border/10">
          {STATE_ORDER.map((state) => {
            const Icon = STATE_ICON[state];
            return (
              <div key={state} className="px-5 py-4">
                <div className="flex items-center gap-2 mb-3">
                  <Icon size={14} className={STATE_ACCENT[state]} />
                  <Label className="text-xs font-semibold text-foreground">
                    {STATE_LABELS[state]}
                  </Label>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <ColorField
                    label="Center"
                    hint="Bright glow color"
                    value={palette[state].core}
                    onChange={(hex) => setColor(state, "core", hex)}
                  />
                  <ColorField
                    label="Edge"
                    hint="Deep falloff at the ends"
                    value={palette[state].edge}
                    onChange={(hex) => setColor(state, "edge", hex)}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground px-5 py-3.5 border-t border-border/10 flex items-center gap-1.5">
          <Sparkles size={11} className="text-primary" /> Colors apply instantly and are saved on this device.
        </p>
      </div>
    </div>
  );
}
