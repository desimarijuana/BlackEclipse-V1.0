---
title: Voice (Read Aloud)
status: Current
last-verified: 2026-10-29
---

# Voice — Read Aloud (TTS)

**Who this is for:** anyone changing how Eclipse speaks replies, or asking why
it uses browser voices instead of a cloud provider.

## What it is

An assistant reply can be spoken with the **Speak** control in its footer. The
same control appears in a structured response's header and in bot messages.
Settings › **Voice** chooses the system voice, rate, pitch and volume, and can
opt into speaking every new reply automatically.

The feature is **text-to-speech only**. It does not listen, record, transcribe or
send audio anywhere.

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
