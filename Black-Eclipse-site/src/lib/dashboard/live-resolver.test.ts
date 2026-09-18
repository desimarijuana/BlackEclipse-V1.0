import { describe, it, expect } from 'vitest';
import { parseChannelLivePage } from './live-resolver';

// The resolver's HTML parser. This is the piece that decides live vs offline, so
// it is pinned here without any network access.
//
// Real signals on YouTube's channel live page:
//   <link rel="canonical" href="https://www.youtube.com/watch?v=<id>">
//   "isLive":true
//   "playableInEmbed":true|false
//   "liveStreamability":{"liveStreamabilityRenderer":{...}}

const LIVE_EMBEDDABLE = `
<html><head>
<link rel="canonical" href="https://www.youtube.com/watch?v=QB5BNdBFujE">
</head><body>
<script>var ytInitialPlayerResponse = {"isLive":true,"playableInEmbed":true,"liveStreamability":{"liveStreamabilityRenderer":{"videoId":"QB5BNdBFujE"}}};</script>
</body></html>`;

const LIVE_NOT_EMBEDDABLE = `
<html><head>
<link rel="canonical" href="https://www.youtube.com/watch?v=AAAAAAAAAAA">
</head><body>
<script>var ytInitialPlayerResponse = {"isLive":true,"playableInEmbed":false};</script>
</body></html>`;

const OFFLINE = `
<html><head><title>Channel</title></head><body>
<script>var ytInitialData = {"noLive":true};</script>
</body></html>`;

const NOT_LIVE_WITH_VIDEO = `
<html><head>
<link rel="canonical" href="https://www.youtube.com/watch?v=BBBBBBBBBBB">
</head><body>
<script>{"isLive":false,"playableInEmbed":true}</script>
</body></html>`;

describe('parseChannelLivePage', () => {
  it('reports live with the resolved video id when live and embeddable', () => {
    expect(parseChannelLivePage(LIVE_EMBEDDABLE)).toEqual({ videoId: 'QB5BNdBFujE', status: 'live' });
  });

  it('reports offline when the page has no canonical live video', () => {
    const r = parseChannelLivePage(OFFLINE);
    expect(r.status).toBe('offline');
    expect(r.videoId).toBeNull();
  });

  it('reports offline when a canonical video exists but is not live', () => {
    // A channel can have a canonical video (a past/upcoming stream) while not
    // being live right now.
    const r = parseChannelLivePage(NOT_LIVE_WITH_VIDEO);
    expect(r.status).toBe('offline');
  });

  it('reports unavailable when the live broadcast cannot be embedded', () => {
    const r = parseChannelLivePage(LIVE_NOT_EMBEDDABLE);
    expect(r.status).toBe('unavailable');
    expect(r.videoId).toBe('AAAAAAAAAAA');
  });

  it('never claims live on empty or garbage input', () => {
    expect(parseChannelLivePage('').status).toBe('offline');
    expect(parseChannelLivePage('<html>consent wall</html>').status).toBe('offline');
  });
});
