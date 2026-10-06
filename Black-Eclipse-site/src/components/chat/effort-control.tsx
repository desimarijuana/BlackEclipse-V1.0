"use client";

// ── EffortControl — the composer's "model intelligence" slider ───────────────
// A compact pill beside the model selector that opens a popover with a
// Faster → Smarter slider. Each stop is one of the shared reasoning-effort
// levels (`@/lib/agent/reasoning`), so the composer, Settings › AI and the
// runtime can never disagree about the vocabulary. Auto (the default) sends no
// override: the run falls back to the operator's saved default and then the
// runtime's task profile.
//
// It is a PER-QUESTION override, not a settings edit — it applies to the next
// run only and never writes the global `LLMConfig.reasoningEffort`.
//
// The popover is rendered through a portal (base-ui Popover) so its frosted
// glass samples the real page (see the UI skill's backdrop-root rule).

import { useState } from "react";
import { Slider as SliderPrimitive } from "@base-ui/react/slider";
import { Popover as PopoverPrimitive } from "@base-ui/react/popover";
import { Brain, ChevronDown, HelpCircle } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  EFFORT_STOPS,
  type ReasoningOption,
  type ReasoningLevel,
} from "@/lib/agent/reasoning";

/** Per-skin styling — all driven by the theme's tokens (`--primary` green,
 *  `--border`, `--muted`), never a foreign palette. The track fills with the
 *  primary accent as effort rises; the top stop glows. */
function skin(option: ReasoningOption): {
  label: string;
  track: string;
  fill: string;
} {
  switch (option.skin) {
    case "aurora":
      return {
        label: "text-primary",
        track: "bg-primary/[0.06] border border-primary/30",
        fill: "bg-gradient-to-r from-primary/20 via-primary/45 to-primary/75",
      };
    case "violet":
      return {
        label: "text-foreground",
        track: "bg-foreground/[0.04] border border-border/40",
        fill: "bg-gradient-to-r from-primary/15 to-primary/45",
      };
    default:
      return {
        label: "text-foreground",
        track: "bg-foreground/[0.04] border border-border/40",
        fill: "bg-foreground/20",
      };
  }
}

export interface EffortControlProps {
  /** The current per-question override (`undefined` = Auto). */
  value: ReasoningLevel | undefined;
  /** Slider index (Auto = 0). */
  index: number;
  onIndexChange: (index: number) => void;
  /** Disable while a run is in flight. */
  disabled?: boolean;
}

export function EffortControl({ value, index, onIndexChange, disabled = false }: EffortControlProps) {
  const [helpOpen, setHelpOpen] = useState(false);
  const selected = EFFORT_STOPS[index] ?? EFFORT_STOPS[0];
  const tint = skin(selected);
  const isOverride = value !== undefined;
  const ultra = selected.skin === "aurora";

  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger
        disabled={disabled}
        title={`Effort: ${selected.label}${isOverride ? "" : " (Auto)"} — set thinking for this question`}
        aria-label="Reasoning effort for this question"
        className={cn(
          "relative inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 h-7 rounded-full border text-xs font-medium whitespace-nowrap transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default",
          // Ultra gets a live energy skin on the PILL itself, so the effect is
          // visible at rest (the popover that carries it closes on pick).
          ultra
            ? "bg-primary/15 border-primary/45 text-primary overflow-visible"
            : isOverride
              ? cn("bg-accent/25 border-border/40", tint.label)
              : "bg-accent/25 border-border/25 text-muted-foreground hover:text-foreground hover:border-border/40",
        )}
      >
        {/* A slim laser beam sweeping the pill while Ultra is active. */}
        {ultra && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 overflow-hidden rounded-full"
          >
            <span className="effort-ultra-beam absolute inset-y-0" />
          </span>
        )}
        <span className="relative">
          <EnergyBrain size={13} />
        </span>
        <span className="relative max-w-[76px] truncate">{selected.label}</span>
        <ChevronDown size={13} className="relative shrink-0 opacity-70" />
      </PopoverPrimitive.Trigger>

      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Positioner side="top" align="end" sideOffset={8} className="isolate z-[120] outline-none">
          <PopoverPrimitive.Popup
            data-slot="effort-popup"
            className="w-[300px] origin-(--transform-origin) overflow-visible glass-tooltip p-3.5 text-popover-foreground outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
          >
            {/* Header — "Effort <Level>" + help. */}
            <div className="mb-3 flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Effort</span>
              <span className={cn("text-sm font-semibold", tint.label)}>{selected.label}</span>
              <button
                type="button"
                onClick={() => setHelpOpen((v) => !v)}
                aria-expanded={helpOpen}
                aria-label="What is effort?"
                className="ml-auto rounded-full p-0.5 text-muted-foreground/60 transition-colors hover:text-foreground cursor-pointer"
              >
                <HelpCircle size={14} />
              </button>
            </div>

            {/* Faster → Smarter labels. */}
            <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted-foreground/70">
              <span>Faster</span>
              <span>Smarter</span>
            </div>

            {/* The slider. */}
            <SliderPrimitive.Root
              min={0}
              max={EFFORT_STOPS.length - 1}
              step={1}
              value={index}
              disabled={disabled}
              onValueChange={(v) => onIndexChange(typeof v === "number" ? v : v[0])}
              className="w-full"
            >
              <SliderPrimitive.Control className="flex h-9 w-full touch-none items-center select-none">
                <SliderPrimitive.Track className={cn("relative h-8 w-full rounded-full", tint.track)}>
                  {/* Resting tick dots for each stop. */}
                  <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-between px-3">
                    {EFFORT_STOPS.map((s, i) => (
                      <span
                        key={s.label}
                        className={cn(
                          "h-1 w-1 rounded-full",
                          i <= index ? "bg-foreground/50" : "bg-foreground/20",
                        )}
                      />
                    ))}
                  </div>
                  {/* Fill. On Ultra it also carries a laser beam sweeping the
                      full bar (Ultra is the last stop, so the fill spans it). */}
                  <SliderPrimitive.Indicator className={cn("relative h-full overflow-hidden rounded-full", tint.fill)}>
                    {selected.skin === "aurora" && (
                      <span aria-hidden className="effort-ultra-beam pointer-events-none absolute inset-y-0" />
                    )}
                  </SliderPrimitive.Indicator>
                  <Thumb option={selected} />
                </SliderPrimitive.Track>
              </SliderPrimitive.Control>
            </SliderPrimitive.Root>

            {/* Caption. */}
            <p className="mt-2 text-center text-[11px] text-muted-foreground/70">{selected.caption}</p>

            {helpOpen && (
              <div className="mt-3 space-y-1.5 border-t border-white/10 pt-2.5 text-[10.5px] leading-relaxed text-muted-foreground/80">
                <p>{selected.hint}</p>
                <p>
                  Applies to this question only. Used by models with adjustable thinking;
                  other models ignore it.
                </p>
              </div>
            )}
          </PopoverPrimitive.Popup>
        </PopoverPrimitive.Positioner>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

