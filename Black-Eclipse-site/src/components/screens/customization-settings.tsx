"use client";

// ── Settings › Customization ──────────────────────────────────────────────
// The centralized theme/customization surface. Everything here flows through
// the Eclipse theme store (`@/lib/theme`), which flattens the theme to CSS
// design tokens on <html> — so changes recolor the entire app (chrome, cards,
// charts, widgets) with no component-specific hacks.
//
// Three groups:
//   1. Branding      — app name, logo, favicon
//   2. Typography & shape — UI/heading/mono fonts, radius, density
//   3. Colors        — presets + custom primary/accent/surface/text/market
//   4. Motion        — glow + animation preferences
//
// Language + accessibility live here too (presentation-layer, localStorage).
// Every preference applies instantly and persists locally.

import { useEffect, useRef, useState } from "react";
import {
  Accessibility, Languages, RotateCcw, Palette, Image as ImageIcon,
  Type, SlidersHorizontal, Sparkles, Check, Sun, AlertTriangle,
  Wand2, Activity, Layers, Square,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DEFAULT_A11Y, LOCALES, useLocaleStore, useT, type LocaleCode } from "@/lib/i18n";
import {
  BACKGROUND_OPTIONS, DENSITY_OPTIONS, GLASS_PRESETS, HEADING_FONT_OPTIONS, MONO_FONT_OPTIONS,
  SHADOW_OPTIONS, THEME_PRESETS, UI_FONT_OPTIONS,
  isValidHex, normalizeHex, syncChartPaletteFromTheme, themeFromBrandColor, useThemeStore,
  type ThemeColors, type ThemeGlass,
} from "@/lib/theme";
import { AuroraSettingsPanel } from "./aurora-settings";
import { ChartSettingsPanel } from "./chart-settings";

type CustomTab = "theme" | "glass" | "aurora" | "charts" | "access";

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70",
        )}
      />
    </button>
  );
}

function Row({
  label, hint, checked, onChange,
}: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
        <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

function Card({
  icon: Icon, title, children,
}: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-5 rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6">
      <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
        <Icon className="w-4 h-4 text-primary shrink-0" />
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

/** Native color swatch + hex input pair, committed live through the store. */
function ColorField({
  label, hint, value, onChange,
}: { label: string; hint?: string; value: string; onChange: (hex: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const valid = isValidHex(text);
  const handleText = (next: string) => {
    setText(next);
    const n = normalizeHex(next);
    if (n) onChange(n);
  };
  return (
    <div className="flex items-center gap-3 min-w-0">
      <label
        className="relative w-9 h-9 shrink-0 rounded-xl border border-white/15 cursor-pointer overflow-hidden shadow-sm"
        style={{ backgroundColor: valid ? text : value }}
      >
        <input
          type="color"
          value={normalizeHex(text) ?? value}
          onChange={(e) => { setText(e.target.value); onChange(e.target.value); }}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          aria-label={`${label} color picker`}
        />
      </label>
      <div className="flex flex-col min-w-0">
        <span className="text-xs font-medium text-foreground">{label}</span>
        {hint && <span className="text-[10px] text-muted-foreground truncate">{hint}</span>}
      </div>
      <input
        value={text}
        onChange={(e) => handleText(e.target.value)}
        spellCheck={false}
        className={cn(
          "ml-auto w-[92px] shrink-0 rounded-lg border bg-transparent px-2 py-1 font-mono text-[11px] uppercase outline-none transition-colors",
          valid ? "border-border/40 focus-visible:border-primary/50" : "border-rose-500/50 text-rose-400",
        )}
        aria-label={`${label} hex value`}
      />
    </div>
  );
}

/** Reads an image file into a data URL, capped to keep localStorage healthy. */
function useImagePicker(onPick: (dataUrl: string) => void) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = () => inputRef.current?.click();
  const node = (
    <input
      ref={inputRef}
      type="file"
      accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon"
      className="hidden"
      onChange={(e) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file) return;
        if (file.size > 300_000) {
          setError("Image is too large (max 300 KB). Use a smaller file or a URL.");
          return;
        }
        const reader = new FileReader();
        reader.onload = () => {
          if (typeof reader.result === "string") { setError(null); onPick(reader.result); }
        };
        reader.readAsDataURL(file);
      }}
    />
  );
  return { open, node, error };
}

function ImageField({
  label, hint, value, onChange,
}: { label: string; hint: string; value: string; onChange: (v: string) => void }) {
  const { open, node, error } = useImagePicker(onChange);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-border/40 bg-muted/20 overflow-hidden">
            {value
              ? <img src={value} alt="" className="h-full w-full object-contain" />
              : <ImageIcon className="w-4 h-4 text-muted-foreground" />}
          </span>
          <Button variant="outline" size="sm" className="rounded-xl cursor-pointer" onClick={open}>Upload</Button>
          {value && (
            <Button variant="ghost" size="sm" className="rounded-xl cursor-pointer" onClick={() => onChange("")}>Clear</Button>
          )}
        </div>
      </div>
      <Input
        value={value.startsWith("data:") ? "" : value}
        placeholder={value.startsWith("data:") ? "Uploaded image" : "…or paste an image URL"}
        onChange={(e) => onChange(e.target.value)}
        className="font-mono text-[11px]"
      />
      {error && (
        <p className="text-[10px] text-rose-400 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {error}
        </p>
      )}
      {node}
    </div>
  );
}

