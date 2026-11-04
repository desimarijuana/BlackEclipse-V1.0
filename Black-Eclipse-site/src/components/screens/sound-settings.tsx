"use client";

// ── Settings › Sound ────────────────────────────────────────────────────────
// A dedicated, fully customisable UI-sound surface:
//   * Master on/off, volume, and mode (all cues vs essential only).
//   * Voice-pack picker — audition each pack across every cue.
//   * Per-cue controls: volume, mute, upload a custom clip, reset.
//   * A live "cues" board to test every sound on demand.
//
// Everything flows through `useSoundStore` (persisted in localStorage), so the
// preference survives reloads with no server round-trip.

import { useRef, useState } from "react";
import {
  Volume2, VolumeX, Play, Upload, RotateCcw, Check, Music2, Bell,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  DEFAULT_PACK,
  SOUND_DEFINITIONS,
  SOUND_NAMES,
  SOUND_PACKS,
  sound,
  useSoundStore,
  type SoundName,
  type SoundPackId,
} from "@/lib/sounds";

function Card({
  icon: Icon, title, children, trailing,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="space-y-5 rounded-2xl border border-white/10 dark:border-white/5 glass-card p-5 md:p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
          <Icon className="w-4 h-4 text-primary shrink-0" />
          <span>{title}</span>
        </div>
        {trailing}
      </div>
      {children}
    </div>
  );
}

// Cues that announce something happening OUTSIDE the current view. They get
// their own card so the operator can decide about them explicitly instead of
// hunting through the generic cue list. These are event notifications: they
// play independently of the interaction-audio master switch, and this card is
// their documented opt-out. Interaction cues (click/tick/toggle) remain
// opt-in and off by default.
const NOTIFICATION_CUES: readonly SoundName[] = ["message", "notification", "taskdone"];

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
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

function MiniSlider({
  value, min, max, step, onChange, label, disabled,
}: {
  value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; label: string; disabled?: boolean;
}) {
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      aria-label={label}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full cursor-pointer disabled:opacity-40"
    />
  );
}

/** Reads a user-selected audio file and stores it as a small data URL. */
async function fileToDataUrl(file: File): Promise<string | undefined> {
  if (!file.type.startsWith("audio/") && !/\.(wav|mp3|ogg|m4a|aac|webm)$/i.test(file.name)) return undefined;
  if (file.size > 1_500_000) return undefined; // keep localStorage happy
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : undefined);
    reader.onerror = () => resolve(undefined);
    reader.readAsDataURL(file);
  });
}

function CueRow({ name }: { name: SoundName }) {
  const cue = useSoundStore((s) => s.prefs.cues[name]);
  const setCueVolume = useSoundStore((s) => s.setCueVolume);
  const setCueMuted = useSoundStore((s) => s.setCueMuted);
  const setCueCustom = useSoundStore((s) => s.setCueCustom);
  const resetCue = useSoundStore((s) => s.resetCue);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const def = SOUND_DEFINITIONS[name];
  const customized = cue.custom !== undefined || cue.volume !== 1 || cue.muted;

  const onPick = async (file: File | undefined) => {
    if (!file) return;
    const dataUrl = await fileToDataUrl(file);
    if (dataUrl) setCueCustom(name, dataUrl);
  };

  return (
    <div className={cn(
      "rounded-xl border p-3 space-y-3 transition-colors",
      cue.muted ? "border-border/20 opacity-60" : "border-border/30",
    )}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-foreground flex items-center gap-2">
            {def.label}
            {customized && <span className="text-[9px] font-bold text-primary border border-primary/30 rounded-full px-1.5 py-0.5">custom</span>}
          </p>
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">{def.hint}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => sound.play(name)}
            aria-label={`Test ${def.label}`}
            title="Test"
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 text-muted-foreground hover:text-foreground hover:border-border cursor-pointer"
          >
            <Play size={12} />
          </button>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            aria-label={`Upload custom ${def.label}`}
            title="Upload custom clip"
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 text-muted-foreground hover:text-foreground hover:border-border cursor-pointer"
          >
            <Upload size={12} />
          </button>
          {customized && (
            <button
              type="button"
              onClick={() => resetCue(name)}
              aria-label={`Reset ${def.label}`}
              title="Reset"
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 text-muted-foreground hover:text-foreground hover:border-border cursor-pointer"
            >
              <RotateCcw size={12} />
            </button>
          )}
          <Toggle
            checked={!cue.muted}
            label={`${def.label} enabled`}
            onChange={(on) => setCueMuted(name, !on)}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <VolumeX size={13} className="text-muted-foreground shrink-0" />
        <MiniSlider
          label={`${def.label} volume`}
          value={Math.round(cue.volume * 100)}
          min={0}
          max={200}
          step={5}
          disabled={cue.muted}
          onChange={(v) => setCueVolume(name, v / 100)}
        />
        <span className="text-[10px] font-mono text-muted-foreground w-10 text-right shrink-0">
          {Math.round(cue.volume * 100)}%
        </span>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*,.wav,.mp3,.ogg,.m4a,.aac,.webm"
        className="hidden"
        onChange={(e) => { void onPick(e.target.files?.[0]); e.target.value = ""; }}
      />
    </div>
  );
}

