---
title: Voice Field — ASCII Wave Dictation Plan
status: Proposed
last-verified: 2026-11-13
---

# Voice Field — ASCII Wave Dictation (plan)

**Who this is for:** whoever builds the "composer turns into a living ASCII
wave while you dictate" feature.

**Goal.** Pressing the mic in either composer should *transform the composer*,
not just start a hidden recording: the input area becomes a dark field of
scrolling ASCII characters that react to the microphone, with the transcript
typing itself out inside the same field. On stop, the field collapses and the
words land at the caret exactly as they do today.

No new persistence, no new provider, no fabricated audio. This is a **visual
layer over the existing dictation pipeline**.

---

## 1. What already exists (do not rebuild)

| Piece | File | Notes |
|---|---|---|
| State machine | `src/hooks/use-voice-input.ts` | `idle → starting → recording → transcribing`; caps, permissions, cleanup |
| Recording | `src/lib/voice/recorder.ts` | `MediaRecorder`; **owns the `MediaStream`** but exposes no meter |
| Browser STT | `src/lib/voice/browser-recognition.ts` | Already has `onInterim` — currently unused by the hook |
| Insertion | `src/lib/voice/insert.ts` | Caret-aware, never replaces typed text |
| Mic control | `src/components/chat/voice-input-button.tsx` | Owns the hook today, so the composer cannot see `state` |
| Composers | `src/components/chat/chat-input.tsx`, `chat-dock.tsx` | Both render `<VoiceInputButton>` |
| Glass surface | `src/app/globals.css` `.glass-composer` | Morph target |

The two structural gaps are: (a) **no amplitude data**, and (b) **the composer
can't observe voice state** because the hook lives inside the button.

## 2. The look (concrete, so there is no ambiguity)

- A mono grid inside the composer: ~80 columns × 5 rows, cell ≈ 8×15 px.
- Character ramp `" .,:;-=+*#%@"` (pure ASCII). Density = amplitude × distance
  from the centre line, so loud speech blooms into `#%@` and silence reads as
  sparse dots.
