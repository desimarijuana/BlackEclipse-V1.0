// ── Client response telemetry seam ────────────────────────────────────────────
// A tiny, installable reporter for the client-side signals the server cannot see:
// time-to-first-block (how fast a structured answer starts appearing), local
// interactions (input/slider changes — which must cost 0 model calls), and
// partial-parse failures. Pure and framework-free; a no-op unless a reporter is
// installed, so it never affects rendering.

export type TelemetryEvent = 'first_block' | 'interaction' | 'partial_parse_failure';

export interface ResponseTelemetryRecord {
  event: TelemetryEvent;
  /** Milliseconds from turn start to the first rendered block (event `first_block`). */
  timeToFirstBlockMs?: number;
  /** Which block drove the interaction (event `interaction`). */
  blockType?: string;
  /** A short reason (event `partial_parse_failure`). */
  reason?: string;
}

type Reporter = (record: ResponseTelemetryRecord) => void;

let reporter: Reporter | null = null;

/** Install a reporter for client response telemetry. Returns an uninstall handle. */
export function setResponseTelemetryReporter(next: Reporter | null): () => void {
  reporter = next;
  return () => {
    if (reporter === next) reporter = null;
  };
}

/** Report one client telemetry record (no-op unless a reporter is installed). */
export function reportResponseTelemetry(record: ResponseTelemetryRecord): void {
  if (process.env.NODE_ENV !== 'production') {
    // eslint-disable-next-line no-console
    console.debug('[eclipse-response] telemetry', record);
  }
  reporter?.(record);
}