export function SoundSettingsPanel() {
  const prefs = useSoundStore((s) => s.prefs);
  const setEnabled = useSoundStore((s) => s.setEnabled);
  const setVolume = useSoundStore((s) => s.setVolume);
  const setMode = useSoundStore((s) => s.setMode);
  const setPack = useSoundStore((s) => s.setPack);
  const reset = useSoundStore((s) => s.reset);
  const [testing, setTesting] = useState(false);

  const auditionPack = (id: SoundPackId) => {
    setPack(id);
    sound.invalidate();
    sound.tick();
  };

  const testAll = async () => {
    setTesting(true);
    for (const name of SOUND_NAMES) {
      sound.play(name);
      await new Promise((r) => setTimeout(r, 420));
    }
    setTesting(false);
  };

  return (
    <div className="space-y-6">
      {/* ── Master ─────────────────────────────────────────────────── */}
      <Card
        icon={prefs.enabled ? Volume2 : VolumeX}
        title="UI Sounds"
        trailing={
          <Toggle
            checked={prefs.enabled}
            label="UI sounds enabled"
            onChange={(v) => { setEnabled(v); if (v) sound.click(); }}
          />
        }
      >
        <div className="flex items-center gap-4">
          <VolumeX size={15} className="text-muted-foreground shrink-0" />
          <MiniSlider
            label="Master volume"
            value={Math.round(prefs.volume * 100)}
            min={0}
            max={100}
            step={1}
            disabled={!prefs.enabled}
            onChange={(v) => setVolume(v / 100)}
          />
          <span className="text-[11px] font-mono text-muted-foreground w-10 text-right shrink-0">
            {Math.round(prefs.volume * 100)}%
          </span>
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground font-medium">Mode</Label>
          <div className="grid grid-cols-2 gap-2">
            {([
              { id: "all", label: "All cues", hint: "Navigation, actions, toggles, alerts" },
              { id: "essential", label: "Essential only", hint: "Clicks, tabs and toggles" },
            ] as const).map((m) => (
              <button
                key={m.id}
                type="button"
                data-sound="toggle"
                disabled={!prefs.enabled}
                aria-pressed={prefs.mode === m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  "flex flex-col items-start gap-0.5 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer disabled:opacity-40",
                  prefs.mode === m.id
                    ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                    : "border-border/40 hover:border-border",
                )}
              >
                <span className="text-xs font-medium text-foreground">{m.label}</span>
                <span className="text-[10px] text-muted-foreground/70">{m.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 pt-1">
          <p className="text-[10px] text-muted-foreground/70">
            Interaction sounds (clicks, tabs, toggles) are opt-in and off by default; they play only after your
            first interaction — never on hover, typing or live price updates. Event notifications (AI result,
            alerts, task done) play while UI sounds are off until you mute them in the card below.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-xl shrink-0"
            disabled={!prefs.enabled || testing}
            onClick={() => void testAll()}
          >
            <Play className="w-3.5 h-3.5 mr-1" /> Test all
          </Button>
        </div>
      </Card>

      {/* ── Notifications & alarms ─────────────────────────────────── */}
      <Card icon={Bell} title="Notifications & alarms">
        <p className="text-[10px] text-muted-foreground -mt-2">
          Whether these events make a sound — decide it here. All three are event
          notifications: they play even while UI sounds are off, so switch off the ones
          you do not want below (or with the same toggles under Settings › Alerts).
        </p>
        <div className="space-y-3">
          {NOTIFICATION_CUES.map((name) => (
            <CueRow key={name} name={name} />
          ))}
        </div>
      </Card>

      {/* ── Voice pack ─────────────────────────────────────────────── */}
      <Card icon={Music2} title="Sound Pack">
        <p className="text-[10px] text-muted-foreground -mt-2">
          Choose the voice for every cue. Click a pack to audition its tick.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {SOUND_PACKS.map((pack) => {
            const active = prefs.pack === pack.id;
            return (
              <button
                key={pack.id}
                type="button"
                disabled={!prefs.enabled}
                aria-pressed={active}
                onClick={() => auditionPack(pack.id)}
                className={cn(
                  "flex items-start gap-3 px-3 py-2.5 rounded-xl border text-left transition-all cursor-pointer disabled:opacity-40",
                  active
                    ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                    : "border-border/30 hover:border-border/60",
                )}
              >
                <span className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                  active ? "border-primary bg-primary" : "border-muted-foreground/40",
                )}>
                  {active && <Check size={10} className="text-primary-foreground" />}
                </span>
                <span className="min-w-0">
                  <span className="text-xs font-semibold text-foreground block">{pack.label}</span>
                  <span className="text-[10px] text-muted-foreground/70 block mt-0.5">{pack.description}</span>
                </span>
              </button>
            );
          })}
        </div>
      </Card>

      {/* ── Per-cue ────────────────────────────────────────────────── */}
      <Card
        icon={Volume2}
        title="Cue Customisation"
        trailing={
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer rounded-xl"
            onClick={reset}
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset all
          </Button>
        }
      >
        <p className="text-[10px] text-muted-foreground -mt-2">
          Fine-tune the remaining cues — volume, mute, or upload your own audio file.
        </p>
        <div className="space-y-3">
          {SOUND_NAMES.filter((name) => !NOTIFICATION_CUES.includes(name)).map((name) => (
            <CueRow key={name} name={name} />
          ))}
        </div>
      </Card>
    </div>
  );
}
