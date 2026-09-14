"use client";

// ── Settings › Aurora ─────────────────────────────────────────────────────
// Lets the user recolor the Aurora glow. Each sentiment state (bearish /
// neutral / bullish) has a bright CORE color (the glow's center) and an EDGE
// color (the deep falloff at both ends of the ribbon). Changes apply live to
// the Aurora rendered behind the whole app and persist in localStorage.
//
// The sentiment model itself is untouched — this only swaps the palette that
// `resolveAuroraVisuals(score, palette)` interpolates between.

import { useEffect, useMemo, useState } from "react";
import {
  Palette, Sparkles, RotateCcw, Check, TrendingUp, TrendingDown, Minus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { resolveAuroraVisuals } from "@/lib/aurora-sentiment";
import {
  AURORA_PRESETS, STATE_LABELS, STATE_ORDER,
  isValidHex, paletteMatchesPreset,
  type AuroraColorPair, type AuroraMarketState,
} from "@/lib/aurora/theme";
import { useAuroraPaletteStore } from "@/lib/aurora/store";

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

  const handleText = (next: string) => {
    setText(next);
    if (isValidHex(next)) onChange(next.trim().toLowerCase());
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
          onChange={(e) => { setText(e.target.value); onChange(e.target.value); }}
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

export function AuroraSettingsPanel() {
  const palette = useAuroraPaletteStore((s) => s.palette);
  const setColor = useAuroraPaletteStore((s) => s.setColor);
  const setPalette = useAuroraPaletteStore((s) => s.setPalette);
  const reset = useAuroraPaletteStore((s) => s.reset);

  const previewScores = useMemo(() => [-1, -0.5, 0, 0.5, 1], []);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-6">
        <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2 flex items-center gap-1.5">
          <Sparkles size={11} /> Personalize
        </p>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 shadow-sm shadow-primary/10">
            <Palette className="text-primary w-[18px] h-[18px]" />
          </div>
          <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Aurora Colors</h2>
        </div>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
          Recolor the ambient glow at the top of the terminal. Each market state has a bright
          <span className="text-foreground"> center </span> and a deep
          <span className="text-foreground"> edge</span> color; Aurora blends between them as sentiment moves.
        </p>
      </div>

      {/* Live preview */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Preview</span>
          <span className="text-[10px] text-muted-foreground font-mono">bearish → bullish</span>
        </div>
        <div className="p-4">
          <AuroraPreview palette={palette} scores={previewScores} />
        </div>
      </div>

      {/* Presets */}
      <div className="rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden mb-4">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/10">
          <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Presets</span>
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
                onClick={() => setPalette(preset.palette)}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer",
                  active
                    ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                    : "border-border/20 glass-card-subtle hover:border-border/40"
                )}
              >
                <span className="flex -space-x-1.5 shrink-0">
                  {[preset.palette.bearish, preset.palette.neutral, preset.palette.bullish].map((p, i) => (
                    <span
                      key={i}
                      className="w-5 h-5 rounded-full border border-white/20"
                      style={{ backgroundColor: p.core }}
                    />
                  ))}
                </span>
                <span className="flex flex-col min-w-0">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    {preset.label}
                    {active && <Check className="w-3 h-3 text-primary" />}
                  </span>
                  <span className="text-[10px] text-muted-foreground truncate">{preset.description}</span>
                </span>
              </button>
            );
          })}
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
