"use client";

// ── Settings › Customization › ChatBot Page ─────────────────────────────────
// Everything that makes the ChatBot page look like *yours*: the conversation
// typeface, and the full backdrop (wallpaper / solid fill) plus the giant
// landing wordmark. The backdrop controls live in `BackgroundSettingsPanel`
// (its own store, moved here from General); the conversation font is a small
// self-contained preference (`lib/chat/appearance`). Both autosave, so this tab
// deliberately sits outside the theme draft/Apply model.

import { Check, MessageSquareText, Palette, RotateCcw, Type } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CHAT_FONT_OPTIONS,
  useChatAppearanceStore,
} from "@/lib/chat/appearance";
import {
  CHAT_SURFACE_FILL_OPTIONS,
  useBackgroundStore,
  type ChatSurfaceFill,
} from "@/lib/backgrounds";
import { Field, Toggle } from "./settings-ui";
import { BackgroundSettingsPanel } from "./background-settings";

function Card({ icon: Icon, title, description, children }: {
  icon: React.ElementType;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-5 rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6">
      <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
        <Icon className="w-4 h-4 text-primary shrink-0" />
        <span>{title}</span>
      </div>
      {description && <p className="text-[10px] text-muted-foreground -mt-2">{description}</p>}
      {children}
    </div>
  );
}

/** A color picker row with an explicit "Theme" reset, shared by the chat-surface
 *  dark/light/end controls. */
function ColorRow({ value, fallback, pickFallback, onChange, label, resetLabel = "Theme" }: {
  value: string;
  fallback: string;
  pickFallback: string;
  onChange: (v: string) => void;
  label: string;
  resetLabel?: string;
}) {
  const activeCls = "bg-primary/10 text-primary border-primary/40";
  const idleCls = "text-muted-foreground border-border/40 hover:text-foreground hover:border-border";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label
        className="relative h-9 w-9 shrink-0 cursor-pointer overflow-hidden rounded-xl border border-border/40"
        style={{ backgroundColor: value || fallback }}
        title={label}
      >
        <input
          type="color"
          value={value || pickFallback}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          aria-label={label}
        />
      </label>
      <button
        type="button"
        onClick={() => onChange("")}
        className={cn("rounded-xl border px-3 py-2 text-xs font-medium transition-all cursor-pointer", !value ? activeCls : idleCls)}
      >
        {resetLabel}
      </button>
      {value && <span className="font-mono text-[11px] text-muted-foreground/80">{value}</span>}
    </div>
  );
}

/** The chat-conversation surface: a flat/gradient fill behind the transcript and
 *  composer, independent of the page backdrop. On by default. */
