---
title: Voice Field — Interactive Fire Dictation Plan
status: Partially shipped
last-verified: 2026-11-13
---

# Voice Field — Interactive Fire (plan)

> **Shipped 2026-11-13 (P0 + P1 on both composers).** `VoiceMeter`, the
> `fire-field` simulation, `VoiceFireField`, the controlled
> `VoiceInputButtonView`, and the `data-voice` morph in `chat-input.tsx` and
> `chat-dock.tsx` are in the tree (browser interim text included). Still open:
> the settings toggle/intensity (P2 polish) and streaming Whisper (P3).
> Current behaviour is documented in `docs/voice.md`.

**Supersedes:** `docs/voice-ascii-wave-plan.md` (ASCII seismograph — not the
intended look).

**Who this is for:** whoever builds "tap the mic, the composer catches fire and
the fire answers your voice".

**Goal.** Tapping the mic transforms the chat composer into a live ember field.
A flame burns along the bottom of the composer, rises when you speak, throws
sparks on loud syllables, goes quiet and smoulders when you pause, and yields to
the cursor like wind. The transcript types itself out above the flame. On stop
the fire banks down, the field collapses, and the words land at the caret exactly
as they do today.

This is a **visual layer over the existing dictation pipeline**. No new provider,
no stored audio, no changes to transcription or insertion.

---

## 1. What already exists (do not rebuild)

| Piece | File | Notes |
|---|---|---|
| State machine | `src/hooks/use-voice-input.ts` | `idle → starting → recording → transcribing`; caps, permissions, cleanup |
| Recording | `src/lib/voice/recorder.ts` | `MediaRecorder`; owns the `MediaStream`, exposes no meter |
| Browser STT | `src/lib/voice/browser-recognition.ts` | Already has `onInterim` — unused by the hook |
| Insertion | `src/lib/voice/insert.ts` | Caret-aware, never replaces typed text |
| Mic control | `src/components/chat/voice-input-button.tsx` | Owns the hook today, so composers cannot see `state` |
| Composers | `src/components/chat/chat-input.tsx`, `chat-dock.tsx` | Both render `<VoiceInputButton>` |
| Glass surface | `src/app/globals.css` `.glass-composer` | Morph target |
| Existing ASCII loaders | `src/components/ui/ascii-loader.tsx` | Not reused; fire is a different language |

Two structural gaps only: **(a) no amplitude data**, and **(b) the composer
cannot observe voice state** because the hook lives inside the button.

## 2. The look

- **Base.** A coal bed along the bottom edge of the composer: a warm radial
  glow (`--primary` pushed toward amber/orange via `hsl` mix, so light theme
  still reads as fire and not mud).
- **Flame body.** A low-resolution heat field (~120 × 40) advected upward with
  1D value noise, tinted through a heat ramp: deep ember → amber → orange →
  near-white core. Drawn on an offscreen canvas, upscaled with smoothing, then
  composited `lighter` onto the field. This is what makes it look like fire
  rather than a bar chart, and it stays cheap.
- **Embers.** 40–140 additive particles with upward drift, curl-noise wander,
  drag and a fading trail. Spawn rate is driven by loudness; a loud syllable
  throws a visible cluster.
- **Glow.** One radial gradient at the base whose radius and alpha follow the
  smoothed level, so silence still has a heartbeat.
- **Text.** The transcript sits above the flame in the existing mono face, warm
  text-shadow: committed words at full opacity, the interim tail at ~55 % with a
  blinking caret.
- **Toolbar.** Compresses to **Stop**, elapsed timer, engine chip
  (`Whisper` / `Browser`). Nothing else moves.

### Interaction (the point of the feature)

| Input | Effect |
|---|---|
| Microphone loudness | flame height, turbulence, ember spawn rate, glow radius |
| Spectral centroid (brightness of speech) | colour temperature — brighter voice burns whiter |
| Pause / silence | flame settles to a low smoulder; a single slow ember drifts up |
| Pointer over the field | local wind: the flame bends away, sparks scatter (mouse *and* touch drag) |
| Tap/click in the field | small flare + ember burst (does not stop dictation) |
| Stop | fire banks down over ~380 ms, embers fall, field collapses |
| Error | flame gutters out to grey smoke, existing amber error pill unchanged |