export function CustomizationSettingsPanel() {
  const t = useT();
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);
  const a11y = useLocaleStore((s) => s.a11y);
  const setA11y = useLocaleStore((s) => s.setA11y);

  const theme = useThemeStore((s) => s.theme);
  const customized = useThemeStore((s) => s.customized);
  const setTheme = useThemeStore((s) => s.setTheme);
  const setColor = useThemeStore((s) => s.setColor);
  const setGlass = useThemeStore((s) => s.setGlass);
  const applyPreset = useThemeStore((s) => s.applyPreset);
  const resetTheme = useThemeStore((s) => s.reset);

  const [tab, setTab] = useState<CustomTab>("theme");
  const [brandColor, setBrandColor] = useState(theme.colors.primary);

  // Keep native charts in step with the theme's market colors when the user
  // explicitly recolors (presets, color edits, reset) — never on hydration.
  const changePreset = (next: typeof theme) => {
    applyPreset(next);
    syncChartPaletteFromTheme(next);
  };
  const changeColor = (key: keyof ThemeColors, hex: string) => {
    setColor(key, hex);
    syncChartPaletteFromTheme(useThemeStore.getState().theme);
  };
  const resetAll = () => {
    resetTheme();
    syncChartPaletteFromTheme(useThemeStore.getState().theme);
  };
  // ServiceNow-style "build a theme from your brand color": derive primary,
  // accent and market colors, then sync charts.
  const generateFromBrand = (hex: string) => {
    const next = themeFromBrandColor(hex, theme);
    applyPreset(next);
    syncChartPaletteFromTheme(next);
  };

  const activePreset = THEME_PRESETS.find(
    (p) => JSON.stringify(theme) === JSON.stringify(p.theme),
  )?.id ?? null;

  const COLORS: { key: keyof ThemeColors; label: string; hint: string }[] = [
    { key: "primary", label: "Primary", hint: "Brand / interactive" },
    { key: "accent", label: "Accent", hint: "Secondary brand tint" },
    { key: "background", label: "Background", hint: "Page backdrop" },
    { key: "surface", label: "Surface", hint: "Cards & panels" },
    { key: "border", label: "Border", hint: "Hairlines & inputs" },
    { key: "text", label: "Text", hint: "Primary text" },
    { key: "bullish", label: "Bullish", hint: "Gains & up candles" },
    { key: "bearish", label: "Bearish", hint: "Losses & down candles" },
  ];

  // Glass preset is "active" when every field matches (so the chip highlights).
  const glassMatches = (g: ThemeGlass) =>
    theme.glass.enabled === g.enabled &&
    theme.glass.blur === g.blur &&
    theme.glass.opacity === g.opacity &&
    theme.glass.tint === g.tint;

  const TABS: { id: CustomTab; label: string; icon: React.ElementType }[] = [
    { id: "theme", label: "Theme", icon: Palette },
    { id: "glass", label: "Glass & Surfaces", icon: Layers },
    { id: "aurora", label: "Aurora", icon: Sparkles },
    { id: "charts", label: "Charts", icon: Activity },
    { id: "access", label: "Language & Access", icon: Accessibility },
  ];

  return (
    <div className="space-y-6">
      {/* Sub-navigation: one Customization home for theme, Aurora, charts and
          language/accessibility so everything that shapes the look lives here. */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-medium transition-all cursor-pointer",
                active
                  ? "bg-primary/10 text-foreground border-primary/40 shadow-sm shadow-primary/10"
                  : "text-muted-foreground border-border/30 hover:text-foreground hover:border-border/60",
              )}
            >
              <Icon size={14} className={active ? "text-primary" : "text-muted-foreground"} />
              {item.label}
            </button>
          );
        })}
      </div>

      {tab === "glass" && (
        <div className="animate-fade-in-up space-y-6">
          {/* ── Glass mode ───────────────────────────────────────────── */}
          <Card icon={Layers} title="Glass Mode">
            <Row
              label="Frosted glass surfaces"
              hint="When off, every card, panel and menu becomes solid with no blur."
              checked={theme.glass.enabled}
              onChange={(v) => setGlass({ enabled: v })}
            />
            <div className="grid gap-2 sm:grid-cols-4">
              {GLASS_PRESETS.map((p) => {
                const active = glassMatches(p.glass);
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setGlass(p.glass)}
                    aria-pressed={active}
                    title={p.hint}
                    className={cn(
                      "flex flex-col gap-2 rounded-xl border p-3 text-left transition-all cursor-pointer",
                      active
                        ? "border-primary/40 bg-primary/10"
                        : "border-border/20 glass-card-subtle hover:border-border/40",
                    )}
                  >
                    <span
                      className="h-8 w-full rounded-lg border border-white/10"
                      style={{
                        backgroundColor: p.glass.enabled
                          ? `rgb(${normalizeHex(p.glass.tint)?.slice(1).match(/../g)?.map((h) => parseInt(h, 16)).join(' ') ?? '18 18 20'} / ${p.glass.opacity})`
                          : p.glass.tint,
                        backdropFilter: p.glass.enabled ? `blur(${p.glass.blur}px)` : 'none',
                      }}
                      aria-hidden
                    />
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      {p.label}
                      {active && <Check className="w-3 h-3 text-primary" />}
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>

          {/* ── Fine-tune ────────────────────────────────────────────── */}
          <Card icon={SlidersHorizontal} title="Fine-tune Glass">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground font-medium">Blur radius</Label>
                <span className="text-[10px] font-mono text-muted-foreground">{theme.glass.blur}px</span>
              </div>
              <input
                type="range"
                min={0}
                max={48}
                step={1}
                value={theme.glass.blur}
                disabled={!theme.glass.enabled}
                onChange={(e) => setGlass({ blur: Number(e.target.value) })}
                className="w-full cursor-pointer disabled:opacity-40"
                aria-label="Glass blur radius"
              />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground font-medium">Tint opacity</Label>
                <span className="text-[10px] font-mono text-muted-foreground">{Math.round(theme.glass.opacity * 100)}%</span>
              </div>
              <input
                type="range"
                min={0.05}
                max={1}
                step={0.01}
                value={theme.glass.opacity}
                onChange={(e) => setGlass({ opacity: Number(e.target.value) })}
                className="w-full cursor-pointer"
                aria-label="Glass tint opacity"
              />
            </div>
            <ColorField
              label="Tint color"
              hint="Base color of every glass surface"
              value={theme.glass.tint}
              onChange={(hex) => setGlass({ tint: hex })}
            />
            <div className="flex items-start gap-3 rounded-xl border border-border/20 glass-card-subtle p-3">
              <span
                className="mt-0.5 h-10 w-16 shrink-0 rounded-lg border border-white/10"
                style={{
                  backgroundColor: `rgb(${normalizeHex(theme.glass.tint)?.slice(1).match(/../g)?.map((h) => parseInt(h, 16)).join(' ') ?? '18 18 20'} / ${theme.glass.enabled ? theme.glass.opacity : 0.96})`,
                  backdropFilter: theme.glass.enabled ? `blur(${theme.glass.blur}px)` : 'none',
                }}
                aria-hidden
              />
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Live preview of a themed surface. Frosted glass only reads correctly when the
                tint is translucent — a high opacity hides the blur and looks solid.
              </p>
            </div>
          </Card>

          {/* ── Depth ────────────────────────────────────────────────── */}
          <Card icon={Square} title="Depth & Shadow">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SHADOW_OPTIONS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setTheme({ shadow: s.id })}
                  title={s.hint}
                  className={cn(
                    "px-3 py-2.5 text-xs font-medium rounded-xl border transition-all cursor-pointer",
                    theme.shadow === s.id
                      ? "bg-primary/10 text-primary border-primary/40"
                      : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </Card>

          {/* ── Page background ──────────────────────────────────────── */}
          <Card icon={Palette} title="Page Background">
            <div className="grid grid-cols-3 gap-2">
              {BACKGROUND_OPTIONS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setTheme({ background: b.id })}
                  title={b.hint}
                  className={cn(
                    "px-3 py-2.5 text-xs font-medium rounded-xl border transition-all cursor-pointer",
                    theme.background === b.id
                      ? "bg-primary/10 text-primary border-primary/40"
                      : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                  )}
                >
                  {b.label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground">
              The pattern is tinted with your primary color and sits over the Background
              token, so it always matches the theme.
            </p>
          </Card>
        </div>
      )}

      {tab === "aurora" && (
        <div className="animate-fade-in-up">
          <AuroraSettingsPanel />
        </div>
      )}

      {tab === "charts" && (
        <div className="animate-fade-in-up">
          <ChartSettingsPanel />
        </div>
      )}

      {tab === "access" && (
        <div className="animate-fade-in-up space-y-6">
          {/* ── Language ──────────────────────────────────────────────── */}
          <Card icon={Languages} title={t("settings.customization.language")}>
            <div className="flex flex-col gap-1.5">
              <Select value={locale} onValueChange={(v) => v && setLocale(v as LocaleCode)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LOCALES.map((l) => (
                    <SelectItem key={l.code} value={l.code}>
                      <span className="inline-flex items-center gap-2">
                        {l.nativeName}
                        <span className="text-muted-foreground/60 text-[10px]">{l.name}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                {t("settings.customization.languageHint")}
              </p>
            </div>
          </Card>

          {/* ── Accessibility ─────────────────────────────────────────── */}
          <Card icon={Accessibility} title={t("settings.accessibility.description")}>
            <Row
              label={t("settings.accessibility.reduceMotion")}
              hint={t("settings.accessibility.reduceMotionHint")}
              checked={a11y.reduceMotion}
              onChange={(v) => setA11y({ reduceMotion: v })}
            />
            <Row
              label={t("settings.accessibility.highContrast")}
              hint={t("settings.accessibility.highContrastHint")}
              checked={a11y.highContrast}
              onChange={(v) => setA11y({ highContrast: v })}
            />
            <Row
              label={t("settings.accessibility.largeText")}
              hint={t("settings.accessibility.largeTextHint")}
              checked={a11y.largeText}
              onChange={(v) => setA11y({ largeText: v })}
            />
            <div className="flex justify-end pt-1">
              <Button
                variant="outline"
                size="sm"
                className="cursor-pointer rounded-xl"
                onClick={() => setA11y(DEFAULT_A11Y)}
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1" /> {t("settings.accessibility.reset")}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {tab === "theme" && (
      <div className="animate-fade-in-up space-y-6">
      {/* ── Brand color generator ─────────────────────────────────────── */}
      <Card icon={Wand2} title="Build Theme From Brand Color">
        <p className="text-[10px] text-muted-foreground -mt-2">
          Pick your organisation&apos;s brand color and Eclipse derives a coordinated
          palette — primary, accent and market colors — around it.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label
            className="relative h-9 w-9 shrink-0 rounded-xl border border-white/15 cursor-pointer overflow-hidden shadow-sm"
            style={{ backgroundColor: brandColor }}
          >
            <input
              type="color"
              value={normalizeHex(brandColor) ?? theme.colors.primary}
              onChange={(e) => setBrandColor(e.target.value)}
              className="absolute inset-0 h-full w-full opacity-0 cursor-pointer"
              aria-label="Brand color picker"
            />
          </label>
          <input
            value={brandColor}
            onChange={(e) => {
              setBrandColor(e.target.value);
              const n = normalizeHex(e.target.value);
              if (n) generateFromBrand(n);
            }}
            spellCheck={false}
            className="w-[120px] rounded-lg border border-border/40 bg-transparent px-2 py-1 font-mono text-[11px] uppercase outline-none focus-visible:border-primary/50"
            aria-label="Brand hex value"
          />
          <Button
            variant="outline"
            size="sm"
            className="rounded-xl cursor-pointer"
            onClick={() => generateFromBrand(normalizeHex(brandColor) ?? theme.colors.primary)}
          >
            <Wand2 className="w-3.5 h-3.5 mr-1" /> Generate theme
          </Button>
          <span
            className="h-5 w-32 shrink-0 rounded-md border border-white/15"
            style={{ background: `linear-gradient(90deg, ${theme.colors.bearish} 0%, ${theme.colors.primary} 50%, ${theme.colors.accent} 100%)` }}
            aria-hidden
          />
        </div>
      </Card>

      {/* ── Theme presets + reset ─────────────────────────────────────── */}
      <Card icon={Palette} title="Eclipse Themes">
        <div className="grid gap-2 sm:grid-cols-2">
          {THEME_PRESETS.map((preset) => {
            const active = activePreset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => changePreset(preset.theme)}
                aria-pressed={active}
                title={preset.description}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer",
                  active
                    ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                    : "border-border/20 glass-card-subtle hover:border-border/40",
                )}
              >
                <span
                  className="h-5 w-12 shrink-0 rounded-md border border-white/15"
                  style={{
                    background: `linear-gradient(90deg, ${preset.theme.colors.bullish} 0%, ${preset.theme.colors.primary} 50%, ${preset.theme.colors.bearish} 100%)`,
                  }}
                  aria-hidden
                />
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
          <div
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left",
              customized && activePreset === null
                ? "bg-primary/10 border-primary/40"
                : "border-border/20 glass-card-subtle",
            )}
          >
            <SlidersHorizontal className="w-4 h-4 text-primary shrink-0" />
            <span className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-foreground">Custom Theme</span>
              <span className="text-[10px] text-muted-foreground truncate">
                {customized && activePreset === null ? "Active — edited below" : "Tune any token below"}
              </span>
            </span>
          </div>
        </div>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={resetAll}>
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset to Eclipse Default
          </Button>
        </div>
      </Card>

      {/* ── Branding ──────────────────────────────────────────────────── */}
      <Card icon={Sparkles} title="Branding">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">App / workspace name</Label>
            <Input
              value={theme.appName}
              onChange={(e) => setTheme({ appName: e.target.value })}
              placeholder="BlackEclipse"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Logo mark (text)</Label>
            <Input
              value={theme.logoText}
              maxLength={4}
              onChange={(e) => setTheme({ logoText: e.target.value })}
              placeholder="B"
            />
          </div>
        </div>
        <ImageField
          label="Logo image"
          hint="Replaces the sidebar / header mark. PNG, SVG or WEBP up to 300 KB."
          value={theme.logoUrl}
          onChange={(v) => setTheme({ logoUrl: v })}
        />
        <ImageField
          label="Favicon"
          hint="Browser tab icon. Empty derives one from your logo mark + primary color."
          value={theme.faviconUrl}
          onChange={(v) => setTheme({ faviconUrl: v })}
        />
      </Card>

      {/* ── Typography & shape ────────────────────────────────────────── */}
      <Card icon={Type} title="Typography & Shape">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">UI font</Label>
            <Select value={theme.fontUi} onValueChange={(v) => v && setTheme({ fontUi: v })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {UI_FONT_OPTIONS.map((f) => <SelectItem key={f.label} value={f.value}>{f.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Heading font</Label>
            <Select value={theme.fontHeading} onValueChange={(v) => v && setTheme({ fontHeading: v })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {HEADING_FONT_OPTIONS.map((f) => <SelectItem key={f.label} value={f.value}>{f.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground font-medium">Monospace font</Label>
            <Select value={theme.fontMono} onValueChange={(v) => v && setTheme({ fontMono: v })}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {MONO_FONT_OPTIONS.map((f) => <SelectItem key={f.label} value={f.value}>{f.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground font-medium">Text size</Label>
              <span className="text-[10px] font-mono text-muted-foreground">{Math.round(theme.fontScale * 100)}%</span>
            </div>
            <input
              type="range"
              min={0.8}
              max={1.4}
              step={0.05}
              value={theme.fontScale}
              onChange={(e) => setTheme({ fontScale: Number(e.target.value) })}
              className="w-full cursor-pointer"
              aria-label="Text size"
            />
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground font-medium">Logo size</Label>
              <span className="text-[10px] font-mono text-muted-foreground">{Math.round(theme.logoScale * 100)}%</span>
            </div>
            <input
              type="range"
              min={0.6}
              max={1.8}
              step={0.05}
              value={theme.logoScale}
              onChange={(e) => setTheme({ logoScale: Number(e.target.value) })}
              className="w-full cursor-pointer"
              aria-label="Logo size"
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground font-medium">Border radius</Label>
            <span className="text-[10px] font-mono text-muted-foreground">{theme.radius.toFixed(2)}rem</span>
          </div>
          <input
            type="range"
            min={0}
            max={1.6}
            step={0.05}
            value={theme.radius}
            onChange={(e) => setTheme({ radius: Number(e.target.value) })}
            className="w-full cursor-pointer"
            aria-label="Border radius"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs text-muted-foreground font-medium">UI density</Label>
          <div className="grid grid-cols-3 gap-2">
            {DENSITY_OPTIONS.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setTheme({ density: d.id })}
                title={d.hint}
                className={cn(
                  "px-3 py-2.5 text-xs font-medium rounded-xl border transition-all cursor-pointer",
                  theme.density === d.id
                    ? "bg-primary/10 text-primary border-primary/40"
                    : "text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
                )}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* ── Colors ────────────────────────────────────────────────────── */}
      <Card icon={Palette} title="Colors">
        <div className="grid gap-3 sm:grid-cols-2">
          {COLORS.map((c) => (
            <ColorField
              key={c.key}
              label={c.label}
              hint={c.hint}
              value={theme.colors[c.key]}
              onChange={(hex) => changeColor(c.key, hex)}
            />
          ))}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <Sun className="w-3.5 h-3.5 text-primary shrink-0" />
          <span>Light/dark mode still follows General › Theme. Custom colors apply in dark mode.</span>
        </div>
      </Card>

      {/* ── Motion ────────────────────────────────────────────────────── */}
      <Card icon={Sparkles} title="Effects & Motion">
        <Row
          label="Ambient glow"
          hint="The Aurora glow behind the app shell."
          checked={theme.glow}
          onChange={(v) => setTheme({ glow: v })}
        />
        <Row
          label="Interface animations"
          hint="Fades, transitions and animated accents."
          checked={theme.animations}
          onChange={(v) => setTheme({ animations: v })}
        />
      </Card>
      </div>
      )}
    </div>
  );
}
