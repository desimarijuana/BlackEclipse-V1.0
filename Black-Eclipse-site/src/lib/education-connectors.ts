// ── Education-resource connectors (YouTube, GitHub, courses) ─────────────────
// Real, source-specific discovery for learning resources. These are NOT keyword
// hacks over generic web search:
//
//  * YouTube — the official YouTube Data API v3 (search.list + videos.list) when
//    an operator configures YOUTUBE_API_KEY. Without a key the connector reports
//    `not_configured` honestly; it NEVER scrapes or fabricates a video id.
//  * GitHub — the official GitHub REST search API (keyless; an optional
//    GITHUB_TOKEN raises the rate limit).
//  * Courses — a source-restricted search over an explicit allowlist of
//    established course/MOOC providers (Coursera, edX, MIT OCW, Khan Academy …).
//    This is deliberately different from a generic web search: it only ever
//    returns a result from a known course host, and an empty answer is honest.
//
// Every connector returns the SAME normalized shape (`WebSearchResult[]` + a
// `RetrievalDiagnostic`) the rest of the research transport uses, so the Python
// registry can treat them uniformly and fall back without changing.

import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import {
  failedDiagnostic,
  okDiagnostic,
  zeroResultDiagnostic,
  type RetrievalDiagnostic,
} from "@/lib/retrieval-diagnostics";
import type { WebSearchResult } from "@/lib/web-search";
import { searchWeb } from "@/lib/web-research";
import { resolveProviderKey } from "@/lib/provider-keys";

const UA = "BlackEclipse/1.0 (open-source educational research; contact@blackeclipse.local)";
const TIMEOUT_MS = 15_000;
const MAX_BYTES = 8 * 1024 * 1024;

export interface ConnectorOutcome {
  results: WebSearchResult[];
  diagnostic: RetrievalDiagnostic;
}

function base(provider: string): Pick<RetrievalDiagnostic, "capability" | "provider" | "tier"> {
  return { capability: "web_search", provider, tier: "secondary" };
}

async function getJson(
  url: string,
  provider: string,
  headers: Record<string, string> = {}
): Promise<{ ok: true; payload: unknown; latencyMs: number } | { ok: false; diagnostic: RetrievalDiagnostic; latencyMs: number }> {
  const check = validateOutboundUrl(url);
  if (!check.safe) {
    return {
      ok: false,
      latencyMs: 0,
      diagnostic: failedDiagnostic(base(provider), "blocked", `URL rejected: ${check.reason ?? "unsafe"}`, {
        retryable: false,
      }),
    };
  }
  const started = Date.now();
  try {
    const res = await safeGet({
      url,
      timeoutMs: TIMEOUT_MS,
      maxBytes: MAX_BYTES,
      headers: { "user-agent": UA, accept: "application/json", ...headers },
    });
    const latencyMs = Date.now() - started;
    if (res.status < 200 || res.status >= 300) {
      return {
        ok: false,
        latencyMs,
        diagnostic: failedDiagnostic(base(provider), "http_error", `${provider} returned HTTP ${res.status}`, {
          latencyMs,
          httpStatus: res.status,
          bytes: res.bytes,
        }),
      };
    }
    return { ok: true, payload: JSON.parse(res.text), latencyMs };
  } catch (err) {
    const code = err instanceof OutboundError ? err.code : "";
    const timedOut = code === "timeout";
    const latencyMs = Date.now() - started;
    return {
      ok: false,
      latencyMs,
      diagnostic: failedDiagnostic(
        base(provider),
        timedOut ? "timeout" : code === "blocked_host" || code === "blocked_protocol" ? "blocked" : "transport_error",
        timedOut ? `${provider} timed out after ${TIMEOUT_MS} ms` : `${provider} request failed`,
        { latencyMs, timedOut }
      ),
    };
  }
}

function empty(provider: string, detail: string, latencyMs = 0): ConnectorOutcome {
  return { results: [], diagnostic: zeroResultDiagnostic(base(provider), detail, { latencyMs }) };
}

// ── YouTube ──────────────────────────────────────────────────────────────────

/** Parse an ISO-8601 duration (PT1H2M3S) to seconds. Returns null when unknown. */
export function parseIsoDuration(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const m = value.match(/^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!m) return null;
  const [, d, h, min, s] = m;
  const seconds = (Number(d ?? 0) * 86400) + (Number(h ?? 0) * 3600) + (Number(min ?? 0) * 60) + Number(s ?? 0);
  return Number.isFinite(seconds) ? seconds : null;
}

