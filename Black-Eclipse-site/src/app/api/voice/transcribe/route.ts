import { NextResponse } from 'next/server';
import { clientKey, guardMutation, rateLimit } from '@/lib/api-guard';
import { HarnessRuntimeUnavailable } from '@/lib/harness/python-client';
import { transcribeWithRuntime, VoiceRuntimeError } from '@/lib/harness/transcribe-client';
import { resolveVoiceProvider } from '@/lib/voice/config-server';

export const dynamic = 'force-dynamic';

// POST /api/voice/transcribe — bounded audio in, transcript out.
//
// The audio is never written to disk or the database. It is validated here,
// forwarded to the Python runtime, and discarded with the request. The provider
// key is resolved server-side and never reaches the browser.

const MAX_AUDIO_BYTES = 15 * 1024 * 1024;
const MAX_DURATION_MS = 120_000;
const ALLOWED_MIME = new Set([
  'audio/webm',
  'audio/ogg',
  'audio/mp4',
  'audio/mpeg',
  'audio/wav',
  'audio/x-wav',
]);

interface Body {
  audioBase64?: unknown;
  mimeType?: unknown;
  durationMs?: unknown;
  language?: unknown;
  prompt?: unknown;
}

function fail(status: number, code: string, error: string) {
  return NextResponse.json({ code, error }, { status });
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, 'voice-transcribe');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit(`voice-transcribe:${clientKey(request)}`, {
    limit: 20,
    windowMs: 60_000,
  });
  if (!limited.ok) {
    return fail(429, 'RATE_LIMITED', `Too many dictations — retry in ${limited.retryAfterSec}s`);
  }

  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return fail(400, 'INVALID_BODY', 'Invalid JSON body');
  }

  const audioBase64 = typeof body.audioBase64 === 'string' ? body.audioBase64 : '';
  if (!audioBase64) return fail(400, 'INVALID_AUDIO', 'No audio was provided');

  // base64 inflates by ~4/3; reject before decoding.
  const estimatedBytes = Math.floor((audioBase64.length * 3) / 4);
  if (estimatedBytes > MAX_AUDIO_BYTES) {
    return fail(413, 'TOO_LARGE', 'That recording is too long. Keep dictation under two minutes.');
  }

  const mimeType = (typeof body.mimeType === 'string' ? body.mimeType : '').split(';')[0].trim().toLowerCase();
  if (!ALLOWED_MIME.has(mimeType)) {
    return fail(415, 'UNSUPPORTED_MEDIA', `Unsupported audio type: ${mimeType || 'unknown'}`);
  }

  const durationMs = typeof body.durationMs === 'number' && Number.isFinite(body.durationMs)
    ? Math.round(body.durationMs)
    : undefined;
  if (durationMs !== undefined && durationMs > MAX_DURATION_MS) {
    return fail(413, 'TOO_LARGE', 'That recording is too long. Keep dictation under two minutes.');
  }

  const language = typeof body.language === 'string' ? body.language.slice(0, 16) : undefined;
  const prompt = typeof body.prompt === 'string' ? body.prompt.slice(0, 900) : undefined;

  let provider: Awaited<ReturnType<typeof resolveVoiceProvider>>;
  try {
    provider = await resolveVoiceProvider();
  } catch (err) {
    console.error('[api/voice/transcribe] config error:', err);
    return fail(500, 'CONFIG_ERROR', 'Could not resolve the transcription provider');
  }

  if (!provider.config.ready) {
    return fail(
      503,
      'NOT_CONFIGURED',
      'Voice transcription is not configured. Add an OpenAI or Groq key in Settings › AI, or use a custom OpenAI-compatible endpoint.',
    );
  }

  try {
    const result = await transcribeWithRuntime({
      audioBase64,
      mimeType,
      durationMs,
      language: language || undefined,
      prompt: prompt || undefined,
      provider: provider.config.provider,
      baseUrl: provider.config.baseUrl,
      apiKey: provider.apiKey,
      model: provider.config.model,
    });
    const text = result.text.trim();
    if (!text) {
      return fail(422, 'EMPTY_TRANSCRIPT', 'No speech was recognized. Try again a little closer to the microphone.');
    }
    return NextResponse.json({
      text,
      provider: result.provider,
      model: result.model,
      language: result.language ?? null,
      durationMs: result.durationMs ?? durationMs ?? null,
    });
  } catch (err) {
    if (err instanceof HarnessRuntimeUnavailable) {
      return fail(503, 'RUNTIME_UNAVAILABLE', 'The Python agent runtime is not available.');
    }
    if (err instanceof VoiceRuntimeError) {
      const status = err.status >= 400 && err.status < 600 ? err.status : 502;
      // 413/415/422 are meaningful to the UI; provider 5xx becomes 502.
      const safeStatus = status === 413 || status === 415 || status === 422 || status === 429 ? status : 502;
      return fail(safeStatus, err.code, err.message);
    }
    console.error('[api/voice/transcribe] error:', err instanceof Error ? err.message : err);
    return fail(502, 'TRANSCRIBE_FAILED', 'Transcription failed. Your audio was discarded.');
  }
}
