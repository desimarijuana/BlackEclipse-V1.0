---
title: Voice (Read Aloud & Dictation)
status: Current
last-verified: 2026-11-13
---

# Voice — Read Aloud & Dictation

**Who this is for:** anyone changing how Eclipse speaks replies or transcribes
spoken prompts, or asking why it uses browser voices / Whisper.

## What it is

Two related but independent systems:

- **Read aloud (TTS).** An assistant reply can be spoken with the **Speak**
  control in its footer; the same control appears in a structured response's
  header and in bot messages. Settings › **Voice** chooses the system voice,
  rate, pitch and volume, and can opt into speaking every new reply.
- **Voice input (dictation).** The mic in either composer records a prompt,
  transcribes it, and inserts the words at the caret. With no cloud key
  configured, transcription runs **on this machine** (`faster-whisper` in the
  Python runtime) — no account, no key. A configured OpenAI/Groq key takes over
  when present; a local whisper.cpp server remains available as a Custom
  endpoint.

Read-aloud is text-to-speech only. Dictation records **only while the control is
active**, sends the clip to the selected transcription endpoint (or the browser
recognizer), and discards it after the response — no audio and no transcript is
persisted by Eclipse.


## Why browser-native (the decision)

Eclipse uses the **Web Speech API** (`speechSynthesis`) that ships with the
browser/OS.

- **Zero config.** `npm install && npm run dev` needs no key, account or service.
- **Private.** Reply text is passed to the local speech engine; no request is
  made to a server for narration.
- **Free and offline.** System voices keep working without a network.

The trade-off is voice quality/coverage, which varies by OS. A cloud voice
(OpenAI/ElevenLabs) is a later upgrade path, not part of v1. If added, it must be
an `/api/tts` proxy using the existing provider-key vault, must return an honest
`503 UNAVAILABLE` when unconfigured, and must leave the browser path intact as a
fallback. Cloud audio is never labeled Eclipse-verified.

## Where it lives

| Concern | File |
|---|---|
| Preferences (device-local zustand) | `src/lib/tts/store.ts` — key `be_tts_v1` |
| The ONE `speechSynthesis` wrapper (queue, chunking, voice pick, generation guard) | `src/lib/tts/speech.ts` |
| Markdown / structured reply → speakable prose | `src/lib/tts/text.ts` (+ `content.ts` for the on-demand projection) |
| React surface + auto-speak | `src/lib/tts/use-tts.ts` |
| Mounted once at the app root | `src/lib/tts/tts-provider.tsx`, wired in `src/app/layout.tsx` |
| Shared Speak/Stop control | `src/components/chat/tts-button.tsx` |
| Operator settings pane | `src/components/screens/voice-settings.tsx` |

Public imports come from `@/lib/tts` (never from `speechSynthesis` directly in a
component).

## Behaviour worth knowing

- **One reply at a time.** Speaking a second reply cancels the first. Stop is the
  same button.
- **Chunked utterances.** Prose is split into short sentences (~220 chars) because
  Chrome truncates or stalls on long utterances. `splitForSpeech` is pure and
  tested.
- **Stale callbacks are ignored.** Every run carries a generation token; an
  `onend` from a cancelled utterance cannot clear a newer run's UI.
- **Unavailable is honest.** No `speechSynthesis`, or no system voices, hides the
  Speak control and shows an explanation in Settings — never a fake voice or a
  silent button.
- **Structured replies are projected to Markdown first** with the same projector
  Copy and PDF use, so JSON is never read aloud.
- **Auto-speak primes on mount.** Loading a saved conversation does not replay
  history, and enabling auto-speak starts with the *next* completed reply.
- **Auto-speak is off by default.** It is deliberately a separate opt-in from the
  master Speak control.

## Preferences (`be_tts_v1`)

`enabled` (master, default on), `autoSpeak` (default off), `voiceURI`
(`null` = browser-locale default), `rate` (0.5–2), `pitch` (0–2), `volume`
(0–1). Stored in `localStorage`; nothing is synced server-side.

## Voice input (dictation)

The mic in the full composer and in the floating dock starts ONE dictation
session. `describeVoiceEngine` decides what actually runs:

| Preference | Provider ready | Browser recognition | Result |
|---|---|---|---|
| `auto` | yes | anything | **Whisper** |
| `auto` | no | yes | **Browser** |
| `auto` | no | no | unavailable (honest) |
| `whisper` | yes / no | — | Whisper / unavailable |
| `browser` | — | yes / no | Browser / unavailable |