export interface YouTubeVideo extends WebSearchResult {
  videoId: string;
  channel: string | null;
  channelId: string | null;
  thumbnail: string | null;
  durationSeconds: number | null;
  viewCount: number | null;
  language: string | null;
}

export async function youtubeKey(): Promise<string | null> {
  const key = await resolveProviderKey("YOUTUBE_API_KEY");
  return key && key.trim() ? key.trim() : null;
}

type YouTubeKind = "video" | "playlist" | "channel";

export async function youtubeSearch(
  query: string,
  limit: number,
  opts: { kind?: YouTubeKind; language?: string; duration?: string; publishedAfter?: string } = {}
): Promise<{ results: YouTubeVideo[]; diagnostic: RetrievalDiagnostic; provider: string }> {
  const provider = "youtube-data-api";
  const key = await youtubeKey();
  if (!key) {
    return {
      results: [],
      provider,
      diagnostic: failedDiagnostic(
        base(provider),
        "not_configured",
        "YouTube Data API key (YOUTUBE_API_KEY) is not configured",
        { retryable: false }
      ),
    };
  }
  const kind = opts.kind ?? "video";
  const max = Math.min(Math.max(limit, 1), 25);
  const p = new URLSearchParams({
    part: "snippet",
    type: kind,
    maxResults: String(max),
    q: query,
    key,
    safeSearch: "moderate",
  });
  if (opts.language) p.set("relevanceLanguage", opts.language);
  if (kind === "video" && opts.duration) p.set("videoDuration", opts.duration);
  if (opts.publishedAfter) p.set("publishedAfter", opts.publishedAfter);

  const got = await getJson(`https://www.googleapis.com/youtube/v3/search?${p.toString()}`, provider);
  if (!got.ok) return { results: [], provider, diagnostic: got.diagnostic };
  const items = (got.payload as { items?: unknown[] })?.items;
  if (!Array.isArray(items) || items.length === 0) {
    return { results: [], provider, diagnostic: empty(provider, "YouTube returned no matches", got.latencyMs).diagnostic };
  }

  const videos: YouTubeVideo[] = [];
  const videoIds: string[] = [];
  for (const it of items) {
    const r = it as Record<string, unknown>;
    const id = r.id as Record<string, unknown> | undefined;
    const snippet = (r.snippet ?? {}) as Record<string, unknown>;
    const idValue = kind === "video" ? (id?.videoId as string) : kind === "playlist" ? (id?.playlistId as string) : (id?.channelId as string);
    if (!idValue) continue;
    const thumbs = (snippet.thumbnails ?? {}) as Record<string, { url?: string }>;
    const thumb = thumbs.medium?.url ?? thumbs.default?.url ?? thumbs.high?.url ?? null;
    const url =
      kind === "playlist"
        ? `https://www.youtube.com/playlist?list=${idValue}`
        : kind === "channel"
          ? `https://www.youtube.com/channel/${idValue}`
          : `https://www.youtube.com/watch?v=${idValue}`;
    if (kind === "video") videoIds.push(idValue);
    videos.push({
      videoId: idValue,
      title: String(snippet.title ?? "").trim() || "Untitled",
      url,
      snippet: String(snippet.description ?? "").slice(0, 500),
      publishedAt: snippet.publishedAt ? String(snippet.publishedAt) : null,
      channel: snippet.channelTitle ? String(snippet.channelTitle) : null,
      channelId: snippet.channelId ? String(snippet.channelId) : null,
      thumbnail: thumb,
      durationSeconds: null,
      viewCount: null,
      language: null,
    });
  }

  // Enrich durations/statistics in ONE follow-up call (videos.list). This is the
  // only place duration comes from — never inferred from a title.
  if (kind === "video" && videoIds.length > 0) {
    const vp = new URLSearchParams({ part: "contentDetails,statistics", id: videoIds.join(","), key });
    const meta = await getJson(`https://www.googleapis.com/youtube/v3/videos?${vp.toString()}`, provider);
    if (meta.ok) {
      const vids = (meta.payload as { items?: unknown[] })?.items;
      if (Array.isArray(vids)) {
        const byId = new Map(videos.map((v) => [v.videoId, v]));
        for (const v of vids) {
          const r = v as Record<string, unknown>;
          const target = byId.get(String(r.id ?? ""));
          if (!target) continue;
          const cd = (r.contentDetails ?? {}) as Record<string, unknown>;
          const stats = (r.statistics ?? {}) as Record<string, unknown>;
          target.durationSeconds = parseIsoDuration(cd.duration);
          target.viewCount = stats.viewCount != null ? Number(stats.viewCount) : null;
        }
      }
    }
  }

  return {
    results: videos,
    provider,
    diagnostic: okDiagnostic(base(provider), { latencyMs: got.latencyMs, resultCount: videos.length }),
  };
}

