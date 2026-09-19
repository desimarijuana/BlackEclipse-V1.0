// ── Sound manager ───────────────────────────────────────────────────────────
// A tiny singleton wrapper around Howler.js that plays the UI cue set. It is
// intentionally defensive because audio is a non-essential enhancement:
//   * The Howler module is preloaded eagerly on mount (audio decoding does not
//     require a gesture), but playback is armed only after the first real user
//     gesture. This ordering matters: Howler registers its own context-unlock
//     listeners during module init, so it must be present *before* the gesture
//     for the AudioContext to actually resume.
//   * Every failure path (unsupported browser, blocked context, decode error)
//     is swallowed — audio never blocks or breaks an interaction.
//   * Per-cue throttling coalesces rapid clicks into a single, clean tick.
//
// Sources resolve per play: a user-uploaded `custom` data URL wins, otherwise
// the active pack's bundled asset. Changing the pack or a custom source rebuilds
// that Howl lazily on the next play.

import type { Howl, Howler as HowlerGlobal } from 'howler';
import {
  SOUND_DEFINITIONS,
  isSoundName,
  packSoundSrc,
  type SoundName,
} from './config';
import { useSoundStore } from './store';

type HowlCtor = typeof import('howler').Howl;
type HowlMap = Partial<Record<SoundName, Howl>>;

interface CachedHowl {
  howl: Howl;
  src: string;
}

class SoundManager {
  private cache: Partial<Record<SoundName, CachedHowl>> = {};
  private HowlerRef: HowlerGlobal | null = null;
  private HowlCtor: HowlCtor | null = null;
  private loaded = false;
  private loading: Promise<void> | null = null;
  private unlocked = false;
  private lastPlayed: Partial<Record<SoundName, number>> = {};

  private resolveSrc(name: SoundName): string {
    const { pack, cues } = useSoundStore.getState().prefs;
    const custom = cues[name]?.custom;
    return custom || packSoundSrc(pack, name);
  }

  /** Whether a specific cue can currently be played (browser + user prefs). */
  private canPlay(name: SoundName): boolean {
    if (typeof window === 'undefined') return false;
    if (!this.unlocked) return false;
    const prefs = useSoundStore.getState().prefs;
    if (!prefs.enabled) return false;
    const cue = prefs.cues[name];
    if (cue?.muted) return false;
    if (prefs.mode === 'essential' && !SOUND_DEFINITIONS[name].essential) return false;
    return true;
  }

  /** Preload the Howler module. Safe on mount — needs no gesture. */
  preload = (): void => {
    void this.ensureLoaded();
  };

  /** Arm playback after the first real user gesture. Never throws. */
  unlock = (): void => {
    if (typeof window === 'undefined') return;
    this.unlocked = true;
    void this.ensureLoaded().then(() => {
      try {
        const ctx = this.HowlerRef?.ctx;
        if (ctx && ctx.state !== 'running') void ctx.resume();
      } catch {
        /* context resume blocked — ignore */
      }
    });
  };

  private ensureLoaded(): Promise<void> {
    if (this.loaded) return Promise.resolve();
    if (this.loading) return this.loading;

    this.loading = (async () => {
      try {
        const mod = await import('howler');
        const howlerModule = (mod as unknown as { default?: typeof mod }).default ?? mod;
        const HowlCtor = howlerModule.Howl as HowlCtor | undefined;
        const HowlerGlobal = howlerModule.Howler as HowlerGlobal | undefined;
        if (!HowlCtor) throw new Error('Howler unavailable');
        this.HowlCtor = HowlCtor;
        this.HowlerRef = HowlerGlobal ?? null;
        this.loaded = true;
      } catch {
        this.HowlCtor = null;
        this.HowlerRef = null;
        this.loaded = true;
      }
    })();

    return this.loading;
  }

  /** Get (or lazily build) the Howl for a cue at its current source. */
  private howlFor(name: SoundName): Howl | null {
    const src = this.resolveSrc(name);
    const cached = this.cache[name];
    if (cached && cached.src === src) return cached.howl;
    if (!this.HowlCtor) return null;

    // Tear down a stale Howl before replacing it to free its buffer.
    try { cached?.howl.unload(); } catch { /* ignore */ }

    try {
      const howl = new this.HowlCtor({
        src: [src],
        format: ['wav'],
        preload: true,
        html5: false,
        volume: 0,
      });
      this.cache[name] = { howl, src };
      return howl;
    } catch {
      return null;
    }
  }

  private start(name: SoundName): void {
    const howl = this.howlFor(name);
    if (!howl) return;
    try {
      const prefs = useSoundStore.getState().prefs;
      const gain = prefs.volume * SOUND_DEFINITIONS[name].volume * (prefs.cues[name]?.volume ?? 1);
      howl.volume(Math.min(1, Math.max(0, gain)));
      // A suspended context silently drops playback; resume then play.
      const ctx = this.HowlerRef?.ctx;
      if (ctx && ctx.state !== 'running') {
        ctx.resume().then(() => howl.play()).catch(() => { /* ignore */ });
      } else {
        howl.play();
      }
    } catch {
      /* playback blocked — ignore */
    }
  }

  /** Play a cue if enabled and not currently throttled. */
  play = (name: SoundName): void => {
    if (!this.canPlay(name)) return;

    const def = SOUND_DEFINITIONS[name];
    const now = Date.now();
    const last = this.lastPlayed[name] ?? 0;
    if (now - last < def.throttleMs) return;
    this.lastPlayed[name] = now;

    if (this.loaded) {
      this.start(name);
    } else {
      void this.ensureLoaded().then(() => this.start(name));
    }
  };

  /** Forget cached Howls so a pack/source change is picked up on next play. */
  invalidate = (name?: SoundName): void => {
    const names = name ? [name] : (Object.keys(this.cache) as SoundName[]);
    for (const n of names) {
      try { this.cache[n]?.howl.unload(); } catch { /* ignore */ }
      delete this.cache[n];
    }
  };

  click = (): void => this.play('click');
  tick = (): void => this.play('tick');
  toggle = (): void => this.play('toggle');
  success = (): void => this.play('success');
  error = (): void => this.play('error');
  notification = (): void => this.play('notification');

  /**
   * Explicit event bus hook. A caller that knows the semantic outcome of an
   * async action can dispatch `eclipse:sound` with `{ name }`.
   */
  handleEvent = (event: Event): void => {
    const name = (event as CustomEvent<{ name?: unknown }>).detail?.name;
    if (isSoundName(name)) this.play(name);
  };
}

export const sound = new SoundManager();

/** Convenience helper for dispatching an explicit sound request. */
export function requestSound(name: SoundName): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('eclipse:sound', { detail: { name } }));
}
