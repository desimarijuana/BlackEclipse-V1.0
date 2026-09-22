// ─── Harness front door ──────────────────────────────────────────────────────
// The Next.js side resolves what the Python runtime cannot own: the LLM config
// from the settings vault and a run id. Agents and system prompts are
// authoritative in Python, so the front door only sends an agent ID.
//
// There is deliberately NO agent loop, tool registry or model adapter here.

import { getLLMConfig } from "@/lib/settings";
import { assertRunInput } from "./validation";
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
  runId?: string;
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
  runId?: string
): Promise<{ output: string; runId: string; status: "completed" | "failed"; error?: string }> {
  const result = await startRun({
    input: { query, history, documents: documents.length ? documents : undefined },
    agentId: "eclipse-agent",
    runId,
  });

  if ("status" in result && !("modelSteps" in result)) {
    return { output: "", runId: result.runId, status: "completed" };
  }
  const runResult = result as RunResult;
  if (runResult.status === "completed" && runResult.output) {
    return { output: runResult.output, runId: runResult.runId, status: "completed" };
  }
  return {
    output: runResult.output ?? "",
    runId: runResult.runId,
    status: "failed",
    error: runResult.error?.message ?? "The agent run did not complete",
  };
}

/** Resolve the model settings the runtime should use for a run. */
async function resolveModelSettings() {
  const cfg = await getLLMConfig();
  const provider = cfg.provider === "auto" || cfg.provider === "mock" ? "openai" : cfg.provider;
  return {
    provider,
    baseUrl: cfg.baseUrl,
    apiKey: cfg.apiKey,
    model: cfg.model,
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
  runId?: string
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
  const payload: RunRequestPayload = {
    runId: id,
    input,
    agentId: agent.id,
    modelSettings,
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
  const payload: RunRequestPayload = {
    runId,
    input,
    agentId: agent.id,
    modelSettings,
    userId: options.userId,
    callbackBaseUrl: runtimeBaseUrl(),
    callbackToken: runtimeCallbackToken(),
  };

  return runViaRuntime(payload, opts);
}
