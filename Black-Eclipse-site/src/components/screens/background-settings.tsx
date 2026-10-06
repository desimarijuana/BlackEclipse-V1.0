"use client";

// ── Settings › General › Background ─────────────────────────────────────────
// The one place to choose the app's backdrop: None / Pattern / Image. Image
// mode offers the five shipped Eclipse wallpapers plus the user's own picture
// (uploaded from their computer — downscaled client-side, stored in IndexedDB).
// Prefs apply immediately through the background store; this panel is purely
// presentational. The old pattern control (Customization › Glass & Surfaces)
// lives here now so there is a single background surface.

import { useEffect, useRef, useState } from "react";
import { Check, Image as ImageIcon, RotateCcw, Trash2, Upload, Type } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  BACKGROUND_FIT_OPTIONS,
  BACKGROUND_MODE_OPTIONS,
  BACKGROUND_WORDMARK_ALIGN_OPTIONS,
  CUSTOM_BACKGROUND_ID,
  DEFAULT_BACKGROUND_ID,
  GRADIENT_TYPE_OPTIONS,
  MAX_UPLOAD_BYTES,
  SHIPPED_BACKGROUNDS,
  SOLID_FILL_OPTIONS,
  SOLID_PATTERN_OPTIONS,
  WORDMARK_FONT_OPTIONS,
  useBackgroundStore,
  type BackgroundFit,
  type BackgroundMode,
  type WordmarkAlign,
} from "@/lib/backgrounds";
import { Field, Panel, Toggle } from "./settings-ui";

function OptionGrid<T extends string>({
  options,
  value,
  onSelect,
  cols = 3,
}: {
  options: { id: T; label: string; hint: string }[];
  value: T;
  onSelect: (id: T) => void;
  cols?: 2 | 3 | 4;
}) {
  return (
    <div className={cn("grid gap-2", cols === 2 ? "grid-cols-2" : cols === 4 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-3")}>
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onSelect(opt.id)}
          title={opt.hint}
          className={cn(
            "flex flex-col items-start gap-0.5 px-3 py-2.5 text-xs font-medium rounded-xl border transition-all cursor-pointer text-left",
            value === opt.id
              ? "bg-primary/10 text-primary border-primary/40 shadow-sm shadow-primary/10"
              : "bg-transparent text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
          )}
        >
          <span>{opt.label}</span>
          <span className="text-[10px] font-normal opacity-70">{opt.hint}</span>
        </button>
      ))}
    </div>
  );
}

function Range({
  label, value, min, max, step, format, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number;
  format: (v: number) => string; onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
        <span className="text-[11px] font-mono text-muted-foreground/80">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-primary"
      />
    </div>
  );
}

