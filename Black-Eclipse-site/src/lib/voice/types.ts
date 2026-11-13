// ── Voice input: shared vocabulary ─────────────────────────────────────────
// One OpenAI-compatible /audio/transcriptions shape covers OpenAI, Groq and a
// local whisper.cpp server. Provider presets live here (no secrets) so the
// client settings pane and the server resolver describe the same thing.

export type VoiceEngine = 'auto' | 'whisper' | 'browser';
export type TranscribeProvider = 'auto' | 'openai' | 'groq' | 'custom' | 'local';

export interface VoiceInputPreferences {
  /** `auto` = Whisper when configured, otherwise browser dictation. */
  engine: VoiceEngine;
  /** BCP-47 hint (`en`, `en-US`, …). Empty = auto. */
  language: string;
  /** Vocabulary hint sent to Whisper; ignored by browser recognition. */
  prompt: string;
  /** Hard stop for a single dictation. */
  maxSeconds: number;
}

export interface TranscribePreset {
  label: string;
  baseUrl: string;
  model: string;
  keyEnv: string;
  /** A local endpoint (whisper.cpp / LM Studio) needs no key. */
  keyOptional?: boolean;
}

export const TRANSCRIBE_PRESETS: Record<'openai' | 'groq' | 'custom' | 'local', TranscribePreset> = {
  local: {
    label: 'On this device',
    baseUrl: '',
    model: 'base.en',
    keyEnv: '',
    keyOptional: true,
  },
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini-transcribe',
    keyEnv: 'OPENAI_API_KEY',
  },
  groq: {
    label: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    model: 'whisper-large-v3',
    keyEnv: 'GROQ_API_KEY',
  },
  custom: {
    label: 'Custom (OpenAI-compatible)',
    baseUrl: '',
    model: 'whisper-1',
    keyEnv: 'TRANSCRIBE_API_KEY',
    keyOptional: true,
  },
};

export const DEFAULT_VOICE_PROMPT =
  'Ticker symbols: AAPL, MSFT, NVDA, TSLA, SPY, QQQ. Finance terms: EPS, P/E, VWAP, drawdown, basis points, EBITDA, 10-K, 10-Q, backtest, notional.';

export const DEFAULT_VOICE_INPUT_PREFERENCES: VoiceInputPreferences = {
  engine: 'auto',
  language: '',
  prompt: DEFAULT_VOICE_PROMPT,
  maxSeconds: 60,
};

/** Server-resolved transcription readiness. Never contains a key. */
export interface VoiceServerConfig {
  /** `none` = no usable provider (should not happen: local is always available). */
  provider: 'openai' | 'groq' | 'custom' | 'local' | 'none';
  model: string;
  baseUrl: string;
  /** A key (or a keyless endpoint / the on-device engine) is available. */
  ready: boolean;
  keyConfigured: boolean;
}

export function isVoiceEngine(value: unknown): value is VoiceEngine {
  return value === 'auto' || value === 'whisper' || value === 'browser';
}

export function isTranscribeProvider(value: unknown): value is TranscribeProvider {
  return (
    value === 'auto' ||
    value === 'openai' ||
    value === 'groq' ||
    value === 'custom' ||
    value === 'local'
  );
}

/** Human label for the engine that will actually run. */
export function describeVoiceEngine(
  engine: VoiceEngine,
  serverReady: boolean,
  browserAvailable: boolean,
): 'whisper' | 'browser' | 'none' {
  if (engine === 'whisper') return serverReady ? 'whisper' : 'none';
  if (engine === 'browser') return browserAvailable ? 'browser' : 'none';
  if (serverReady) return 'whisper';
  return browserAvailable ? 'browser' : 'none';
}
