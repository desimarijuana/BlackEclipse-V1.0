'use client';

// ── Voice front-door client ────────────────────────────────────────────────
// Talks to the app's own routes only. No provider key or provider URL ever
// reaches the browser; audio leaves the page as a bounded base64 body and the
// clipboard/transcript is never stored anywhere by this module.

import type { VoiceServerConfig } from './types';

export class VoiceError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = 'VoiceError';
    this.code = code;
  }
}

let configPromise: Promise<VoiceServerConfig> | null = null;

/** Cached readiness probe; `refresh` re-reads after settings change. */
export function loadVoiceConfig(refresh = false): Promise<VoiceServerConfig> {
  if (!configPromise || refresh) {
    configPromise = fetch('/api/voice/config', { cache: 'no-store' })
      .then(async (res) => {
        const body = (await res.json().catch(() => ({}))) as { config?: VoiceServerConfig };
        if (!res.ok || !body.config) {
          throw new VoiceError('CONFIG_UNAVAILABLE', 'Voice settings could not be read');
        }
        return body.config;
      })
      .catch(() => {
        configPromise = null;
        throw new VoiceError('CONFIG_UNAVAILABLE', 'Voice settings could not be read');
      });
  }
  return configPromise;
}

export function resetVoiceConfigCache(): void {
  configPromise = null;
}

export interface TranscribeRequest {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  language?: string;
  prompt?: string;
}

export async function blobToBase64(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function transcribeAudio(request: TranscribeRequest): Promise<{ text: string; model: string }> {
  const audioBase64 = await blobToBase64(request.blob);
  const res = await fetch('/api/voice/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      audioBase64,
      mimeType: request.mimeType,
      durationMs: Math.round(request.durationMs),
      language: request.language || undefined,
      prompt: request.prompt || undefined,
    }),
  });
  const body = (await res.json().catch(() => ({}))) as {
    text?: string;
    model?: string;
    error?: string;
    code?: string;
  };
  if (!res.ok || typeof body.text !== 'string') {
    throw new VoiceError(
      body.code || 'TRANSCRIBE_FAILED',
      body.error || 'Transcription failed. Your audio was discarded.',
    );
  }
  return { text: body.text, model: body.model || '' };
}
