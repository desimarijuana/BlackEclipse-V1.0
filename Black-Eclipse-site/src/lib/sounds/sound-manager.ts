// ── Sound manager ───────────────────────────────────────────────────────────
// A tiny singleton over the Web Audio API that plays the UI cue set. It is
// intentionally defensive because audio is a non-essential enhancement:
//   * The AudioContext is created once and kept for the life of the page. It is
//     resumed on *every* user gesture (not just the first) and whenever the tab
//     returns to the foreground, which is what fixes the old "sometimes silent"
//     behaviour — a suspended context silently drops `play()`.
//   * `play()` resumes a suspended context itself and waits for the resume
//     before starting the buffer, so an async cue (an alert, a finished chat
//     reply) is not lost even if the context drifted to `suspended`.
//   * Every failure path (unsupported browser, blocked context, decode error)
//     is swallowed — audio never blocks or breaks an interaction.
//   * Per-cue throttling coalesces rapid clicks into a single, clean tick.
//
// Sources resolve per play: a user-uploaded `custom` data URL wins, otherwise
// the active pack's bundled asset. Decoded buffers are cached by source URL and
// re-fetched only when the source changes (pack switch / custom upload).

import {
  SOUND_NAMES,
  SOUND_DEFINITIONS,
  isSoundName,
  packSoundSrc,
  type SoundName,
} from './config';
import { useSoundStore } from './store';

type AudioContextCtor = typeof AudioContext;

function getAudioContextCtor(): AudioContextCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    AudioContext?: AudioContextCtor;
    webkitAudioContext?: AudioContextCtor;
  };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

/** Promise-based `decodeAudioData` that also works on older callback signatures. */
function decode(ctx: AudioContext, bytes: ArrayBuffer): Promise<AudioBuffer> {
  return new Promise<AudioBuffer>((resolve, reject) => {
    let settled = false;
    const done = (buf: AudioBuffer) => { if (!settled) { settled = true; resolve(buf); } };
    const fail = (err: unknown) => { if (!settled) { settled = true; reject(err); } };
    try {
      const maybe = ctx.decodeAudioData(bytes, done, fail);
      if (maybe && typeof maybe.then === 'function') maybe.then(done, fail);
    } catch (err) {
      fail(err);
    }
  });
}

class SoundManager {
  private ctx: AudioContext | null = null;
  private buffers = new Map<string, AudioBuffer>();
  private loading = new Map<string, Promise<AudioBuffer | null>>();
  private armed = false;
  private lastPlayed: Partial<Record<SoundName, number>> = {};

  private resolveSrc(name: SoundName): string {
    const { pack, cues } = useSoundStore.getState().prefs;
    const custom = cues[name]?.custom;
    return custom || packSoundSrc(pack, name);
  }

  /** Create (or return) the one shared AudioContext. Never throws. */
  private getContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    if (this.ctx) return this.ctx;
    const Ctor = getAudioContextCtor();
    if (!Ctor) return null;
    try {
      const ctx = new Ctor();
      // If the context ever suspends (tab hidden, OS audio focus), resume as
      // soon as the page is visible again so cues keep firing.
      ctx.onstatechange = () => {
        if (ctx.state === 'suspended' && typeof document !== 'undefined' && document.visibilityState === 'visible') {
          void ctx.resume().catch(() => { /* ignore */ });
        }
      };
      this.ctx = ctx;
    } catch {
      this.ctx = null;
    }
    return this.ctx;
  }

  /** Whether a specific cue can currently be played (browser + user prefs). */
  private canPlay(name: SoundName): boolean {
    if (typeof window === 'undefined') return false;
    if (!this.armed) return false;
    const prefs = useSoundStore.getState().prefs;
    if (!prefs.enabled) return false;
    const cue = prefs.cues[name];
    if (cue?.muted) return false;
    if (prefs.mode === 'essential' && !SOUND_DEFINITIONS[name].essential) return false;
    return true;
  }

  /** Fetch + decode a source once, deduping concurrent requests. */
  private loadBuffer(ctx: AudioContext, src: string): Promise<AudioBuffer | null> {
    const cached = this.buffers.get(src);
    if (cached) return Promise.resolve(cached);
    const pending = this.loading.get(src);
    if (pending) return pending;

    const promise = (async (): Promise<AudioBuffer | null> => {
      try {
        const res = await fetch(src, { cache: 'force-cache' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const bytes = await res.arrayBuffer();
        const buffer = await decode(ctx, bytes);
        this.buffers.set(src, buffer);
        return buffer;
      } catch {
        return null;
      } finally {
        this.loading.delete(src);
      }
    })();

    this.loading.set(src, promise);
    return promise;
  }

  /** Decode every cue in the active pack so the first click is instant. */
  private warm(): void {
    if (typeof window === 'undefined') return;
    const ctx = this.getContext();
    if (!ctx) return;
    for (const name of SOUND_NAMES) void this.loadBuffer(ctx, this.resolveSrc(name));
  }

  /** Preload the shared context. Safe on mount — needs no gesture. */
  preload = (): void => {
    if (typeof window === 'undefined') return;
    this.getContext();
    this.warm();
  };

  /**
   * Arm playback. Called on every user gesture and on tab visibility — cheap
   * and idempotent, so the context is always running by the time a cue fires.
   */
  unlock = (): void => {
    if (typeof window === 'undefined') return;
    this.armed = true;
    const ctx = this.getContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      try { void ctx.resume().catch(() => { /* ignore */ }); } catch { /* ignore */ }
    }
    this.warm();
  };

  /** Start one buffer through a fresh gain node. Assumes a running context. */
  private start(name: SoundName, buffer: AudioBuffer): void {
    const ctx = this.ctx;
    if (!ctx) return;
    try {
      const prefs = useSoundStore.getState().prefs;
      const gain = prefs.volume * SOUND_DEFINITIONS[name].volume * (prefs.cues[name]?.volume ?? 1);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      const node = ctx.createGain();
      node.gain.value = Math.min(1, Math.max(0, gain));
      source.connect(node).connect(ctx.destination);
      source.start();
    } catch {
      /* playback blocked — ignore */
    }
  }

  /** Resolve the context to `running`, then play the decoded buffer. */
  private async emit(name: SoundName): Promise<void> {
    const ctx = this.getContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      try { await ctx.resume(); } catch { /* ignore */ }
    }
    if (ctx.state !== 'running') return;
    const buffer = await this.loadBuffer(ctx, this.resolveSrc(name));
    if (!buffer) return;
    // Re-check: prefs may have changed during the async decode.
    if (!this.canPlay(name)) return;
    this.start(name, buffer);
  }

  /** Play a cue if enabled and not currently throttled. */
  play = (name: SoundName): void => {
    if (!this.canPlay(name)) return;

    const def = SOUND_DEFINITIONS[name];
    const now = Date.now();
    const last = this.lastPlayed[name] ?? 0;
    if (now - last < def.throttleMs) return;
    this.lastPlayed[name] = now;

    void this.emit(name);
  };

  /** Forget decoded buffers; the next play re-fetches the current sources. */
  invalidate = (_name?: SoundName): void => {
    this.buffers.clear();
    this.warm();
  };

  click = (): void => this.play('click');
  tick = (): void => this.play('tick');
  toggle = (): void => this.play('toggle');
  success = (): void => this.play('success');
  error = (): void => this.play('error');
  notification = (): void => this.play('notification');
  message = (): void => this.play('message');

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
