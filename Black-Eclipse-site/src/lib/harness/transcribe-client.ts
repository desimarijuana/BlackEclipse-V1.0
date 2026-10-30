// ── Transcription runtime client ───────────────────────────────────────────
// Thin proxy to the Python runtime's `/voice/transcribe`. It adds no model
// logic: it forwards the bounded audio + resolved provider config and returns
// what the runtime owns. The operator token is presented when one exists.

import { HARNESS_PY_URL, ensurePythonRuntime } from './python-runtime';
import { runtimeCallbackToken } from './runtime-auth';
import { HarnessRuntimeUnavailable } from './python-client';
import { redactSecrets } from './errors';

export class VoiceRuntimeError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'VoiceRuntimeError';
    this.code = code;
    this.status = status;
  }
}

export interface TranscribeRuntimePayload {
  audioBase64: string;
  mimeType: string;
  durationMs?: number;
  language?: string;
  prompt?: string;
  provider: string;
  baseUrl: string;
  apiKey: string | null;
  model: string;
}

export interface TranscribeRuntimeResult {
  text: string;
  provider: string;
  model: string;
  language?: string | null;
  durationMs?: number | null;
}

interface RuntimeDetail {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
}

export async function transcribeWithRuntime(
  payload: TranscribeRuntimePayload,
): Promise<TranscribeRuntimeResult> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      'The Python agent runtime is not available. Install the runtime: npm run setup:python',
    );
  }

  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}/voice/transcribe`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(operatorToken ? { 'X-Harness-Operator': operatorToken } : {}),
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(120_000),
  });

  const body = (await res.json().catch(() => ({}))) as
    | TranscribeRuntimeResult
    | { detail?: RuntimeDetail | string };

  if (!res.ok) {
    const detail = (body as { detail?: RuntimeDetail | string }).detail;
    const code =
      typeof detail === 'object' && detail && typeof detail.code === 'string'
        ? detail.code
        : 'TRANSCRIBE_FAILED';
    const message =
      typeof detail === 'string'
        ? detail
        : typeof detail?.message === 'string'
          ? detail.message
          : `Transcription failed (runtime HTTP ${res.status})`;
    throw new VoiceRuntimeError(code, redactSecrets(message), res.status);
  }

  const result = body as TranscribeRuntimeResult;
  if (typeof result.text !== 'string') {
    throw new VoiceRuntimeError('TRANSCRIBE_FAILED', 'The runtime returned no transcript', 502);
  }
  return result;
}
