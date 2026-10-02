// ─── Harness front door ──────────────────────────────────────────────────────
// The Next.js side resolves what the Python runtime cannot own: the LLM config
// from the settings vault and a run id. Agents and system prompts are
// authoritative in Python, so the front door only sends an agent ID.
//
// There is deliberately NO agent loop, tool registry or model adapter here.

import { getLLMConfig } from "@/lib/settings";
import { assertChatAutonomy, assertRunInput, validateWorkspaceRef } from "./validation";
import { resolveChatCodeProfile } from "./chat-capability";
import { getAgentPreset } from "./agent-presets";
import { runViaRuntime, startRunBackground, type RunRequestPayload } from "./python-client";
import { runtimeBaseUrl, runtimeCallbackToken } from "./runtime-auth";
import type { RunInput, RunResult } from "./types";
import { newRunId } from "./ids";
import { HarnessError } from "./errors";

export interface StartRunOptions {
  input: RunInput;
  agentId?: string;
  userId?: string;
  // M3/M4 request-scoped isolation identity (optional; the runtime defaults them).
  sessionId?: string;
  profileId?: string;
  projectId?: string;
  runId?: string;
  // Phase 1 (optional): bind this run to a read-only workspace. Validated here
  // and forwarded; the runtime only ever binds its server-resolved root.
  workspace?: { root: string; baseRevision?: string };
}

/**
 * Conversational entry point for the chat surfaces. Runs the Eclipse Agent
 * through the harness with prior turns as context, so a follow-up keeps the
 * thread. Returns the agent's final text.
 */
export async function chatWithAgent(
  query: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
  documents: Array<{ name: string; text: string }> = [],
  runId?: string,
  sessionId?: string,
): Promise<{
  output: string;
  runId: string;
  status: "completed" | "failed";
  error?: string;
  research?: import("./types").ResearchRunInfo;
}> {
  const result = await startRun({
    input: { query, history, documents: documents.length ? documents : undefined },
    agentId: "eclipse-agent",
    runId,
    // The chat workspace id is the session id, so a chat turn belongs to a
    // long-lived session and shows up in the Sessions tab (M3).
    sessionId,
  });

  if ("status" in result && !("modelSteps" in result)) {
    return { output: "", runId: result.runId, status: "completed" };
  }
  const runResult = result as RunResult;
  if (runResult.status === "completed" && runResult.output) {
    return {
      output: runResult.output,
      runId: runResult.runId,
      status: "completed",
      research: runResult.research,
    };
  }
  return {
    output: runResult.output ?? "",
    runId: runResult.runId,
    status: "failed",
    error: runResult.error?.message ?? "The agent run did not complete",
    research: runResult.research,
  };
}

/**
 * Resolve the model settings the runtime should use for a run.
 *
 * Exported (Phase 14) so the code-task route can resolve them server-side when a
 * task is started from a UI surface that has no vault access. There is still one
 * resolution path — this function.
 */
export async function resolveRunModelSettings() {
  return resolveModelSettings();
}

async function resolveModelSettings() {
  const cfg = await getLLMConfig();
  const provider = cfg.provider === "auto" || cfg.provider === "mock" ? "openai" : cfg.provider;
  return {
    provider,
    baseUrl: cfg.baseUrl,
    apiKey: cfg.apiKey,
    model: cfg.model,
    // Pass the operator-declared window through only when set; the runtime treats
    // absent as "unknown" and falls back to its catalog + conservative ceiling.
    ...(cfg.contextWindow ? { contextWindow: cfg.contextWindow } : {}),
  };
}

/**
 * Start a conversational run in the background and return its run id.
 *
 * The caller streams `/api/harness/runs/<id>/stream` for live status + tokens,
 * then reads the finished run for the final answer. This is what lets the chat
 * show the agent working instead of a blank spinner.
 */
export async function startChatRun(
  query: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
  documents: Array<{ name: string; text: string }> = [],
  runId?: string,
  sessionId?: string,
): Promise<string> {
  const input = assertRunInput({
    query,
    history,
    documents: documents.length ? documents : undefined,
  });
  const agent = await getAgentPreset("eclipse-agent");
  const modelSettings = await resolveModelSettings();
  if (!modelSettings.apiKey && !/localhost|127\.0\.0\.1/.test(modelSettings.baseUrl)) {
    throw new HarnessError(
      "PROVIDER_NOT_CONFIGURED",
      "No LLM provider is configured. Add a key in Settings → AI."
    );
  }
  const id = runId ?? newRunId();
  // Phase 14: ask the runtime's deterministic classifier whether this turn is a
  // coding request. A failure to classify is an ordinary turn (null), never a
  // guess — an unavailable classifier must not hand out a code profile.
  let capability: Awaited<ReturnType<typeof resolveChatCodeProfile>> = null;
  try {
    capability = await resolveChatCodeProfile(query, history);
  } catch {
    capability = null;
  }
  const autonomy = capability ? assertChatAutonomy(capability.autonomy) : undefined;
  const payload: RunRequestPayload = {
    runId: id,
    input,
    agentId: agent.id,
    modelSettings,
    sessionId,
    ...(autonomy ? { autonomy } : {}),
    ...(capability?.analysisEnabled ? { analysisEnabled: true } : {}),
    callbackBaseUrl: runtimeBaseUrl(),
    callbackToken: runtimeCallbackToken(),
  };
  await startRunBackground(payload);
  return id;
}

export async function startRun(
  options: StartRunOptions,
  opts: { background?: boolean } = {}
): Promise<RunResult | { runId: string; status: string }> {
  const input = assertRunInput(options.input);
  // Validate the agent id against the runtime's authoritative presets (this
  // also warms the cache) without sending a prompt copy.
  const agent = await getAgentPreset(options.agentId);
  const modelSettings = await resolveModelSettings();

  if (!modelSettings.apiKey && !/localhost|127\.0\.0\.1/.test(modelSettings.baseUrl)) {
    throw new HarnessError(
      "PROVIDER_NOT_CONFIGURED",
      "No LLM provider is configured. Add a key in Settings → AI."
    );
  }

  const runId = options.runId ?? newRunId();
  let workspace: { root: string; baseRevision?: string } | undefined;
  if (options.workspace !== undefined) {
    const validated = validateWorkspaceRef(options.workspace);
    if (!validated.ok || !validated.value) {
      throw new HarnessError("INVALID_INPUT", "Invalid workspace reference", validated.issues.join("; "));
    }
    workspace = validated.value;
  }
  const payload: RunRequestPayload = {
    runId,
    input,
    agentId: agent.id,
    modelSettings,
    userId: options.userId,
    // Request-scoped isolation identity (M3/M4). Absent = default profile and a
    // runtime-derived session; the runtime resolves and enforces the scope.
    sessionId: options.sessionId,
    profileId: options.profileId,
    projectId: options.projectId,
    // Phase 1 (optional): a narrowing/confirmation of the workspace root.
    workspace,
    callbackBaseUrl: runtimeBaseUrl(),
    callbackToken: runtimeCallbackToken(),
  };

  return runViaRuntime(payload, opts);
}