### States

| State | Field |
|---|---|
| `idle` | normal composer; fire layer not mounted |
| `starting` | ignition from a spark, flame grows ~400 ms |
| `recording` | steady interactive burn |
| `transcribing` | flame shrinks to a coal bed + `Transcribing…` |
| success | one ember burst, 240 ms word-by-word reveal, then collapse + insert |
| error | gutter out, then collapse |

## 3. Amplitude and spectrum (the only new runtime input)

New `src/lib/voice/meter.ts`:

```
class VoiceMeter {
  constructor(stream: MediaStream)      // AudioContext + AnalyserNode(fftSize 1024)
  read(): { level: number; centroid: number }
  close(): void                         // tears down the graph, never the tracks
}
```

- `level`: RMS from `getByteTimeDomainData`, noise-floor subtraction, soft
  compression, asymmetric smoothing (fast attack ≈ 0.5, slow release ≈ 0.12).
- `centroid`: normalised spectral centroid from `getByteFrequencyData` — cheap,
  one pass over 512 bins, heavily smoothed.
- Pure helpers (`rmsToLevel`, `smoothLevel`, `spectralCentroid`) live beside the
  class and are unit-tested with synthetic buffers. No DOM in the maths.

**Whisper path** (the desktop default): `VoiceRecorder` exposes its stream
(read-only getter) and the hook builds the meter. Nothing about the recording
changes.

**Browser path:** `SpeechRecognition` exposes no stream, so the hook opens a
*visual-only* `getUserMedia` for the meter and closes it on stop. If it fails,
the field burns on the idle smoulder and dictation continues untouched — the
microphone is never required to succeed twice.

**Desktop reality:** Tauri/WebView2 has no `SpeechRecognition`, so desktop is
Whisper-only. There the fire reacts to your voice but the transcript arrives
after stop (then animates in). Live text while speaking is a browser behaviour
until chunked Whisper (P3) exists. Say so in the docs; never fake live text.

## 4. Performance contract

- **No React state per frame.** The loop reads `meterRef.current.read()` and the
  pointer ref directly. React state holds only discrete facts: `state`,
  throttled `interim` (~6 Hz), `elapsedMs` (already 5 Hz).
- Preallocated particle pool and heat buffer; the draw loop allocates nothing.
- 30 fps cap (60 on a large viewport), DPR capped at 2, particle budget scaled
  by area: `clamp(40, area / 900, 140)`.
- Loop pauses on `visibilitychange`, on `state !== recording`, and when the
  composer is not mounted. One `requestAnimationFrame` at a time.
- No `filter: blur()` on the canvas; the softness comes from the offscreen
  upscale and additive gradients (GPU-cheap, no repaint storms).
- Canvas is the only added layer; the glass composer keeps its existing
  `backdrop-filter` (no nesting of backdrop roots).

## 5. Files

| File | Change |
|---|---|
| `src/lib/voice/meter.ts` | **new** — analyser, level + centroid, pure maths |
| `src/lib/voice/fire-field.ts` | **new** — pure, framework-free simulation: heat advection, embers, wind, seeded RNG; step + render-data |
| `src/lib/voice/fire-field.test.ts` | **new** — determinism, bounds, decay, no NaN, reduced-motion frame |
| `src/components/chat/voice-fire-field.tsx` | **new** — canvas host, pointer wind, reduced-motion fallback |
| `src/lib/voice/recorder.ts` | expose `stream`; close the meter on stop/cancel |
| `src/hooks/use-voice-input.ts` | return `meterRef`, `interim`; pass `onInterim` through |
| `src/lib/voice/browser-recognition.ts` | emit combined final+interim preview |
| `src/components/chat/voice-input-button.tsx` | accept an optional controlled `voice` prop (self-contained when omitted) |
| `src/components/chat/chat-input.tsx` | hoist the hook, `data-voice` morph, Esc cancel / Enter stop |
| `src/components/chat/chat-dock.tsx` | same, sharing the field component |
| `src/app/globals.css` | `.glass-composer[data-voice="active"]`, `.voice-fire`, reduced-motion rules |
| `src/components/screens/voice-input-settings.tsx` | "Voice fire" toggle (default on) + intensity `calm / normal / wild`, persisted in `be_voice_input_v1` |
| `docs/voice.md`, `docs/NAVIGATION.md` | describe the field and the new files |

