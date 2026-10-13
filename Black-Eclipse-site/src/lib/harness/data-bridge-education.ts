// ── Education / media discovery capabilities ─────────────────────────────────
// Extracted from `data-bridge.ts` (R3-04 split follow-up) so the dispatcher only
// wires capabilities. Everything here goes through the existing keyless
// connectors and official APIs; nothing opens a new transport.

import { youtubeSearch, youtubeVideoMetadata, youtubeTranscript, githubSearch, courseSearch } from "@/lib/education-connectors";
import { runConnectors, type ConnectorKind } from "@/lib/web-connectors";
import { describeDiagnostics } from "@/lib/harness/web-provider-resolve";
import { unavailableClass } from "@/lib/harness/data-bridge-result";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

/**
 * Video search. Prefers the official YouTube Data API when a key is configured;
 * otherwise falls through to the keyless media connector (Wikimedia Commons).
 * It NEVER fabricates a video id: a keyless answer is a real source page.
 */
export async function videoSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailableClass("invalid_request", "query is required");
  const rawLimit = Number(params.limit ?? 8);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 25) : 8;
  const yt = await youtubeSearch(query, limit, {
    kind: "video",
    language: typeof params.language === "string" ? params.language : undefined,
    duration: typeof params.duration === "string" ? params.duration : undefined,
  });
  if (yt.results.length > 0) {
    return { status: "OK", query, kind: "video", provider: yt.provider, results: yt.results, diagnostics: [yt.diagnostic] };
  }
  // YouTube unconfigured/empty → the keyless connector is the honest fallback.
  return structuredConnectorCapability("video", params);
}

/** Playlist discovery — kept distinct from single videos. */
export async function playlistSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailableClass("invalid_request", "query is required");
  const rawLimit = Number(params.limit ?? 8);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 25) : 8;
  const yt = await youtubeSearch(query, limit, { kind: "playlist" });
  if (yt.results.length === 0) {
    return {
      status: "UNAVAILABLE",
      failureClass: yt.diagnostic.category === "not_configured" ? "not_configured" : "no_data",
      error: yt.diagnostic.detail || "no playlists found",
      diagnostics: [yt.diagnostic],
    };
  }
  return { status: "OK", query, kind: "playlist", provider: yt.provider, results: yt.results, diagnostics: [yt.diagnostic] };
}

/** One video's canonical metadata (duration/statistics from the API only). */
export async function videoMetadataCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const videoId = String(params.videoId ?? params.video_id ?? "").trim();
  if (!videoId) return unavailableClass("invalid_request", "videoId is required");
  const result = await youtubeVideoMetadata(videoId);
  if (!result.ok) {
    return {
      status: "UNAVAILABLE",
      failureClass: result.diagnostic.category === "not_configured" ? "not_configured" : "no_data",
      error: result.diagnostic.detail,
      diagnostics: [result.diagnostic],
    };
  }
  return { status: "OK", video: result.video, diagnostics: [] };
}

/** Transcript through a permitted, configured provider only; never scraped. */
export async function transcriptFetchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const videoId = String(params.videoId ?? params.video_id ?? "").trim();
  if (!videoId) return unavailableClass("invalid_request", "videoId is required");
  const language = String(params.language ?? "en");
  const result = await youtubeTranscript(videoId, language);
  if (result.status !== "OK") {
    return { status: "UNAVAILABLE", failureClass: "not_configured", error: result.error ?? "transcript unavailable" };
  }
  return { status: "OK", language: result.language, text: result.text, segments: result.segments };
}

/** Course discovery restricted to an explicit allowlist of course providers. */
export async function courseSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailableClass("invalid_request", "query is required");
  const rawLimit = Number(params.limit ?? 8);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 25) : 8;
  const outcome = await courseSearch(query, limit);
  if (outcome.results.length === 0) {
    return {
      status: "UNAVAILABLE",
      failureClass: outcome.diagnostic.normalizedStatus === "failed" ? "source_failure" : "no_data",
      error: outcome.diagnostic.detail || "no course-provider results matched",
      diagnostics: [outcome.diagnostic],
    };
  }
  return { status: "OK", query, provider: outcome.diagnostic.provider, results: outcome.results, diagnostics: [outcome.diagnostic] };
}

/** Repository discovery via the official GitHub REST search API. */
export async function githubSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailableClass("invalid_request", "query is required");
  const rawLimit = Number(params.limit ?? 8);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 25) : 8;
  const language = typeof params.language === "string" ? params.language : undefined;
  const outcome = await githubSearch(query, limit, language);
  if (outcome.results.length === 0) {
    return {
      status: "UNAVAILABLE",
      failureClass: outcome.diagnostic.normalizedStatus === "failed" ? "source_failure" : "no_data",
      error: outcome.diagnostic.detail || "GitHub returned no repositories",
      diagnostics: [outcome.diagnostic],
    };
  }
  return { status: "OK", query, provider: outcome.diagnostic.provider, results: outcome.results, diagnostics: [outcome.diagnostic] };
}

/**
 * A structured connector capability (academic/news/image/video). Runs the
 * keyless connector chain for the kind (OpenAlex/Crossref, GDELT, Openverse/
 * Commons) and reports honestly: a genuine empty answer is `no_data`, a
 * connector failure is `source_failure` with per-connector diagnostics. The
 * Python registry falls back to web search when this reports UNAVAILABLE.
 */
export async function structuredConnectorCapability(
  kind: ConnectorKind,
  params: Record<string, unknown>
): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) return unavailableClass("invalid_request", "query is required");
  const rawLimit = Number(params.limit ?? 8);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 25) : 8;
  const outcome = await runConnectors(kind, query, limit);
  if (outcome.results.length === 0) {
    const allFailed = outcome.diagnostics.every((d) => d.normalizedStatus === "failed");
    return {
      status: "UNAVAILABLE",
      failureClass: allFailed ? "source_failure" : "no_data",
      error: allFailed
        ? `${kind} connectors failed: ${describeDiagnostics(outcome.diagnostics)}`
        : `the ${kind} connectors returned no results`,
      diagnostics: outcome.diagnostics,
    };
  }
  return {
    status: "OK",
    query,
    kind,
    provider: outcome.provider,
    results: outcome.results,
    diagnostics: outcome.diagnostics,
  };
}
