// ─── Shared command-handler kit ───────────────────────────────────────────────
// The handler signature, result envelope and the tiny helpers every domain
// module needs. Kept separate from `command-handlers.ts` so a new domain module
// (workspace/markets/dev) can be added without importing the whole dispatch
// table and creating a cycle.

import type { BoundArgs } from "./command-parser";
import type { CommandSpec } from "./command-registry";
import type { ResponseBlock } from "@/lib/response/contract";
import type { CommandUiAction } from "./command-ui";
import type {
  CommandContext,
  CommandDeps,
  CommandResult,
  CommandRunStatus,
  CompactionPayload,
} from "./command-router";

export interface HandlerOutput {
  status: CommandRunStatus;
  blocks?: ResponseBlock[];
  markdownText?: string;
  error?: { code: string; message: string };
  compaction?: CompactionPayload;
  meta?: CommandResult["meta"];
  /** A client-only navigation/Canvas intent; ignored by non-UI surfaces. */
  ui?: CommandUiAction;
}

export type Handler = (
  ctx: CommandContext,
  spec: CommandSpec,
  args: BoundArgs,
  deps: CommandDeps,
) => Promise<HandlerOutput>;

export function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function fail(code: string, message: string): HandlerOutput {
  return { status: "failed", error: { code, message } };
}

export function invalid(code: string, message: string): HandlerOutput {
  return { status: "invalid", error: { code, message } };
}

/** Read the human-readable error out of a front-door JSON error response. */
export function frontDoorError(data: unknown, status: number): string {
  const d = (data ?? {}) as { error?: unknown; detail?: unknown };
  const msg = typeof d.error === "string" ? d.error : typeof d.detail === "string" ? d.detail : undefined;
  return msg ?? `request failed (HTTP ${status})`;
}