export async function youtubeVideoMetadata(videoId: string): Promise<
  | { ok: true; video: YouTubeVideo }
  | { ok: false; status: "UNAVAILABLE"; diagnostic: RetrievalDiagnostic }
> {
  const provider = "youtube-data-api";
  const key = await youtubeKey();
  if (!key) {
    return {
      ok: false,
      status: "UNAVAILABLE",
      diagnostic: failedDiagnostic(base(provider), "not_configured", "YouTube Data API key (YOUTUBE_API_KEY) is not configured", { retryable: false }),
    };
  }
  const p = new URLSearchParams({ part: "snippet,contentDetails,statistics", id: videoId, key });
  const got = await getJson(`https://www.googleapis.com/youtube/v3/videos?${p.toString()}`, provider);
  if (!got.ok) return { ok: false, status: "UNAVAILABLE", diagnostic: got.diagnostic };
  const items = (got.payload as { items?: unknown[] })?.items;
  if (!Array.isArray(items) || items.length === 0) {
    return { ok: false, status: "UNAVAILABLE", diagnostic: empty(provider, `no YouTube video with id ${videoId}`).diagnostic };
  }
  const r = items[0] as Record<string, unknown>;
  const snippet = (r.snippet ?? {}) as Record<string, unknown>;
  const cd = (r.contentDetails ?? {}) as Record<string, unknown>;
  const stats = (r.statistics ?? {}) as Record<string, unknown>;
  const thumbs = (snippet.thumbnails ?? {}) as Record<string, { url?: string }>;
  return {
    ok: true,
    video: {
      videoId,
      title: String(snippet.title ?? "").trim() || "Untitled",
      url: `https://www.youtube.com/watch?v=${videoId}`,
      snippet: String(snippet.description ?? "").slice(0, 500),
      publishedAt: snippet.publishedAt ? String(snippet.publishedAt) : null,
      channel: snippet.channelTitle ? String(snippet.channelTitle) : null,
      channelId: snippet.channelId ? String(snippet.channelId) : null,
      thumbnail: thumbs.medium?.url ?? thumbs.high?.url ?? thumbs.default?.url ?? null,
      durationSeconds: parseIsoDuration(cd.duration),
      viewCount: stats.viewCount != null ? Number(stats.viewCount) : null,
      language: snippet.defaultAudioLanguage ? String(snippet.defaultAudioLanguage) : (snippet.defaultLanguage ? String(snippet.defaultLanguage) : null),
    },
  };
}

/**
 * Fetch a transcript through a PERMITTED, configured method only.
 *
 * YouTube exposes no keyless official transcript endpoint; captions require an
 * authorized (OAuth) method. So this returns UNAVAILABLE unless the operator
 * configures a compliant transcript provider (`YOUTUBE_TRANSCRIPT_API_URL`).
 * It never scrapes timedtext or fabricates a transcript.
 */