export function BackgroundSettingsPanel() {
  const prefs = useBackgroundStore((s) => s.prefs);
  const customUrl = useBackgroundStore((s) => s.customUrl);
  const saving = useBackgroundStore((s) => s.saving);
  const hydrated = useBackgroundStore((s) => s.hydrated);
  const setPrefs = useBackgroundStore((s) => s.setPrefs);
  const setCustomImage = useBackgroundStore((s) => s.setCustomImage);
  const clearCustomImage = useBackgroundStore((s) => s.clearCustomImage);
  const reset = useBackgroundStore((s) => s.reset);
  const text = useBackgroundStore((s) => s.prefs.text);
  const textEnabled = useBackgroundStore((s) => s.prefs.textEnabled);
  const textFont = useBackgroundStore((s) => s.prefs.textFont);
  const textColor = useBackgroundStore((s) => s.prefs.textColor);
  const textScale = useBackgroundStore((s) => s.prefs.textScale);
  const textOpacity = useBackgroundStore((s) => s.prefs.textOpacity);
  const textPositionY = useBackgroundStore((s) => s.prefs.textPositionY);
  const textAlign = useBackgroundStore((s) => s.prefs.textAlign);
  const solidColor = useBackgroundStore((s) => s.prefs.solidColor);
  const solidColor2 = useBackgroundStore((s) => s.prefs.solidColor2);
  const solidFill = useBackgroundStore((s) => s.prefs.solidFill);
  const solidGradientType = useBackgroundStore((s) => s.prefs.solidGradientType);
  const solidGradientAngle = useBackgroundStore((s) => s.prefs.solidGradientAngle);
  const solidPattern = useBackgroundStore((s) => s.prefs.solidPattern);
  const solidPatternOpacity = useBackgroundStore((s) => s.prefs.solidPatternOpacity);
  const solidPatternScale = useBackgroundStore((s) => s.prefs.solidPatternScale);
  const textWeight = useBackgroundStore((s) => s.prefs.textWeight);
  const textLetterSpacing = useBackgroundStore((s) => s.prefs.textLetterSpacing);
  const textLineHeight = useBackgroundStore((s) => s.prefs.textLineHeight);
  const textWidth = useBackgroundStore((s) => s.prefs.textWidth);
  const textItalic = useBackgroundStore((s) => s.prefs.textItalic);
  const textUppercase = useBackgroundStore((s) => s.prefs.textUppercase);

  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  // Clear a stale error when the user leaves the upload flow.
  useEffect(() => { if (!error) return; const id = setTimeout(() => setError(null), 6000); return () => clearTimeout(id); }, [error]);

  const onPick = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    const err = await setCustomImage(file);
    if (err) setError(err);
  };

  const isCustom = prefs.preset === CUSTOM_BACKGROUND_ID;
  const activeThumb = prefs.mode === "image"
    ? (isCustom ? customUrl : SHIPPED_BACKGROUNDS.find((b) => b.id === prefs.preset)?.url ?? null)
    : null;
  // Solid mode forces the wordmark on (it IS the backdrop), so its controls are
  // always open there; image mode reveals them behind the opt-in toggle.
  const wordmarkOpen = prefs.mode === "solid" || textEnabled;

  return (
    <div className="animate-fade-in-up space-y-4">
      <Panel className="p-5 md:p-6 space-y-5">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
          <ImageIcon className="w-4 h-4 text-primary shrink-0" />
          <span>Background</span>
        </div>

        <Field label="Type" hint="Wallpapers paint the ChatBot page only; Solid fills it with a color and your wordmark.">
          <OptionGrid
            options={BACKGROUND_MODE_OPTIONS}
            value={prefs.mode}
            onSelect={(mode: BackgroundMode) => setPrefs({ mode })}
          />
        </Field>

        {prefs.mode === "image" && (
          <>
            <Field
              label="Wallpaper"
              hint={customUrl
                ? "Pick a shipped wallpaper, or keep your uploaded image selected."
                : "Choose a shipped wallpaper or upload your own from your computer."}
            >
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {SHIPPED_BACKGROUNDS.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => setPrefs({ preset: b.id })}
                    title={`${b.label} (${b.weight})${b.id === DEFAULT_BACKGROUND_ID ? ' — the official default' : ''}`}
                    className={cn(
                      "group relative aspect-video overflow-hidden rounded-xl border transition-all cursor-pointer",
                      !isCustom && prefs.preset === b.id
                        ? "border-primary/60 ring-1 ring-primary/40"
                        : "border-border/30 hover:border-border/60",
                    )}
                  >
                    <span
                      className="absolute inset-0 bg-cover bg-center"
                      style={{ backgroundImage: `url("${b.url}")` }}
                      aria-hidden
                    />
                    {b.id === DEFAULT_BACKGROUND_ID && (
                      <span className="absolute right-1 top-1 rounded-full bg-primary/85 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-primary-foreground">
                        Default
                      </span>
                    )}
                    <span className="absolute inset-x-0 bottom-0 bg-black/55 px-1.5 py-0.5 text-[9px] font-medium text-white/90 truncate">
                      {b.label}
                    </span>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => (customUrl ? setPrefs({ preset: CUSTOM_BACKGROUND_ID }) : fileRef.current?.click())}
                  title={customUrl ? "Use your uploaded image" : "Upload an image from your computer"}
                  className={cn(
                    "group relative aspect-video overflow-hidden rounded-xl border transition-all cursor-pointer flex flex-col items-center justify-center gap-1",
                    isCustom
                      ? "border-primary/60 ring-1 ring-primary/40"
                      : "border-dashed border-border/40 hover:border-border/70",
                  )}
                >
                  {customUrl ? (
                    <>
                      <span className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url("${customUrl}")` }} aria-hidden />
                      <span className="absolute inset-x-0 bottom-0 bg-black/55 px-1.5 py-0.5 text-[9px] font-medium text-white/90">Custom</span>
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
                      <span className="text-[9px] text-muted-foreground">Custom</span>
                    </>
                  )}
                </button>
              </div>
            </Field>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="rounded-xl cursor-pointer"
                disabled={saving}
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="w-3.5 h-3.5 mr-1" /> {saving ? "Optimising…" : customUrl ? "Replace image" : "Upload image"}
              </Button>
              {customUrl && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="rounded-xl cursor-pointer text-muted-foreground hover:text-rose-300"
                  onClick={() => void clearCustomImage()}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" /> Remove custom
                </Button>
              )}
              <span className="text-[10px] text-muted-foreground/60">
                Up to {Math.round(MAX_UPLOAD_BYTES / 1_000_000)} MB. Large images are downscaled automatically.
              </span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Fit">
                <OptionGrid
                  options={BACKGROUND_FIT_OPTIONS}
                  value={prefs.fit}
                  onSelect={(fit: BackgroundFit) => setPrefs({ fit })}
                  cols={3}
                />
              </Field>
              <Field label="Applies to">
                <p className="text-[11px] text-muted-foreground leading-relaxed pt-1.5">
                  The ChatBot page only — it stays continuous behind the sidebar.
                </p>
              </Field>
            </div>

            <Range
              label="Darkening"
              value={prefs.dim}
              min={0}
              max={100}
              step={1}
              format={(v) => `${v}%`}
              onChange={(dim) => setPrefs({ dim })}
            />

            <div className="grid gap-4 sm:grid-cols-3">
              <Range
                label="Zoom"
                value={prefs.scale}
                min={50}
                max={300}
                step={5}
                format={(v) => `${v}%`}
                onChange={(scale) => setPrefs({ scale })}
              />
              <Range
                label="Horizontal"
                value={prefs.positionX}
                min={0}
                max={100}
                step={1}
                format={(v) => `${v}%`}
                onChange={(positionX) => setPrefs({ positionX })}
              />
              <Range
                label="Vertical"
                value={prefs.positionY}
                min={0}
                max={100}
                step={1}
                format={(v) => `${v}%`}
                onChange={(positionY) => setPrefs({ positionY })}
              />
            </div>
          </>
        )}

        {prefs.mode === "solid" && (
          <>
            <Field label="Style" hint="Flat color, a two-color gradient, or a textured pattern.">
              <OptionGrid options={SOLID_FILL_OPTIONS} value={solidFill} onSelect={(v) => setPrefs({ solidFill: v })} />
            </Field>

            <Field
              label={solidFill === "gradient" ? "Color (start)" : "Color"}
              hint="Leave on Theme to follow the active theme, or pick your own."
            >
              <div className="flex flex-wrap items-center gap-2">
                <label
                  className="relative h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-border/40"
                  style={{ backgroundColor: solidColor || "var(--background)" }}
                  title="Pick the base color"
                >
                  <input
                    type="color"
                    value={solidColor || "#000000"}
                    onChange={(e) => setPrefs({ solidColor: e.target.value })}
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                    aria-label="Solid background color"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setPrefs({ solidColor: "" })}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-xs font-medium transition-all cursor-pointer",
                    !solidColor
                      ? "bg-primary/10 text-primary border-primary/40"
                      : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                  )}
                >
                  Theme
                </button>
                {solidColor && (
                  <span className="font-mono text-[11px] text-muted-foreground/80">{solidColor}</span>
                )}
              </div>
            </Field>

            {solidFill === "gradient" && (
              <Field label="Color (end)" hint="Leave on Brand for a tint derived from your theme's brand color.">
                <div className="flex flex-wrap items-center gap-2">
                  <label
                    className="relative h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-border/40"
                    style={{ backgroundColor: solidColor2 || "rgb(var(--brand-rgb) / 0.55)" }}
                    title="Pick the end color"
                  >
                    <input
                      type="color"
                      value={solidColor2 || "#00ff41"}
                      onChange={(e) => setPrefs({ solidColor2: e.target.value })}
                      className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                      aria-label="Gradient end color"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => setPrefs({ solidColor2: "" })}
                    className={cn(
                      "rounded-xl border px-3 py-2 text-xs font-medium transition-all cursor-pointer",
                      !solidColor2
                        ? "bg-primary/10 text-primary border-primary/40"
                        : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                    )}
                  >
                    Brand
                  </button>
                  {solidColor2 && (
                    <span className="font-mono text-[11px] text-muted-foreground/80">{solidColor2}</span>
                  )}
                </div>
              </Field>
            )}

            {solidFill === "gradient" && (
              <>
                <Field label="Gradient">
                  <OptionGrid options={GRADIENT_TYPE_OPTIONS} value={solidGradientType} onSelect={(v) => setPrefs({ solidGradientType: v })} />
                </Field>
                {solidGradientType === "linear" && (
                  <Range
                    label="Angle"
                    value={solidGradientAngle}
                    min={0}
                    max={360}
                    step={5}
                    format={(v) => `${v}°`}
                    onChange={(solidGradientAngle) => setPrefs({ solidGradientAngle })}
                  />
                )}
              </>
            )}

            {solidFill === "pattern" && (
              <>
                <Field label="Pattern">
                  <OptionGrid options={SOLID_PATTERN_OPTIONS} value={solidPattern} onSelect={(v) => setPrefs({ solidPattern: v })} cols={4} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Range
                    label="Pattern strength"
                    value={solidPatternOpacity}
                    min={0}
                    max={100}
                    step={1}
                    format={(v) => `${v}%`}
                    onChange={(solidPatternOpacity) => setPrefs({ solidPatternOpacity })}
                  />
                  <Range
                    label="Pattern size"
                    value={solidPatternScale}
                    min={4}
                    max={80}
                    step={1}
                    format={(v) => `${v}px`}
                    onChange={(solidPatternScale) => setPrefs({ solidPatternScale })}
                  />
                </div>
              </>
            )}
          </>
        )}

        {prefs.mode === "image" && (
          <div
            className="relative h-20 overflow-hidden rounded-xl border border-border/30 bg-background"
            aria-hidden
          >
            {activeThumb ? (
              <>
                <span
                  className="absolute inset-0"
                  style={{
                    backgroundImage: `url("${activeThumb}")`,
                    backgroundSize: prefs.fit === "cover" ? "cover" : prefs.fit === "contain" ? "contain" : "auto",
                    backgroundRepeat: prefs.fit === "tile" ? "repeat" : "no-repeat",
                    backgroundPosition: `${prefs.positionX}% ${prefs.positionY}%`,
                    transform: `scale(${Math.min(3, Math.max(0.5, prefs.scale / 100))})`,
                    transformOrigin: `${prefs.positionX}% ${prefs.positionY}%`,
                  }}
                />
                <span
                  className="absolute inset-0"
                  style={{ backgroundColor: `rgba(0,0,0,${prefs.dim / 100})` }}
                />
              </>
            ) : (
              <span className="absolute inset-0 bg-gradient-to-b from-primary/10 to-transparent" />
            )}
            <span className="absolute bottom-1.5 left-2 text-[10px] text-white/70">
              ChatBot page
            </span>
          </div>
        )}

        <div className="space-y-4 border-t border-white/10 dark:border-white/5 pt-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
                <Type className="w-4 h-4 text-primary shrink-0" />
                <span>Landing text</span>
              </div>
              <Toggle
                checked={wordmarkOpen}
                onChange={(v) => setPrefs({ textEnabled: v })}
                disabled={prefs.mode === "solid"}
              />
            </div>
            <p className="text-[10px] text-muted-foreground/70 -mt-2">
              {prefs.mode === "solid"
                ? "The wordmark is the solid backdrop — customize its text, font, color and size."
                : "Off by default. Turn on to paint the wordmark over your wallpaper — shipped or your own upload."}
            </p>

            {wordmarkOpen && (
              <>
                <Field
                  label="Text"
                  hint="A giant wordmark painted behind the ChatBot landing. Leave empty to hide it."
                >
                  <Input
                    value={text}
                    maxLength={64}
                    placeholder="ECLIPSE AGENT"
                    onChange={(e) => setPrefs({ text: e.target.value })}
                  />
                </Field>

                <Field label="Font" hint="Tap a face to preview and apply it. Each shows its own name in that typeface.">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {WORDMARK_FONT_OPTIONS.map((f) => (
                      <button
                        key={f.label}
                        type="button"
                        onClick={() => setPrefs({ textFont: f.value })}
                        title={f.label}
                        aria-pressed={textFont === f.value}
                        className={cn(
                          "flex items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-all cursor-pointer",
                          textFont === f.value
                            ? "bg-primary/10 text-primary border-primary/40"
                            : "bg-transparent text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                        )}
                      >
                        <span className="truncate text-sm leading-tight" style={{ fontFamily: f.value }}>{f.label}</span>
                        {textFont === f.value && <Check className="w-3.5 h-3.5 shrink-0 text-primary" />}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field label="Align">
                  <div className="grid grid-cols-3 gap-2">
                    {BACKGROUND_WORDMARK_ALIGN_OPTIONS.map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setPrefs({ textAlign: opt.id as WordmarkAlign })}
                        className={cn(
                          "px-3 py-2 text-xs font-medium rounded-xl border transition-all cursor-pointer",
                          textAlign === opt.id
                            ? "bg-primary/10 text-primary border-primary/40"
                            : "bg-transparent text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field
                  label="Text color"
                  hint="Leave on Theme to follow the app's text color, or pick your own."
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <label
                      className="relative h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-border/40"
                      style={{ backgroundColor: textColor || "var(--foreground)" }}
                      title="Pick the wordmark color"
                    >
                      <input
                        type="color"
                        value={textColor || "#ffffff"}
                        onChange={(e) => setPrefs({ textColor: e.target.value })}
                        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                        aria-label="Wordmark color"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => setPrefs({ textColor: "" })}
                      className={cn(
                        "rounded-xl border px-3 py-2 text-xs font-medium transition-all cursor-pointer",
                        !textColor
                          ? "bg-primary/10 text-primary border-primary/40"
                          : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                      )}
                    >
                      Theme
                    </button>
                    {textColor && (
                      <span className="font-mono text-[11px] text-muted-foreground/80">{textColor}</span>
                    )}
                  </div>
                </Field>

                <div className="grid gap-4 sm:grid-cols-3">
                  <Range
                    label="Size"
                    value={textScale}
                    min={4}
                    max={40}
                    step={1}
                    format={(v) => `${v}vw`}
                    onChange={(textScale) => setPrefs({ textScale })}
                  />
                  <Range
                    label="Strength"
                    value={textOpacity}
                    min={0}
                    max={100}
                    step={1}
                    format={(v) => `${v}%`}
                    onChange={(textOpacity) => setPrefs({ textOpacity })}
                  />
                  <Range
                    label="Vertical"
                    value={textPositionY}
                    min={0}
                    max={100}
                    step={1}
                    format={(v) => `${v}%`}
                    onChange={(textPositionY) => setPrefs({ textPositionY })}
                  />
                </div>

                {/* Typography playground — weight, width, tracking, leading, slant. */}
                <div className="grid gap-4 sm:grid-cols-3">
                  <Range
                    label="Weight"
                    value={textWeight}
                    min={100}
                    max={900}
                    step={100}
                    format={(v) => `${v}`}
                    onChange={(textWeight) => setPrefs({ textWeight })}
                  />
                  <Range
                    label="Width"
                    value={textWidth}
                    min={50}
                    max={200}
                    step={5}
                    format={(v) => `${v}%`}
                    onChange={(textWidth) => setPrefs({ textWidth })}
                  />
                  <Range
                    label="Tracking"
                    value={textLetterSpacing}
                    min={-0.1}
                    max={0.5}
                    step={0.01}
                    format={(v) => `${v.toFixed(2)}em`}
                    onChange={(textLetterSpacing) => setPrefs({ textLetterSpacing })}
                  />
                  <Range
                    label="Leading"
                    value={textLineHeight}
                    min={0.7}
                    max={2}
                    step={0.05}
                    format={(v) => `${v.toFixed(2)}`}
                    onChange={(textLineHeight) => setPrefs({ textLineHeight })}
                  />
                  <div className="flex items-end gap-3">
                    <button
                      type="button"
                      onClick={() => setPrefs({ textItalic: !textItalic })}
                      aria-pressed={textItalic}
                      className={cn(
                        "rounded-xl border px-3 py-2 text-xs font-medium italic transition-all cursor-pointer",
                        textItalic
                          ? "bg-primary/10 text-primary border-primary/40"
                          : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                      )}
                    >
                      Italic
                    </button>
                    <button
                      type="button"
                      onClick={() => setPrefs({ textUppercase: !textUppercase })}
                      aria-pressed={textUppercase}
                      className={cn(
                        "rounded-xl border px-3 py-2 text-xs font-medium uppercase tracking-wide transition-all cursor-pointer",
                        textUppercase
                          ? "bg-primary/10 text-primary border-primary/40"
                          : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                      )}
                    >
                      Uppercase
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

        {error && <p className="text-[10px] text-rose-400">{error}</p>}
      </Panel>

      <div className="flex items-center justify-between">
        <p className="text-[10px] text-muted-foreground/60">
          {hydrated ? "Changes apply instantly." : "Loading…"}
        </p>
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={reset}>
          <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset background
        </Button>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          void onPick(file);
        }}
      />
    </div>
  );
}
