import { beforeEach, describe, expect, it, vi } from 'vitest';

// The front door owns validation, rate limiting and provider resolution; the
// runtime owns the provider call. These tests pin the honest failure classes.

const resolveVoiceProvider = vi.fn();
const transcribeWithRuntime = vi.fn();

vi.mock('@/lib/api-guard', () => ({
  guardMutation: () => null,
  rateLimit: () => ({ ok: true, retryAfterSec: 0 }),
  clientKey: () => 'test-client',
}));

vi.mock('@/lib/voice/config-server', () => ({
  resolveVoiceProvider: (...args: unknown[]) => resolveVoiceProvider(...args),
}));

vi.mock('@/lib/harness/transcribe-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/harness/transcribe-client')>(
    '@/lib/harness/transcribe-client',
  );
  return {
    ...actual,
    transcribeWithRuntime: (...args: unknown[]) => transcribeWithRuntime(...args),
  };
});

import { POST } from '@/app/api/voice/transcribe/route';
import { VoiceRuntimeError } from '@/lib/harness/transcribe-client';

function request(body: Record<string, unknown>) {
  return new Request('http://localhost/api/voice/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

const validBody = {
  audioBase64: 'aGVsbG8=',
  mimeType: 'audio/webm;codecs=opus',
  durationMs: 1500,
  language: 'en',
  prompt: 'AAPL',
};

beforeEach(() => {
  resolveVoiceProvider.mockReset();
  transcribeWithRuntime.mockReset();
  resolveVoiceProvider.mockResolvedValue({
    config: {
      provider: 'openai',
      model: 'gpt-4o-mini-transcribe',
      baseUrl: 'https://api.openai.com/v1',
      ready: true,
      keyConfigured: true,
    },
    keyEnv: 'OPENAI_API_KEY',
    apiKey: 'sk-test',
  });
  transcribeWithRuntime.mockResolvedValue({
    text: '  analyze NVDA earnings  ',
    provider: 'openai',
    model: 'gpt-4o-mini-transcribe',
    language: 'en',
    durationMs: 1500,
  });
});

describe('POST /api/voice/transcribe', () => {
  it('forwards the bounded audio and returns the trimmed transcript', async () => {
    const res = await POST(request(validBody));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.text).toBe('analyze NVDA earnings');
    expect(transcribeWithRuntime).toHaveBeenCalledWith(
      expect.objectContaining({
        mimeType: 'audio/webm',
        language: 'en',
        prompt: 'AAPL',
        apiKey: 'sk-test',
        model: 'gpt-4o-mini-transcribe',
      }),
    );
  });

  it('reports an unconfigured provider honestly instead of calling it', async () => {
    resolveVoiceProvider.mockResolvedValue({
      config: { provider: 'none', model: '', baseUrl: '', ready: false, keyConfigured: false },
      keyEnv: null,
      apiKey: null,
    });

    const res = await POST(request(validBody));
    const body = await res.json();

    expect(res.status).toBe(503);
    expect(body.code).toBe('NOT_CONFIGURED');
    expect(transcribeWithRuntime).not.toHaveBeenCalled();
  });

  it('rejects an unsupported audio type before any provider call', async () => {
    const res = await POST(request({ ...validBody, mimeType: 'application/pdf' }));
    expect(res.status).toBe(415);
    expect(transcribeWithRuntime).not.toHaveBeenCalled();
  });

  it('rejects a missing recording', async () => {
    const res = await POST(request({ ...validBody, audioBase64: '' }));
    expect(res.status).toBe(400);
  });

  it('maps a provider rejection to the runtime error class', async () => {
    transcribeWithRuntime.mockRejectedValue(
      new VoiceRuntimeError('KEY_REJECTED', 'The transcription provider rejected the key.', 502),
    );
    const res = await POST(request(validBody));
    const body = await res.json();
    expect(res.status).toBe(502);
    expect(body.code).toBe('KEY_REJECTED');
  });
});