- Columns scroll right → left like a seismograph. A faint mirrored copy behind
  the main wave and a slow sine ripple keep it alive between words ("soul
  wave"); the ripple is decorative, never a claim of louder audio.
- Everything is tinted from `currentColor` / `var(--primary)`, so dark and light
  themes work without new colours. No full-saturation noise; alpha tiers only.
- The transcript types out beneath the wave in the same mono face: committed
  words at full opacity, the interim tail at ~50% with a blinking caret.
- Toolbar compresses to: **Stop**, elapsed timer, engine chip (`Whisper` /
  `Browser`). Nothing else moves.

### States

| State | Field |
|---|---|
| `idle` | normal composer; wave layer not mounted |
| `starting` | composer morphs (200 ms), wave shows a low idle breathing ripple |
| `recording` | live wave + timer + transcript |
| `transcribing` | wave flattens to a single scanning line, label `Transcribing…` |
| success | 260 ms word-by-word reveal of the final transcript, then collapse + insert |
| error | collapse, existing amber error pill (unchanged) |

## 3. Amplitude (the only genuinely new runtime piece)

New `src/lib/voice/meter.ts`:

```
class VoiceMeter {
  constructor(stream: MediaStream)   // AudioContext + AnalyserNode(fftSize 1024)
  read(): { level: number; peaks: Float32Array | null }
  close(): void                      // stops the graph, never the tracks
}
```

- RMS from `getByteTimeDomainData`, noise-floor subtraction, then a soft
  compression curve, then asymmetric smoothing (fast attack ≈ 0.5, slow release
  ≈ 0.12). Pure functions (`rmsToLevel`, `smoothLevel`) live beside the class
  and are unit-tested with synthetic buffers.
- **Whisper path:** `VoiceRecorder` exposes its stream (a read-only getter, or an
  `onStream` callback) and the hook creates the meter. No change to what is
  recorded or uploaded.
- **Browser path:** `SpeechRecognition` gives no stream. The hook opens a
  *visual-only* `getUserMedia` for the meter and closes it immediately on stop.
  If that second acquisition fails or is blocked, the field falls back to the
  idle ripple and dictation continues untouched — the mic is never required to
  succeed twice.
- AudioContext creation happens inside the click handler (`start()`), so the
  autoplay policy is satisfied.
- Desktop (Tauri / WebView2) has no `SpeechRecognition`, so desktop is
  Whisper-only: amplitude waves plus the post-stop reveal. Live text during
  recording is a browser-only behaviour — state that in the docs rather than
  pretending otherwise.

## 4. Zero-React-per-frame rule

60 fps of `setState` would be the classic mistake here. The canvas loop pulls:

```
voice.meterRef.current?.read()   // returns the latest smoothed level
```

and only discrete facts become React state: `state`, `interim` (throttled to
~6 Hz), `finalPreview`, `elapsedMs` (already 5 Hz). The wave history is a
preallocated ring buffer owned by the renderer, so the draw loop allocates
nothing.

## 5. Files

| File | Change |
|---|---|
| `src/lib/voice/meter.ts` | **new** — analyser + pure level maths |
| `src/lib/voice/wave-field.ts` | **new** — pure ring buffer, ramp mapping, frame build (testable without canvas) |
| `src/components/chat/voice-wave-field.tsx` | **new** — canvas renderer + DOM transcript (`aria-live`) |
| `src/lib/voice/recorder.ts` | expose the stream; close meter on stop/cancel |
| `src/hooks/use-voice-input.ts` | return `meterRef`, `interim`, `finalPreview`, keep `engine`; pass `onInterim` through |
| `src/lib/voice/browser-recognition.ts` | emit a combined final+interim preview (no behaviour change for callers that ignore it) |
| `src/components/chat/voice-input-button.tsx` | accept an optional controlled `voice` prop (self-contained when omitted) |
| `src/components/chat/chat-input.tsx` | hoist the hook, `data-voice` morph, Esc = cancel / Enter = stop+transcribe |
| `src/components/chat/chat-dock.tsx` | same, sharing the field component |
| `src/app/globals.css` | `.glass-composer[data-voice="active"]`, `.voice-field`, reduced-motion rules |
| `src/components/screens/voice-input-settings.tsx` | "Voice wave" toggle (default on) + intensity (calm / normal), persisted in `be_voice_input_v1` |
| `docs/voice.md`, `docs/NAVIGATION.md` | describe the field + the new files |

The textarea stays mounted while hidden (`opacity-0 pointer-events-none`) so the
caret, selection and IME state survive the morph; the field is absolutely
positioned over it, and the form keeps a fixed reserved height so the transcript
above never jumps.

## 6. Motion and accessibility

- `prefers-reduced-motion: reduce` (and the app's existing animations-off
  switch): no rAF loop, one static low-amplitude frame, timer + transcript text
  only. Dictation still works identically.
- Canvas is `aria-hidden`; the real transcript is DOM text with
  `role="status" aria-live="polite"` so screen readers announce words, not
  characters.
- Esc cancels (with the existing right-click behaviour kept), Enter stops and
  transcribes, Stop is always visible and reachable by keyboard.
- Tab is not trapped; leaving the composer does not cancel a dictation.

## 7. Tests

- `src/lib/voice/wave-field.test.ts` — ring buffer wrap/advance, ramp index
  bounds, frame height for a known level, silence = flat, determinism.
- `src/lib/voice/meter.test.ts` — `rmsToLevel` (silence, quiet, loud, clipped),
  smoothing attack vs release, NaN/zero-length buffers.
- `src/lib/voice/types.test.ts` — engine resolution unchanged.
- Manual matrix: permission denied · device unplugged mid-recording · tab
  backgrounded (rAF pause must not corrupt the ring) · 120 s cap · Esc/Stop ·
  reduce-motion · light theme · 360 px width · desktop WebView2 (no live text).

## 8. Phases

1. **P0 — amplitude field (Whisper + browser).** Meter, wave renderer, morph in
   `chat-input`, Whisper-only reveal. This alone delivers the effect on desktop.
2. **P1 — live text.** Interim transcript through the browser engine, the
   typing reveal, and the final+interim preview.
3. **P2 — parity + settings.** `chat-dock` shares the component, the settings
   toggle/intensity, light-theme and mobile polish.
4. **P3 — optional, separate decision.** Streaming partial Whisper (chunked
   uploads) for live text on desktop. Touches the transcribe route, the 20/min
   rate limit and the 120 s cap — do not smuggle it into P0.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Second `getUserMedia` for browser mode fails | Wave degrades to idle ripple; dictation unaffected |
| Canvas churn costs battery on laptops | 30 fps cap, DPR ≤ 2, loop paused on `visibilitychange` and on state change |
| Composer height jump / transcript shift | Fixed reserved height while active; 200 ms eased morph |
| Motion-sensitivity | Reduced-motion static frame, settings intensity |
| Desktop has no browser STT | Documented: desktop gets amplitude + reveal, not live text |
| Feature mistaken for "Eclipse is listening even when idle" | Field only mounts in `starting`/`recording`/`transcribing`; never on `idle` |

## 10. Open questions

- The reference ("mobile lab" animation, "open coach" voice typing) is not in
  this repo. If the intended look differs — e.g. characters falling like rain
  rather than a scrolling seismograph — only `wave-field.ts` + the renderer
  change; the plan's plumbing is unaffected.
- Whether the wave should also react to **TTS output** (agent speaking). Cheap
  to add later (`speech.ts` already owns the audio path) but out of scope here.
