'use client';

// ── Settings › Voice (read aloud) ───────────────────────────────────────────
// Read-aloud for assistant replies. This pane is deliberately separate from
// Settings › Sound: UI cues and spoken replies are different systems with
// different controls (voice, rate, pitch, auto-speak). Everything is device-
// local and speaks through the browser's own voices — reply text is never sent
// to a server, and there is no key to configure.
//
// When the Web Speech API is missing the pane says so plainly instead of
// showing dead controls.

import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Play, RotateCcw, Square, Volume2 } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { tts, useTts, useTtsStore } from '@/lib/tts';
import { Field, Panel, SubSection, Toggle } from './settings-ui';

const PREVIEW_TEXT =
  'Eclipse will read replies aloud at this pace and volume. Numbers, tables and citations are skipped.';
const PREVIEW_KEY = '__tts_preview__';

export function VoiceSettingsPanel() {
  const { available, speakingKey, prefs, preview, stop } = useTts();
  const setEnabled = useTtsStore((store) => store.setEnabled);
  const setAutoSpeak = useTtsStore((store) => store.setAutoSpeak);
  const setVoiceURI = useTtsStore((store) => store.setVoiceURI);
  const setRate = useTtsStore((store) => store.setRate);
  const setPitch = useTtsStore((store) => store.setPitch);
  const setVolume = useTtsStore((store) => store.setVolume);
  const reset = useTtsStore((store) => store.reset);

  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() => tts.voices());

  useEffect(() => {
    let alive = true;
    void tts.loadVoices().then((list) => {
      if (alive) setVoices(list);
    });
    return () => {
      alive = false;
    };
  }, []);

  const groups = useMemo(() => {
    const byLang = new Map<string, SpeechSynthesisVoice[]>();
    for (const voice of voices) {
      const lang = voice.lang || 'other';
      const list = byLang.get(lang) ?? [];
      list.push(voice);
      byLang.set(lang, list);
    }
    return [...byLang.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([lang, list]) => [lang, [...list].sort((a, b) => a.name.localeCompare(b.name))] as const);
  }, [voices]);

  const previewing = speakingKey === PREVIEW_KEY;

  if (!available) {
    return (
      <Panel className="p-5 md:p-6">
        <div className="flex items-start gap-3">
          <span className="mt-px flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-300">
            <AlertCircle size={15} />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Read-aloud is unavailable here</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Eclipse speaks through your browser&apos;s built-in Web Speech API, which this
              environment does not expose. Try a Chromium-based browser (Chrome or Edge) or
              install a system voice. Nothing is sent to a server either way.
            </p>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <div className="space-y-5">
      <Panel className="p-5 md:p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Read replies aloud</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Adds a Speak control to every assistant reply. Speaks on this device with the
              browser&apos;s voices — your conversation is never uploaded for narration.
            </p>
          </div>
          <Toggle checked={prefs.enabled} onChange={setEnabled} />
        </div>

        <div className="flex items-start justify-between gap-4 border-t border-border/20 pt-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Speak new replies automatically</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              When a turn finishes, read the answer without pressing Speak. Off by default —
              opt in only if you want a hands-free conversation.
            </p>
          </div>
          <Toggle
            checked={prefs.autoSpeak}
            onChange={setAutoSpeak}
            disabled={!prefs.enabled}
          />
        </div>
      </Panel>

      <Panel className="p-5 md:p-6 space-y-5">
        <SubSection
          icon={Volume2}
          title="Voice"
          description="Voices come from your operating system and browser. The list can be empty until the system finishes loading them."
        >
          <Field label="Voice" hint={prefs.voiceURI ? undefined : 'Automatic picks a voice that matches your system language.'}>
            <Select
              value={prefs.voiceURI ?? 'auto'}
              onValueChange={(value) => setVoiceURI(!value || value === 'auto' ? null : value)}
            >
              <SelectTrigger className="h-auto w-full justify-between py-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value="auto">Automatic (system default)</SelectItem>
                {groups.map(([lang, list]) => (
                  <SelectGroup key={lang}>
                    <SelectLabel>{lang}</SelectLabel>
                    {list.map((voice) => (
                      <SelectItem key={voice.voiceURI} value={voice.voiceURI}>
                        {voice.name}
                        {voice.localService ? '' : ' (network)'}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {groups.length === 0 && (
            <p className="text-[10px] leading-relaxed text-amber-300/80">
              No system voices are available yet. The Speak controls stay hidden until one
              loads — nothing is simulated.
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={`Rate · ${prefs.rate.toFixed(2)}×`}>
              <input
                type="range"
                min={0.5}
                max={2}
                step={0.05}
                value={prefs.rate}
                onChange={(event) => setRate(Number(event.target.value))}
                className="w-full cursor-pointer"
                aria-label="Speech rate"
              />
            </Field>
            <Field label={`Pitch · ${prefs.pitch.toFixed(2)}`}>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={prefs.pitch}
                onChange={(event) => setPitch(Number(event.target.value))}
                className="w-full cursor-pointer"
                aria-label="Speech pitch"
              />
            </Field>
            <Field label={`Volume · ${Math.round(prefs.volume * 100)}%`}>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={prefs.volume}
                onChange={(event) => setVolume(Number(event.target.value))}
                className="w-full cursor-pointer"
                aria-label="Speech volume"
              />
            </Field>
            <div className="flex items-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  if (previewing) stop();
                  else preview(PREVIEW_TEXT);
                }}
              >
                {previewing ? <Square size={13} /> : <Play size={13} />}
                {previewing ? 'Stop' : 'Preview'}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={reset}>
                <RotateCcw size={13} /> Reset
              </Button>
            </div>
          </div>
        </SubSection>
      </Panel>

      <p className={cn('px-1 text-[10px] leading-relaxed text-muted-foreground/70')}>
        Code blocks, tables and structured-response JSON are converted to prose before speaking;
        raw Markdown symbols and URLs are never read out.
      </p>
    </div>
  );
}

export default VoiceSettingsPanel;
