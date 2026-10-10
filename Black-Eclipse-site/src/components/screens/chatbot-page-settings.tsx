"use client";

// ── Settings › Customization › ChatBot Page ─────────────────────────────────
// Everything that makes the ChatBot page look like *yours*: the conversation
// typeface, and the full backdrop (wallpaper / solid fill) plus the giant
// landing wordmark. The backdrop controls live in `BackgroundSettingsPanel`
// (its own store, moved here from General); the conversation font is a small
// self-contained preference (`lib/chat/appearance`). Both autosave, so this tab
// deliberately sits outside the theme draft/Apply model.

import { Check, MessageSquareText, RotateCcw, Type } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CHAT_FONT_OPTIONS,
  useChatAppearanceStore,
} from "@/lib/chat/appearance";
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
        description="Wallpapers and solid fills paint the ChatBot page only. The giant wordmark sits behind the empty landing."
      >
        <BackgroundSettingsPanel />
      </Card>
    </div>
  );
}
