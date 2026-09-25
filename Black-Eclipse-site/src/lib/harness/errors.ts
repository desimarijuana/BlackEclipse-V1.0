// ─── Structured harness errors ───────────────────────────────────────────────
// Every failure in the runtime carries a stable machine-readable `code` so the
// API can map it to an HTTP status and the UI can branch without string
// matching. Messages never include secrets — providers are responsible for
// not leaking keys, and `safeMessage` exists so persistence can redact.

export type HarnessErrorCode =
  | "INVALID_INPUT"
  | "PROVIDER_NOT_CONFIGURED"
  | "PROVIDER_ERROR"
  | "PROVIDER_TIMEOUT"
  | "TOOL_NOT_FOUND"
  | "TOOL_VALIDATION_FAILED"
  | "TOOL_FORBIDDEN"
  | "TOOL_TIMEOUT"
  | "TOOL_ERROR"
  | "MAX_STEPS_EXCEEDED"
  | "TOOL_BUDGET_EXCEEDED"
  | "CANCELLED"
  | "PERSISTENCE_ERROR"
  | "INTERNAL_ERROR";

export interface HarnessErrorJson {
  code: HarnessErrorCode;
  message: string;
  /** Optional, non-sensitive diagnostic detail (already redacted). */
  detail?: string;
}

/** Redact anything that looks like a bearer token / API key from a message. */
export function redactSecrets(text: string): string {
  return text
    .replace(/(Bearer\s+)[A-Za-z0-9._\-]+/gi, "$1[redacted]")
    .replace(/(sk-[A-Za-z0-9._\-]{8,})/g, "[redacted-key]")
    .replace(/("?(?:api[_-]?key|token|secret|authorization)"?\s*[:=]\s*")([^"]+)(")/gi, "$1[redacted]$3");
}

export class HarnessError extends Error {
  readonly code: HarnessErrorCode;
  readonly detail?: string;

  constructor(code: HarnessErrorCode, message: string, detail?: string) {
    super(message);
    this.name = "HarnessError";
    this.code = code;
    this.detail = detail;
  }

  toJSON(): HarnessErrorJson {
    return {
      code: this.code,
      message: redactSecrets(this.message),
      ...(this.detail ? { detail: redactSecrets(this.detail) } : {}),
    };
  }
}

/** Coerce any thrown value into a HarnessError-shaped record for persistence. */
export function toHarnessErrorJson(err: unknown, fallbackCode: HarnessErrorCode = "INTERNAL_ERROR"): HarnessErrorJson {
  if (err instanceof HarnessError) return err.toJSON();
  if (err instanceof Error) {
    if (err.name === "AbortError" || err.name === "TimeoutError") {
      return { code: "PROVIDER_TIMEOUT", message: redactSecrets(err.message || "Request timed out") };
    }
    return { code: fallbackCode, message: redactSecrets(err.message || "Unknown error") };
  }
  return { code: fallbackCode, message: redactSecrets(String(err)) };
}

export function isHarnessError(err: unknown): err is HarnessError {
  return err instanceof HarnessError;
}
