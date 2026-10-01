"use client";

// ── Settings › General › Background ─────────────────────────────────────────
// The one place to choose the app's backdrop: None / Pattern / Image. Image
// mode offers the five shipped Eclipse wallpapers plus the user's own picture
// (uploaded from their computer — downscaled client-side, stored in IndexedDB).
// Prefs apply immediately through the background store; this panel is purely
// presentational. The old pattern control (Customization › Glass & Surfaces)
// lives here now so there is a single background surface.

import { useEffect, useRef, useState } from "react";
import { Image as ImageIcon, RotateCcw, Trash2, Upload, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  BACKGROUND_FIT_OPTIONS,
  BACKGROUND_MODE_OPTIONS,
  BACKGROUND_PATTERN_OPTIONS,
  BACKGROUND_WORDMARK_ALIGN_OPTIONS,
  CUSTOM_BACKGROUND_ID,
  DEFAULT_BACKGROUND_ID,
  MAX_UPLOAD_BYTES,
  SHIPPED_BACKGROUNDS,
  WORDMARK_FONT_OPTIONS,
  useBackgroundStore,
  type BackgroundFit,
  type BackgroundMode,
  type BackgroundPattern,
  type WordmarkAlign,
} from "@/lib/backgrounds";

function Panel({ className, children, ...rest }: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)} {...rest}>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>}
    </div>
  );
}

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
  const textFont = useBackgroundStore((s) => s.prefs.textFont);
  const textScale = useBackgroundStore((s) => s.prefs.textScale);
  const textOpacity = useBackgroundStore((s) => s.prefs.textOpacity);
  const textPositionY = useBackgroundStore((s) => s.prefs.textPositionY);
  const textAlign = useBackgroundStore((s) => s.prefs.textAlign);

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

  return (
    <div className="animate-fade-in-up space-y-4">
      <Panel className="p-5 md:p-6 space-y-5">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
          <ImageIcon className="w-4 h-4 text-primary shrink-0" />
          <span>Background</span>
        </div>

        <Field label="Type" hint="Patterns tint the whole app; wallpapers paint the ChatBot page only.">
          <OptionGrid
            options={BACKGROUND_MODE_OPTIONS}
            value={prefs.mode}
            onSelect={(mode: BackgroundMode) => setPrefs({ mode })}
          />
        </Field>

        {prefs.mode === "pattern" && (
          <Field label="Pattern">
            <OptionGrid
              options={BACKGROUND_PATTERN_OPTIONS}
              value={prefs.pattern}
              onSelect={(pattern: BackgroundPattern) => setPrefs({ pattern })}
            />
          </Field>
        )}

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

        {prefs.mode !== "none" && (
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
              {prefs.mode === "image" ? "ChatBot page" : "Whole app"}
            </span>
          </div>
        )}

        {prefs.mode !== "none" && (
          <div className="space-y-4 border-t border-white/10 dark:border-white/5 pt-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
              <Type className="w-4 h-4 text-primary shrink-0" />
              <span>Landing text</span>
            </div>

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

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Font">
                <Select
                  value={textFont}
                  onValueChange={(v) => v && setPrefs({ textFont: v })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WORDMARK_FONT_OPTIONS.map((f) => (
                      <SelectItem key={f.label} value={f.value}>
                        <span style={{ fontFamily: f.value }}>{f.label}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
            </div>

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
          </div>
        )}

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
