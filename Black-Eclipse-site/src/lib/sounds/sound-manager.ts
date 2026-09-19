// ── Sound manager ───────────────────────────────────────────────────────────
// A tiny singleton wrapper around Howler.js that plays the UI cue set. It is
// intentionally defensive because audio is a non-essential enhancement:
//   * Howler is loaded lazily on the first user gesture, which both satisfies
//     browser autoplay policies and keeps it out of the SSR/server bundle.
//   * Every failure path (unsupported browser, blocked context, decode error)
//     is swallowed — audio never blocks or breaks an interaction.
//   * Per-cue throttling coalesces rapid clicks into a single, clean tick.

import type { Howl } from 'howler';
import { SOUND_DEFINITIONS, type SoundName } from './config';
import { useSoundStore } from './store';

type HowlMap = Partial<Record<SoundName, Howl>>;

class SoundManager {
  private howls: HowlMap = {};
  private loaded = false;
  private loading: Promise<void> | null = null;
  private unlocked = false;
  private lastPlayed: Partial<Record<SoundName, number>> = {};

  /** Whether audio can currently be played (browser + user prefs). */
  private canPlay(): boolean {
    if (typeof window === 'undefined') return false;
    if (!this.unlocked) return false;
    return useSoundStore.getState().prefs.enabled;
  }

  /**
   * Arm audio after the first real user gesture. Safe to call repeatedly.
   * Never throws.
   */
  unlock = (): void => {
    if (typeof window === 'undefined') return;
    this.unlocked = true;
    void this.ensureLoaded();
  };

  private ensureLoaded(): Promise<void> {
    if (this.loaded) return Promise.resolve();
    if (this.loading) return this.loading;

    this.loading = (async () => {
      try {
        const { Howl: HowlCtor } = await import('howler');
        const next: HowlMap = {};
        for (const [name, def] of Object.entries(SOUND_DEFINITIONS) as [SoundName, (typeof SOUND_DEFINITIONS)[SoundName]][]) {
          next[name] = new HowlCtor({
            src: [def.src],
            format: ['wav'],
            preload: true,
            html5: false,
            volume: 0,
          });
        }
        this.howls = next;
        this.loaded = true;
      } catch {
        // Audio unsupported or blocked — remain a silent no-op.
        this.howls = {};
        this.loaded = true;
      }
    })();

    return this.loading;
  }

  /** Play a cue if it is enabled and not currently throttled. */
  play = (name: SoundName): void => {
    if (!this.canPlay()) return;

    const def = SOUND_DEFINITIONS[name];
    const now = Date.now();
    const last = this.lastPlayed[name] ?? 0;
    if (now - last < def.throttleMs) return;
    this.lastPlayed[name] = now;

    void this.ensureLoaded().then(() => {
      const howl = this.howls[name];
      if (!howl) return;
      try {
        const master = useSoundStore.getState().prefs.volume;
        howl.volume(Math.min(1, Math.max(0, master * def.volume)));
        howl.play();
      } catch {
        /* playback blocked — ignore */
      }
    });
  };

  click = (): void => this.play('click');
  tick = (): void => this.play('tick');
  toggle = (): void => this.play('toggle');
  success = (): void => this.play('success');
  error = (): void => this.play('error');
  notification = (): void => this.play('notification');

  /**
   * Explicit event bus hook. A caller that knows the semantic outcome of an
   * async action (e.g. a research run) can dispatch `eclipse:sound` with a
   * detail of `{ name }` and it will play without importing the manager.
   */
  handleEvent = (event: Event): void => {
    const name = (event as CustomEvent<{ name?: unknown }>).detail?.name;
    if (typeof name === 'string' && name in SOUND_DEFINITIONS) {
      this.play(name as SoundName);
    }
  };
}

export const sound = new SoundManager();

/** Convenience helper for dispatching an explicit sound request. */
export function requestSound(name: SoundName): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('eclipse:sound', { detail: { name } }));
}
