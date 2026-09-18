import { NextResponse } from 'next/server';
import { LIVE_CHANNELS, LIVE_CATEGORIES } from '@/lib/dashboard/live-channels';
import { resolveLiveStreams } from '@/lib/dashboard/live-resolver';

export const dynamic = 'force-dynamic';

// ── Live Intelligence — stream status ────────────────────────────────────────
// Resolves the CURRENT live video id + status for the requested channels,
// server-side and cached (3 min). The client embeds `/embed/<resolved id>`
// instead of the unreliable `live_stream?channel=` endpoint.
//
// GET /api/live-streams                 → every built-in channel
// GET /api/live-streams?ids=a,b,c       → just those ids
//
// This reads a public page's metadata only. It does NOT fetch, proxy, relay or
// rebroadcast any media, and it never fabricates a "live" status.

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const requested = searchParams.get('ids');
  const ids = requested
    ? requested.split(',').map(s => s.trim()).filter(Boolean)
    : LIVE_CHANNELS.map(c => c.id);

  const byId = new Map(LIVE_CHANNELS.map(c => [c.id, c]));
  const targets = ids
    .map(id => byId.get(id))
    .filter((c): c is NonNullable<typeof c> => Boolean(c && (c.youtubeHandle || c.youtubeChannelId)))
    .map(c => ({ key: c.id, handle: c.youtubeHandle, channelId: c.youtubeChannelId }));

  if (targets.length === 0) {
    return NextResponse.json({ streams: {}, checkedAt: new Date().toISOString() });
  }

  const streams = await resolveLiveStreams(targets);

  return NextResponse.json({
    streams,
    checkedAt: new Date().toISOString(),
    categories: LIVE_CATEGORIES,
  });
}