The textarea stays mounted while hidden (`opacity-0 pointer-events-none`) so the
caret, selection and IME state survive the morph; the fire layer is absolutely
positioned behind/over it and the form keeps a fixed reserved height so the
transcript above never jumps.

### Mobile

The same component serves the narrow/mobile layout of the app and the planned
standalone mobile app: the simulation module is framework-free, the canvas host
takes `height` and `density` props, touch drag acts as wind, and the particle
budget follows the smaller area. Mobile gets 30 fps and no offscreen upscale
when `navigator.hardwareConcurrency <= 4`.

## 6. Motion and accessibility

- `prefers-reduced-motion: reduce` and the app's animations-off switch: mount a
  **static ember glow** (one frame, no loop, no particles), timer + transcript
  only. Dictation is unaffected.
- Canvas is `aria-hidden`; the real transcript is DOM text with
  `role="status" aria-live="polite"`.
- Esc cancels (right-click kept), Enter stops and transcribes, Stop is always
  visible and keyboard reachable. Tab is never trapped.
- Fire is decorative: no meaning depends on colour or animation.

## 7. Tests

- `src/lib/voice/fire-field.test.ts` — seeded RNG reproduces a frame; ember
  count stays within budget; energy decays when level = 0; heat field stays in
  0..1; pointer wind moves particles away from the cursor; no NaN in any frame;
  reduced-motion frame is identical across steps.
- `src/lib/voice/meter.test.ts` — `rmsToLevel` (silence, quiet, loud, clipped),
  attack vs release, `spectralCentroid` on known tones, zero/NaN buffers.
- Manual: permission denied · device unplugged mid-recording · tab backgrounded
  (loop resumes cleanly) · 120 s cap · Esc/Stop/tap-in-field · reduce-motion ·
  light theme · 360 px width · touch drag · desktop WebView2 (no live text).

## 8. Phases

1. **P0 — fire + morph (Whisper and browser).** Meter, fire simulation, canvas
   host, morph in `chat-input`, stop/ignition, post-stop reveal. Delivers the
   whole effect on desktop.
2. **P1 — interactivity + live text.** Pointer wind, tap flare, interim text
   through the browser engine, word reveal.
3. **P2 — parity + settings.** `chat-dock` shares the component, mobile touch
   tuning, the settings toggle/intensity, light-theme polish.
4. **P3 — optional, separate decision.** Chunked/streaming Whisper for live text
   on desktop. Touches the transcribe route, the 20/min rate limit and the 120 s
   cap — do not smuggle it into P0.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Looks like a screensaver, not fire | One heat field + heat ramp, no per-bar bars; tune against a real flame reference |
| Costs battery | 30 fps, particle budget, pause on hidden/idle, no blur filter |
| Second `getUserMedia` for browser mode fails | Idle smoulder only; dictation unaffected |
| Composer height jump | Fixed reserved height while active, 200 ms eased morph |
| Motion sensitivity | Static ember frame + intensity setting |
| Desktop has no browser STT | Documented; amplitude-reactive fire + post-stop reveal |
| Fire mistaken for "recording" after stop | Field only mounts in `starting`/`recording`/`transcribing`; bank-down is unmistakable |

## 10. Open questions

- "Like OpenCode's animation": the reference is not in this repo and I could not
  identify it with confidence. If it is a *pixel/ASCII* flame rather than a
  smooth particle fire, only `fire-field.ts` + the renderer change — the
  plumbing, states and interactions above stay identical.
- Whether the fire should also react to **agent speech** (TTS). Cheap later —
  `speech.ts` already owns that path — but out of scope here.