An explicit preference never silently falls back: choosing Whisper without a
provider reports why instead of switching engines behind the operator's back.

### Flow

```
mic → local:    MediaRecorder → base64 → POST /api/voice/transcribe
                 → Next caps/rate → Python /voice/transcribe
                 → on-device faster-whisper (model cached once) → { text }
mic → cloud:    same path, provider endpoint `/audio/transcriptions`
mic → Browser:  SpeechRecognition → final transcript → insert at caret
```

**Local is the default.** `auto` uses a configured cloud key when there is one,
otherwise the on-device engine. The Whisper model (`base.en`, ~75 MB) downloads
once into `.black-eclipse/models/whisper` and then works offline; after that a
short dictation transcribes in about a second on CPU. Nothing is uploaded.

Audio is bounded (≤ 15 MB, ≤ 120 s), MIME-allowlisted, transcribed once and
discarded. Nothing is written to disk, JDDS, artifacts or memory; the transcript
is ordinary composer text, so the operator reviews it before sending.

### Voice field (the composer catches fire)

Tapping the mic in **either composer** morphs that composer into an ember field
(`data-voice="active"` on the form): an advected heat grid, additive embers, a
warm rim, and the transcript typed above the flame. The composer owns the
dictation session (`useVoiceInput` lives in `chat-input.tsx` / `chat-dock.tsx`),
so the field and the control cannot disagree; `VoiceInputButtonView` is the
controlled control, `VoiceInputButton` the self-contained one kept for any host
that does not need the state.

- **Amplitude.** `VoiceMeter` (`src/lib/voice/meter.ts`) attaches an
  AnalyserNode to the **same** stream the recorder owns and returns a smoothed
  loudness + spectral centroid. Loudness drives flame height and spark rate, the
  centroid drives colour temperature. The canvas reads it through a ref, so no
  React render happens per frame.
- **Interaction.** Pointer movement is wind (the flame bends away), a tap throws
  a flare, Esc cancels, Enter stops and transcribes. Stop is always visible.