export async function youtubeTranscript(videoId: string, language: string): Promise<{
  status: "OK" | "UNAVAILABLE";
  text?: string;
  segments?: Array<{ start: number; duration: number; text: string }>;
  language?: string;
  error?: string;
}> {
  const endpoint = process.env.YOUTUBE_TRANSCRIPT_API_URL?.trim();
  if (!endpoint) {
    return {
      status: "UNAVAILABLE",
      error:
        "Transcripts require an authorized method. Set YOUTUBE_TRANSCRIPT_API_URL to a compliant transcript provider; captions are never scraped or fabricated.",
    };
  }
  const url = `${endpoint}${endpoint.includes("?") ? "&" : "?"}video_id=${encodeURIComponent(videoId)}&lang=${encodeURIComponent(language)}`;
  const got = await getJson(url, "youtube-transcript");
  if (!got.ok) return { status: "UNAVAILABLE", error: got.diagnostic.detail };
  const payload = got.payload as { segments?: unknown[]; text?: unknown; language?: unknown };
  const segments: Array<{ start: number; duration: number; text: string }> = [];
  if (Array.isArray(payload.segments)) {
    for (const s of payload.segments) {
      const r = s as Record<string, unknown>;
      if (typeof r.text !== "string") continue;
      segments.push({ start: Number(r.start ?? 0), duration: Number(r.duration ?? 0), text: r.text });
    }
  }
  const text = typeof payload.text === "string" ? payload.text : segments.map((s) => s.text).join(" ");
  if (!text && segments.length === 0) return { status: "UNAVAILABLE", error: "the transcript provider returned no content" };
  return { status: "OK", text, segments, language: typeof payload.language === "string" ? payload.language : language };
}

// ── GitHub ───────────────────────────────────────────────────────────────────

export async function githubSearch(query: string, limit: number, language?: string): Promise<ConnectorOutcome> {
  const provider = "github-rest";
  const token = await resolveProviderKey("GITHUB_TOKEN");
  const max = Math.min(Math.max(limit, 1), 25);
  let q = query.trim();
  if (language) q += ` language:${language}`;
  const url = `https://api.github.com/search/repositories?q=${encodeURIComponent(q)}&per_page=${max}&sort=stars&order=desc`;
  const headers: Record<string, string> = { accept: "application/vnd.github+json" };
  if (token && token.trim()) headers.authorization = `Bearer ${token.trim()}`;
  const got = await getJson(url, provider, headers);
  if (!got.ok) return { results: [], diagnostic: got.diagnostic };
  const items = (got.payload as { items?: unknown[] })?.items;
  if (!Array.isArray(items) || items.length === 0) return empty(provider, "GitHub returned no repositories", got.latencyMs);
  const results: WebSearchResult[] = [];
  for (const it of items) {
    if (results.length >= limit) break;
    const r = it as Record<string, unknown>;
    const html = String(r.html_url ?? "").trim();
    if (!html) continue;
    const stars = Number(r.stargazers_count ?? 0);
    const lang = r.language ? String(r.language) : "unknown";
    results.push({
      title: String(r.full_name ?? r.name ?? "").trim() || "Untitled repository",
      url: html,
      snippet: `${lang} · ${stars}★ — ${String(r.description ?? "").slice(0, 300)}`,
      publishedAt: r.created_at ? String(r.created_at) : null,
    });
  }
  return { results, diagnostic: okDiagnostic(base(provider), { latencyMs: got.latencyMs, resultCount: results.length }) };
}

// ── Courses (source-restricted) ──────────────────────────────────────────────

export const COURSE_HOSTS = [
  "coursera.org",
  "edx.org",
  "udacity.com",
  "khanacademy.org",
  "ocw.mit.edu",
  "futurelearn.com",
  "pluralsight.com",
  "datacamp.com",
  "codecademy.com",
  "freecodecamp.org",
  "openstax.org",
  "nptel.ac.in",
  "class-central.com",
];

export async function courseSearch(query: string, limit: number): Promise<ConnectorOutcome> {
  const provider = "course-allowlist";
  const hostQuery = COURSE_HOSTS.map((h) => `site:${h}`).join(" OR ");
  const outcome = await searchWeb(`${query} (${hostQuery})`, Math.min(Math.max(limit, 1), 25) * 2);
  // Enforce the allowlist: only return results hosted on a known course provider.
  const allowed = outcome.results.filter((r) => {
    try {
      const host = new URL(r.url).hostname.replace(/^www\./, "");
      return COURSE_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
    } catch {
      return false;
    }
  });
  const results = allowed.slice(0, limit);
  if (results.length === 0) {
    return {
      results: [],
      diagnostic: zeroResultDiagnostic(base(provider), "no course-provider results matched", {
        resultCount: 0,
      }),
    };
  }
  return { results, diagnostic: okDiagnostic(base(provider), { resultCount: results.length }) };
}

export const YOUTUBE_API_ENV = "YOUTUBE_API_KEY";
export const GITHUB_TOKEN_ENV = "GITHUB_TOKEN";
export const TRANSCRIPT_ENV = "YOUTUBE_TRANSCRIPT_API_URL";
