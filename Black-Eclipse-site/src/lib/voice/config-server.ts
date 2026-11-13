// ── Voice transcription config (server-owned) ──────────────────────────────
// Provider/model choice lives in JDDS SystemConfig; the key never leaves the
// vault. `auto` picks the first provider whose key is actually configured.
//
// This module is server-only: it imports the settings store and key vault.

import { getConfigJSON, setConfigJSON } from '@/lib/settings';
import { resolveProviderKey } from '@/lib/provider-keys';
import {
  TRANSCRIBE_PRESETS,
  isTranscribeProvider,
  type TranscribeProvider,
  type VoiceServerConfig,
} from './types';

export const VOICE_CONFIG_KEY = 'voice_input_config';

export interface StoredVoiceConfig {
  provider: TranscribeProvider;
  baseUrl?: string;
  model?: string;
}

const DEFAULT_STORED: StoredVoiceConfig = { provider: 'auto' };

export async function readStoredVoiceConfig(): Promise<StoredVoiceConfig> {
  try {
    const stored = await getConfigJSON<StoredVoiceConfig>(VOICE_CONFIG_KEY, DEFAULT_STORED);
    return normalizeStored(stored);
  } catch {
    return { ...DEFAULT_STORED };
  }
}

function normalizeStored(value: unknown): StoredVoiceConfig {
  const record = (value ?? {}) as Partial<StoredVoiceConfig>;
  const provider = isTranscribeProvider(record.provider) ? record.provider : 'auto';
  return {
    provider,
    baseUrl: typeof record.baseUrl === 'string' ? record.baseUrl.trim() : undefined,
    model: typeof record.model === 'string' ? record.model.trim() : undefined,
  };
}

/** Providers are tried in this order for `auto`. */
const AUTO_ORDER: Array<'openai' | 'groq'> = ['openai', 'groq'];

export interface ResolvedVoiceProvider {
  config: VoiceServerConfig;
  keyEnv: string | null;
  /** Server-only. Must never be returned to the browser or logged. */
  apiKey: string | null;
}

/**
 * Resolve the effective provider and key. `ready` is honest: a key is present,
 * or a keyless custom endpoint (local whisper.cpp) has a base URL.
 */
export async function resolveVoiceProvider(
  storedInput?: StoredVoiceConfig,
): Promise<ResolvedVoiceProvider> {
  const stored = storedInput ?? (await readStoredVoiceConfig());

  let provider: 'openai' | 'groq' | 'custom' | 'local' | null = null;
  if (stored.provider === 'auto') {
    for (const candidate of AUTO_ORDER) {
      const preset = TRANSCRIBE_PRESETS[candidate];
      if (await resolveProviderKey(preset.keyEnv)) {
        provider = candidate;
        break;
      }
    }
    // No key anywhere: use the engine that ships with the app. This is what
    // makes dictation plug-and-play — nothing to buy, nothing to configure.
    if (!provider) provider = 'local';
  } else {
    provider = stored.provider;
  }

  if (provider === 'local') {
    const preset = TRANSCRIBE_PRESETS.local;
    const sameProvider = stored.provider === 'local';
    return {
      config: {
        provider: 'local',
        baseUrl: '',
        model: (sameProvider ? stored.model : undefined) || preset.model,
        // The engine ships with the Python runtime; a missing install fails at
        // transcription time with an honest LOCAL_ENGINE_MISSING, not a silent
        // "not configured" before the user ever tries.
        ready: true,
        keyConfigured: false,
      },
      keyEnv: null,
      apiKey: null,
    };
  }

  if (!provider) {
    return {
      config: { provider: 'none', model: '', baseUrl: '', ready: false, keyConfigured: false },
      keyEnv: null,
      apiKey: null,
    };
  }

  const preset = TRANSCRIBE_PRESETS[provider];
  const sameProvider = stored.provider === provider;
  const baseUrl = (sameProvider ? stored.baseUrl : undefined) || preset.baseUrl;
  const model = (sameProvider ? stored.model : undefined) || preset.model;
  const apiKey = await resolveProviderKey(preset.keyEnv);
  const keyConfigured = Boolean(apiKey);
  const ready = keyConfigured || (preset.keyOptional === true && Boolean(baseUrl));

  return {
    config: { provider, baseUrl, model, ready, keyConfigured },
    keyEnv: preset.keyEnv,
    apiKey,
  };
}

export async function readVoiceServerConfig(): Promise<VoiceServerConfig> {
  return (await resolveVoiceProvider()).config;
}

function validateBaseUrl(raw: string): string {
  const value = raw.trim().replace(/\/+$/, '');
  if (!value) return '';
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error('Base URL must be a full http(s) URL');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('Base URL must use http or https');
  }
  return value;
}

export async function saveVoiceConfig(input: unknown): Promise<VoiceServerConfig> {
  const record = (input ?? {}) as Partial<StoredVoiceConfig>;
  if (!isTranscribeProvider(record.provider)) {
    throw new Error('Unknown transcription provider');
  }
  if (record.provider === 'custom') {
    const baseUrl = validateBaseUrl(typeof record.baseUrl === 'string' ? record.baseUrl : '');
    if (!baseUrl) throw new Error('A custom provider needs a base URL');
  }
  const next: StoredVoiceConfig = {
    provider: record.provider,
    // A base URL only belongs to a custom endpoint. Keeping a stale one when
    // switching back to OpenAI/Groq would silently send audio to the wrong host.
    baseUrl:
      record.provider === 'custom' &&
      typeof record.baseUrl === 'string' &&
      record.baseUrl.trim()
        ? validateBaseUrl(record.baseUrl)
        : undefined,
    model:
      typeof record.model === 'string' && record.model.trim()
        ? record.model.trim().slice(0, 80)
        : undefined,
  };
  await setConfigJSON(VOICE_CONFIG_KEY, next);
  return (await resolveVoiceProvider(next)).config;
}
