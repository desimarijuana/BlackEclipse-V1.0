import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import {
  readStoredVoiceConfig,
  readVoiceServerConfig,
  saveVoiceConfig,
} from '@/lib/voice/config-server';

export const dynamic = 'force-dynamic';

// GET /api/voice/config — readiness + non-secret provider config.
// PUT /api/voice/config — choose the provider/model (the key stays in the vault).
export async function GET() {
  try {
    const [config, stored] = await Promise.all([
      readVoiceServerConfig(),
      readStoredVoiceConfig(),
    ]);
    return NextResponse.json({ config, stored });
  } catch (err) {
    console.error('[api/voice/config] GET error:', err);
    return NextResponse.json({ error: 'Could not read voice settings' }, { status: 500 });
  }
}

export async function PUT(request: Request) {
  const blocked = guardMutation(request, 'voice-config');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  try {
    return NextResponse.json({ config: await saveVoiceConfig(body) });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Could not save voice settings';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