/**
 * The brain mark, in the theme accent. When `energy` is set it throbs and, at
 * the top stop, sits inside the full energy core (glow / plasma / shockwaves /
 * sparks). Defined once so the trigger pill and the slider thumb share it.
 *
 * Uses the dedicated `.effort-accent` class (not `text-primary`): a global CSS
 * remap forces `.text-primary` to muted gray for text, and its `.dark` variant
 * out-specifies the `svg.text-primary` green rule — so an icon needs its own
 * accent class to stay green in both schemes.
 */
function EnergyBrain({ size, energy = false }: { size: number; energy?: boolean }) {
  return <Brain weight="fill" size={size} className={cn("effort-accent", energy && "effort-ultra-core")} />;
}

/**
 * The full energy core shown in the slider's Ultra stop: a glowing, solid-accent
 * brain ringed by a rotating plasma band, two expanding shockwaves and three
 * orbiting sparks. The animation is defined in globals.css and disabled by the
 * global `prefers-reduced-motion` rule, falling back to a static, fully-lit core.
 */
function EnergyCore() {
  return (
    <span className="relative flex h-9 w-9 items-center justify-center">
      {/* Soft outer energy glow. */}
      <span aria-hidden className="effort-ultra-glow absolute h-9 w-9 rounded-full bg-primary/45 blur-md" />
      {/* Expanding shockwaves (two, phase-offset). */}
      <span aria-hidden className="effort-ultra-shock absolute h-9 w-9 rounded-full border border-primary/70" />
      <span aria-hidden className="effort-ultra-shock-2 absolute h-9 w-9 rounded-full border border-primary/50" />
      {/* Rotating plasma ring. */}
      <span aria-hidden className="effort-ultra-plasma absolute h-8 w-8 rounded-full" />
      {/* Orbiting sparks. */}
      <span aria-hidden className="effort-ultra-sparks absolute h-7 w-7">
        {[0, 120, 240].map((deg) => (
          <span
            key={deg}
            className="absolute left-1/2 top-1/2 h-1 w-1 rounded-full bg-primary shadow-[0_0_4px_var(--primary)]"
            style={{ transform: `translate(-50%,-50%) rotate(${deg}deg) translateY(-13px)` }}
          />
        ))}
      </span>
      {/* Dark core disc so the solid accent brain reads clearly, as in the
          reference. */}
      <span aria-hidden className="absolute flex h-7 w-7 items-center justify-center rounded-full bg-background/85 ring-1 ring-primary/40">
        <EnergyBrain size={18} energy />
      </span>
    </span>
  );
}

/**
 * The draggable thumb. At the low/mid stops it is a plain handle; at the top
 * ("Ultra") stop it becomes the pulsing energy core.
 */
function Thumb({ option }: { option: ReasoningOption }) {
  const aurora = option.skin === "aurora";
  return (
    <SliderPrimitive.Thumb
      getAriaLabel={() => "Reasoning effort"}
      getAriaValueText={(_formatted, v) => EFFORT_STOPS[v]?.label ?? ""}
      className={cn(
        "flex items-center justify-center rounded-full outline-none",
        "data-[dragging]:cursor-grabbing cursor-grab",
        aurora && "focus-visible:ring-2 focus-visible:ring-primary/50",
      )}
    >
      {aurora ? (
        <EnergyCore />
      ) : (
        <span
          className={cn(
            "h-5 w-2 rounded-full shadow-sm",
            option.skin === "violet" ? "bg-primary/90" : "bg-foreground/80",
          )}
        />
      )}
    </SliderPrimitive.Thumb>
  );
}
