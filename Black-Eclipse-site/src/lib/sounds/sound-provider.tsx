'use client';

// ── Sound provider ──────────────────────────────────────────────────────────
// Mounted once at the app root. Its only jobs are to:
//   1. Hydrate the persisted sound preferences after mount.
//   2. Unlock the audio context on the first real user gesture (pointer/key),
//      satisfying browser autoplay restrictions.
//   3. Delegate a *narrow* set of semantic clicks to the right cue via a
//      single capturing listener, so individual components stay untouched.
//
// Deliberately excluded: hover, typing, drag, scroll, chart movement and any
// other high-frequency event — sounds must feel like a terminal, not a game.

import { useEffect } from 'react';
import { sound } from './sound-manager';
import { useSoundStore } from './store';

/** Elements that should stay silent. */
const SILENT_SELECTOR = '[data-sound="off"], [aria-hidden="true"]';

function isDisabled(el: Element): boolean {
  if (el instanceof HTMLButtonElement && el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  return false;
}

export function SoundProvider() {
  const hydrate = useSoundStore((s) => s.hydrate);

  // Hydrate persisted preferences (no-op on first render to keep SSR stable)
  // and preload/decode the cue set. Preloading on mount is important: Howler
  // registers its context-unlock listeners during module init, so it must be
  // present before the first gesture for the AudioContext to actually resume.
  useEffect(() => {
    hydrate();
    sound.preload();
  }, [hydrate]);

  // Arm playback on the first pointer or key interaction.
  useEffect(() => {
    const unlock = () => sound.unlock();
    window.addEventListener('pointerdown', unlock, { once: true, capture: true });
    window.addEventListener('keydown', unlock, { once: true, capture: true });
    return () => {
      window.removeEventListener('pointerdown', unlock, { capture: true });
      window.removeEventListener('keydown', unlock, { capture: true });
    };
  }, []);

  // Explicit semantic cues from anywhere in the app (e.g. async completion).
  useEffect(() => {
    window.addEventListener('eclipse:sound', sound.handleEvent);
    return () => window.removeEventListener('eclipse:sound', sound.handleEvent);
  }, []);

  // Single delegated click listener: classify the clicked control and play the
  // matching cue. Capture phase so it works even if a handler stops propagation.
  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      const target = e.target as Element | null;
      if (!target || typeof target.closest !== 'function') return;

      // Explicit per-element override wins (also allows silencing).
      const explicit = target.closest('[data-sound]') as HTMLElement | null;
      if (explicit) {
        const value = explicit.getAttribute('data-sound');
        if (value === 'off') return;
        if (isDisabled(explicit)) return;
        if (value === 'click' || value === 'tick' || value === 'toggle' || value === 'success' || value === 'error' || value === 'notification') {
          sound.play(value);
          return;
        }
      }

      if (target.closest(SILENT_SELECTOR)) return;

      const switchEl = target.closest('[role="switch"], input[type="checkbox"], input[type="radio"]');
      if (switchEl) {
        if (!isDisabled(switchEl)) sound.toggle();
        return;
      }

      const actionable = target.closest(
        'button, a[href], [role="menuitem"], [role="option"], [role="tab"], [role="combobox"], [role="checkbox"], [role="radio"]',
      );
      if (actionable && !isDisabled(actionable)) sound.click();
    };

    window.addEventListener('pointerdown', onPointerDown, { capture: true });

    // Keyboard activation of a focused control mirrors the pointer cues.
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const target = e.target as Element | null;
      if (!target || typeof target.closest !== 'function') return;
      if (target.closest(SILENT_SELECTOR)) return;
      const explicit = target.closest('[data-sound]') as HTMLElement | null;
      if (explicit?.getAttribute('data-sound') === 'off') return;
      const control = target.closest('[role="switch"], button, a[href], [role="menuitem"], [role="option"], [role="tab"]');
      if (!control || isDisabled(control)) return;
      if (control.getAttribute('role') === 'switch' || control instanceof HTMLInputElement) sound.toggle();
      else sound.click();
    };

    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => {
      window.removeEventListener('pointerdown', onPointerDown, { capture: true });
      window.removeEventListener('keydown', onKeyDown, { capture: true });
    };
  }, []);

  return null;
}