- **Microphone consent.** WebView2's own consent dialog is drawn in the top-left
  corner of the window and cannot be themed or anchored. The desktop shell
  therefore suppresses it for the media-consent UI
  (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--use-fake-ui-for-media-stream`, set in
  `desktop/src-tauri/src/main.rs`) and the app owns the decision: the first mic
  press opens an **Allow / Not now** card above the button, and the choice is
  remembered in `localStorage` key `be_voice_consent_v1`. Audio handling is
  unchanged — this only moves where the question is asked.
- **Browser engine.** `SpeechRecognition` exposes no stream, so a *visual-only*
  `getUserMedia` feeds the meter and `onInterim` supplies the live words. If the
  extra capture fails, the field keeps its idle smoulder and dictation is
  unaffected. That engine is **never offered inside the desktop shell**:
  WebView2 exposes the constructor but has no speech service behind it, so a
  session starts and then ends after a second. Recognition is also *patient* —
  it restarts itself on an unexpected `onend`, so a breath does not finish the
  dictation; only Stop does.
- **Honest limits.** Desktop (Tauri/WebView2) has no usable `SpeechRecognition`,
  so dictation there needs a transcription provider (OpenAI/Groq key, or the
  Custom preset pointed at a local whisper.cpp server). Without one the mic says
  so instead of pretending to listen. The flame still reacts to the voice, and
  words appear only after transcription — never a fake live transcript.
- **Cost.** 30 fps cap, DPR ≤ 2, particle budget by area, loop paused when the
  tab is hidden, and no `filter: blur()`. The OS "animation effects" setting
  (`prefers-reduced-motion`, which Windows maps from client-area animations)
  drops the field to a calm 8 fps breathing flame instead of freezing a live
  indicator into a still image; the app's own reduce-motion / animations-off
  switch still draws a single static frame.
- **Nothing new is stored.** Audio handling, caps and insertion are unchanged.

Design rationale, phases and the mobile notes:
`docs/voice-fire-field-plan.md`.

### Where it lives

| Concern | File |
|---|---|
| Preferences (`be_voice_input_v1`: engine, language, prompt, max seconds) | `src/lib/voice/store.ts` |
| Engine/provider vocabulary + presets | `src/lib/voice/types.ts` |
| MediaRecorder wrapper (tracks released on stop/cancel) | `src/lib/voice/recorder.ts` |
| SpeechRecognition wrapper + friendly errors | `src/lib/voice/browser-recognition.ts` |
| Front-door client (config + transcribe, no key) | `src/lib/voice/client.ts` |
| State machine (engine choice, caps, permissions, cleanup) | `src/hooks/use-voice-input.ts` |
| Mic control (timer, spinner, error pill) | `src/components/chat/voice-input-button.tsx` (`VoiceInputButtonView` = controlled, `VoiceInputButton` = self-contained) |
| Live level/spectrum meter (AnalyserNode + pure maths) | `src/lib/voice/meter.ts` |
| Fire simulation (heat advection, embers, wind; framework-free) | `src/lib/voice/fire-field.ts` |
| Canvas host + transcript overlay | `src/components/chat/voice-fire-field.tsx` |
| Composer insertion (caret-aware, never replaces typed text) | `src/lib/voice/insert.ts` |
| Server config + key resolution | `src/lib/voice/config-server.ts` |
| Config route (`GET` readiness/stored, `PUT` save) | `src/app/api/voice/config/route.ts` |
| Bounded transcription front door | `src/app/api/voice/transcribe/route.ts` |
| Runtime client | `src/lib/harness/clients/transcribe-client.ts` |
| Python validation + provider call | `python/harness/transcription/service.py` |
| On-device engine (no key, offline after one download) | `python/harness/transcription/local.py` |
| Shared failure classes | `python/harness/transcription/errors.py` |
| Python route (`/voice/transcribe`, operator-gated) | `python/harness/routers/transcription.py` |
| Operator settings card | `src/components/screens/voice-input-settings.tsx` |

### Config and keys

- Provider choice is server-owned in JDDS `SystemConfig` key
  `voice_input_config` (`provider`, optional `baseUrl`, optional `model`).
  `auto` picks the first configured key (OpenAI, then Groq).
- Presets: **On this device** (`base.en`, no key), OpenAI
  (`gpt-4o-mini-transcribe`), Groq (`whisper-large-v3`), and Custom. Custom is
  any OpenAI-compatible endpoint — including a keyless local `whisper.cpp`
  server (`http://127.0.0.1:8080/v1`).
- The on-device engine needs no key at all. `faster-whisper` ships with the
  Python runtime (`python/requirements.txt`), and the model downloads once into
  `.black-eclipse/models/whisper`. PyAV is pinned below 15 because 15+ removed
  the `metadata_errors` keyword faster-whisper passes to `av.open()`.
- Keys come from the shared vault: `OPENAI_API_KEY`, `GROQ_API_KEY`, or the
  optional `TRANSCRIBE_API_KEY` for a custom remote endpoint. The browser only
  learns *whether* one is configured — never its value.
- Caps enforced in `src/app/api/voice/transcribe/route.ts` and again in Python:
  15 MB, 120 s, MIME allowlist, 20 requests/minute/client.
- Provider failure classes are explicit: `NOT_CONFIGURED`, `UNSUPPORTED_MEDIA`,
  `TOO_LARGE`, `KEY_REJECTED`, `RATE_LIMITED`, `TIMEOUT`, `EMPTY_TRANSCRIPT`,
  `PROVIDER_ERROR`, `RUNTIME_UNAVAILABLE`.

### Browser dictation caveat

Chromium-only, and Chrome/Edge may process audio in the vendor's cloud. It also
needs microphone permission for the origin; a denied permission is reported in
the composer, never swallowed. This is why Whisper is preferred whenever a
provider is configured.

## Adding a speak control elsewhere

```tsx
import { TtsButton } from '@/components/chat/tts-button';

<TtsButton content={markdown} speakKey={stableId} />;
// variant="pill" for a labelled control
```

Pass a stable `speakKey` so the Stop state lands on the control that started the
speech. `content` may be plain Markdown or an `eclipse-response` fence.

## Tests

`src/lib/tts/text.test.ts` covers the projection (fences, links, tables,
entities, citations, punctuation) and the chunker (merge, split, hard break,
empty input). The engine itself is browser-only; keep changes to `speech.ts`
conservative and verify them in a real browser.

Voice input has pure tests for caret insertion and engine resolution
(`src/lib/voice/insert.test.ts`, `src/lib/voice/types.test.ts`), a front-door
route test (`src/app/api/voice/transcribe/route.test.ts`), and Python tests for
validation + the provider multipart call
(`python/tests/test_transcription.py`). The recorder and SpeechRecognition
wrappers are browser-only; verify them with a real microphone.