function ChatBackgroundCard() {
  const enabled = useBackgroundStore((s) => s.prefs.chatSurfaceEnabled);
  const fill = useBackgroundStore((s) => s.prefs.chatSurfaceFill);
  const color = useBackgroundStore((s) => s.prefs.chatSurfaceColor);
  const colorLight = useBackgroundStore((s) => s.prefs.chatSurfaceColorLight);
  const color2 = useBackgroundStore((s) => s.prefs.chatSurfaceColor2);
  const opacity = useBackgroundStore((s) => s.prefs.chatSurfaceOpacity);
  const bubbleDark = useBackgroundStore((s) => s.prefs.chatBubbleColor);
  const bubbleLight = useBackgroundStore((s) => s.prefs.chatBubbleColorLight);
  const setPrefs = useBackgroundStore((s) => s.setPrefs);

  const activeCls = "bg-primary/10 text-primary border-primary/40";
  const idleCls = "text-muted-foreground border-border/40 hover:text-foreground hover:border-border";

  return (
    <Card
      icon={Palette}
      title="Chat background"
      description="A surface behind the conversation itself — the transcript and composer — separate from the page backdrop above. On by default: near-black in dark mode, matte off-white in light."
    >
      <div className="flex items-center justify-between gap-4">
        <span className="text-xs font-medium text-foreground/80">Custom chat surface</span>
        <Toggle checked={enabled} onChange={(v) => setPrefs({ chatSurfaceEnabled: v })} />
      </div>

      {enabled && (
        <>
          <Field label="Style" hint="A flat color, or a two-color wash.">
            <div className="grid grid-cols-2 gap-2">
              {CHAT_SURFACE_FILL_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setPrefs({ chatSurfaceFill: opt.id as ChatSurfaceFill })}
                  className={cn(
                    "flex flex-col items-start gap-0.5 rounded-xl border px-3 py-2.5 text-left text-xs font-medium transition-all cursor-pointer",
                    fill === opt.id ? activeCls : cn("bg-transparent", idleCls),
                  )}
                >
                  <span>{opt.label}</span>
                  <span className="text-[10px] font-normal opacity-70">{opt.hint}</span>
                </button>
              ))}
            </div>
          </Field>

          <Field
            label={fill === "gradient" ? "Start color — dark" : "Color — dark"}
            hint="Used in dark mode. Leave on Theme to follow the theme's card surface."
          >
            <ColorRow
              value={color}
              fallback="var(--card)"
              pickFallback="#0a0b0b"
              onChange={(v) => setPrefs({ chatSurfaceColor: v })}
              label="Chat background color (dark)"
            />
          </Field>

          <Field
            label={fill === "gradient" ? "Start color — light" : "Color — light"}
            hint="Used in light mode. Leave on Theme to follow the theme's card surface."
          >
            <ColorRow
              value={colorLight}
              fallback="var(--card)"
              pickFallback="#f4f4f5"
              onChange={(v) => setPrefs({ chatSurfaceColorLight: v })}
              label="Chat background color (light)"
            />
          </Field>

          {fill === "gradient" && (
            <Field label="Color (end)" hint="Leave on Brand for a tint derived from your theme's brand color. Shared by both schemes.">
              <ColorRow
                value={color2}
                fallback="rgb(var(--brand-rgb) / 0.55)"
                pickFallback="#00ff41"
                onChange={(v) => setPrefs({ chatSurfaceColor2: v })}
                label="Chat background gradient end color"
              />
            </Field>
          )}

          <Field label="Strength" hint="Lower it to let the page backdrop show through the chat surface.">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={opacity}
                onChange={(e) => setPrefs({ chatSurfaceOpacity: Number(e.target.value) })}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-primary"
              />
              <span className="w-10 shrink-0 text-right font-mono text-[11px] text-muted-foreground/80">{opacity}%</span>
            </div>
          </Field>

          <div className="space-y-4 border-t border-white/10 dark:border-white/5 pt-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
              <Palette className="w-4 h-4 text-primary shrink-0" />
              <span>Prompt bubble</span>
            </div>
            <p className="text-[10px] text-muted-foreground/70 -mt-2">
              The background of your own prompts (the user bubbles). Empty follows the default neutral tint.
            </p>
            <Field label="Color — dark" hint="Bubble fill in dark mode. Leave on Default for the neutral tint.">
              <ColorRow
                value={bubbleDark}
                fallback="color-mix(in srgb, var(--foreground) 30%, transparent)"
                pickFallback="#4c4c4c"
                onChange={(v) => setPrefs({ chatBubbleColor: v })}
                label="Prompt bubble color (dark)"
                resetLabel="Default"
              />
            </Field>
            <Field label="Color — light" hint="Bubble fill in light mode. Leave on Default for the neutral tint.">
              <ColorRow
                value={bubbleLight}
                fallback="color-mix(in srgb, var(--foreground) 10%, transparent)"
                pickFallback="#e4e4e7"
                onChange={(v) => setPrefs({ chatBubbleColorLight: v })}
                label="Prompt bubble color (light)"
                resetLabel="Default"
              />
            </Field>
          </div>

          <p className="text-[10px] text-muted-foreground/60">Applies to the Eclipse Agent page conversation. Changes apply instantly.</p>
        </>
      )}
    </Card>
  );
}

export function ChatbotPageSettings() {
  const font = useChatAppearanceStore((s) => s.appearance.font);
  const setAppearance = useChatAppearanceStore((s) => s.setAppearance);
  const reset = useChatAppearanceStore((s) => s.reset);

  const previewFont = font || "var(--font-sans)";

  return (
    <div className="animate-fade-in-up space-y-6">
      {/* Conversation typeface */}
      <Card
        icon={MessageSquareText}
        title="Conversation font"
        description="The typeface for your prompts, the assistant's replies and the composer. Every option is a real, self-hosted face — “App font” follows your UI font from the Theme tab."
      >
        <div
          className="rounded-xl border border-border/30 bg-background/40 px-4 py-3 text-foreground"
          style={{ fontFamily: previewFont }}
          aria-hidden
        >
          <p className="text-[15px]">How did NVDA close today?</p>
          <p className="mt-1 text-[15px] text-muted-foreground">
            Maybe it&apos;s a good time to assess your portfolio&apos;s tech exposure — here is the latest.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {CHAT_FONT_OPTIONS.map((f) => (
            <button
              key={f.label}
              type="button"
              onClick={() => setAppearance({ font: f.value })}
              title={f.label}
              aria-pressed={font === f.value}
              className={cn(
                "flex items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-all cursor-pointer",
                font === f.value
                  ? "bg-primary/10 text-primary border-primary/40"
                  : "bg-transparent text-muted-foreground border-border/40 hover:text-foreground hover:border-border",
              )}
            >
              <span
                className="truncate text-sm leading-tight"
                style={{ fontFamily: f.value || "var(--font-sans)" }}
              >
                {f.label}
              </span>
              {font === f.value && <Check className="w-3.5 h-3.5 shrink-0 text-primary" />}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground/60">Changes apply instantly.</p>
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-xl"
            disabled={!font}
            onClick={reset}
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> Use app font
          </Button>
        </div>
      </Card>

      {/* Backdrop + giant landing wordmark (the panel that used to live in
          Settings › General › Background). */}
      <Card
        icon={Type}
        title="Backdrop & landing wordmark"
        description="Wallpapers and solid fills paint the Eclipse Agent page only. The giant wordmark sits behind the empty landing."
      >
        <BackgroundSettingsPanel />
      </Card>

      {/* Chat conversation surface — the transcript + composer background. */}
      <ChatBackgroundCard />
    </div>
  );
}
