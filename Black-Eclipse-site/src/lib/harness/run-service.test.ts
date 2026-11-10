import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door tests: the Next.js side resolves config + forwards to Python.
// The Python client and settings vault are mocked; there is no agent loop here.

const runViaRuntime = vi.fn();
const listAgentsFromRuntime = vi.fn();
const startRunBackground = vi.fn();
const getLLMConfig = vi.fn();
const resolveChatCodeProfile = vi.fn();

vi.mock("./python-client", () => ({
  runViaRuntime: (...a: unknown[]) => runViaRuntime(...a),
  listAgentsFromRuntime: (...a: unknown[]) => listAgentsFromRuntime(...a),
  startRunBackground: (...a: unknown[]) => startRunBackground(...a),
}));
vi.mock("@/lib/settings", () => ({
  getLLMConfig: (...a: unknown[]) => getLLMConfig(...a),
}));
vi.mock("./chat-capability", () => ({
  resolveChatCodeProfile: (...a: unknown[]) => resolveChatCodeProfile(...a),
}));

import { startRun, startChatRun, chatWithAgent } from "./run-service";
import { __clearAgentPresetCache } from "./agent-presets";
import { HarnessError } from "./errors";

beforeEach(() => {
  runViaRuntime.mockReset();
  startRunBackground.mockReset();
  startRunBackground.mockResolvedValue("run_bg");
  getLLMConfig.mockReset();
  resolveChatCodeProfile.mockReset();
  resolveChatCodeProfile.mockResolvedValue(null);
  __clearAgentPresetCache();
  listAgentsFromRuntime.mockResolvedValue({
    agents: [{ id: "eclipse-agent", name: "Eclipse Agent", systemPrompt: "You are Eclipse Agent." }],
    defaultAgentId: "eclipse-agent",
  });
  getLLMConfig.mockResolvedValue({
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    apiKey: "test-key",
    model: "gpt-4o-mini",
  });
});

describe("startRun", () => {
  it("sends the authoritative agent id, not a prompt copy", async () => {
    runViaRuntime.mockResolvedValue({
      runId: "run_1",
      status: "completed",
      output: "ok",
      modelSteps: 1,
      toolCalls: 0,
      toolErrors: 0,
    });
    const result = await startRun({ input: { query: "price of AAPL", ticker: "AAPL" } });
    expect(result.status).toBe("completed");

    const [payload] = runViaRuntime.mock.calls[0];
    expect(payload.agentId).toBe("eclipse-agent");
    expect(payload.agent).toBeUndefined();
    expect(payload.modelSettings.apiKey).toBe("test-key");
    expect(payload.runId).toMatch(/^run_/);
  });

  it("forwards a per-chat workspace root id (an id, never a path)", async () => {
    runViaRuntime.mockResolvedValue({
      runId: "run_1",
      status: "completed",
      output: "ok",
      modelSteps: 1,
      toolCalls: 0,
      toolErrors: 0,
    });
    await startRun({ input: { query: "fix this project" }, workspaceRootId: "root_abc" });
    const [payload] = runViaRuntime.mock.calls[0];
    expect(payload.workspaceRootId).toBe("root_abc");
    // No caller-supplied path is ever sent; the runtime resolves the id.
    expect(payload.workspace).toBeUndefined();
  });

  it("forwards the session project root id on the streaming chat path", async () => {
    await startChatRun(
      "fix this project", [], [], undefined, "chat_1",
      undefined, undefined, undefined, undefined, undefined, undefined, "root_abc",
    );
    const [payload] = startRunBackground.mock.calls[0];
    expect(payload.workspaceRootId).toBe("root_abc");
    expect(payload.workspace).toBeUndefined();
  });

  it("passes an explicit agent id through", async () => {
    listAgentsFromRuntime.mockResolvedValue({
      agents: [
        { id: "eclipse-agent", name: "Eclipse Agent", systemPrompt: "x" },
        { id: "journal-agent", name: "Journal", systemPrompt: "y" },
      ],
      defaultAgentId: "eclipse-agent",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_x", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "q" }, agentId: "journal-agent" });
    expect(runViaRuntime.mock.calls[0][0].agentId).toBe("journal-agent");
  });

  it("rejects an unknown agent before calling the runtime", async () => {
    await expect(startRun({ input: { query: "q" }, agentId: "nope" })).rejects.toThrow(/Unknown agent/);
    expect(runViaRuntime).not.toHaveBeenCalled();
  });

  it("passes background through", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_bg", status: "running" });
    const result = await startRun({ input: { query: "x" } }, { background: true });
    expect("status" in result && result.status).toBe("running");
    expect(runViaRuntime.mock.calls[0][1]).toEqual({ background: true });
  });

  it("refuses a remote provider with no key", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "",
      model: "gpt-4o-mini",
    });
    await expect(startRun({ input: { query: "x" } })).rejects.toThrow(HarnessError);
  });

  it("allows a keyless local provider", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "ollama",
      baseUrl: "http://localhost:11434/v1",
      apiKey: "",
      model: "llama3.1",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_l", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await expect(startRun({ input: { query: "x" } })).resolves.toBeTruthy();
  });

  it("resolves an auto/mock sentinel to the saved local endpoint instead of openai", async () => {
    // Regression: a configured Ollama endpoint saved with `provider: "mock"`
    // was forwarded as `openai` and the runtime failed with "missing API key".
    getLLMConfig.mockResolvedValue({
      provider: "mock",
      baseUrl: "http://localhost:11434/v1",
      apiKey: "",
      model: "deepseek-v4.1-flash:cloud",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_local", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    const ms = runViaRuntime.mock.calls[0][0].modelSettings;
    expect(ms.provider).toBe("ollama");
    expect(ms.baseUrl).toBe("http://localhost:11434/v1");
  });

  it("rejects invalid input before calling the runtime", async () => {
    await expect(startRun({ input: { query: "  " } })).rejects.toThrow(HarnessError);
    expect(runViaRuntime).not.toHaveBeenCalled();
  });

  it("forwards an operator-declared context window to the runtime", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "ollama",
      baseUrl: "http://localhost:11434/v1",
      apiKey: "",
      model: "llama3.1",
      contextWindow: 8192,
    });
    runViaRuntime.mockResolvedValue({ runId: "run_w", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].modelSettings.contextWindow).toBe(8192);
  });

  it("omits the context window when the operator did not declare one", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_n", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect("contextWindow" in runViaRuntime.mock.calls[0][0].modelSettings).toBe(false);
  });

  it("forwards saved sampling defaults to the runtime", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "test-key",
      model: "gpt-4o-mini",
      temperature: 0.2,
      maxTokens: 2048,
    });
    runViaRuntime.mockResolvedValue({ runId: "run_s", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    const ms = runViaRuntime.mock.calls[0][0].modelSettings;
    expect(ms.temperature).toBe(0.2);
    expect(ms.maxTokens).toBe(2048);
  });

  it("omits sampling defaults on Auto so the payload is unchanged", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_sa", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    const ms = runViaRuntime.mock.calls[0][0].modelSettings;
    expect("temperature" in ms).toBe(false);
    expect("maxTokens" in ms).toBe(false);
  });

  it("forwards a user routing preference as input.context.modelPolicy", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "test-key",
      model: "gpt-4o-mini",
      routingPolicy: { localOnly: true, preferFree: true },
    });
    runViaRuntime.mockResolvedValue({ runId: "run_p", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].input.context.modelPolicy).toEqual({
      local_only: true,
      prefer_free: true,
    });
  });

  it("sends no model policy when the operator set no routing preference", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_np", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].input.context?.modelPolicy).toBeUndefined();
  });

  it("forwards a reasoning-effort override as input.context.reasoning", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "test-key",
      model: "o3-mini",
      reasoningEffort: "very_high",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_re", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].input.context.reasoning).toBe("very_high");
  });

  it("sends no reasoning requirement when the operator left it on Auto", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_ra", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].input.context?.reasoning).toBeUndefined();
  });

  it("lets a per-run effort override outrank the saved default", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "test-key",
      model: "o3-mini",
      reasoningEffort: "low",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_ro", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" }, reasoningEffort: "very_high" });
    expect(runViaRuntime.mock.calls[0][0].input.context.reasoning).toBe("very_high");
  });

  it("falls back to the saved default when the composer sent no override", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "test-key",
      model: "o3-mini",
      reasoningEffort: "high",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_rf", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect(runViaRuntime.mock.calls[0][0].input.context.reasoning).toBe("high");
  });

  it("forwards a per-run effort override through chatWithAgent too", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_c", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("analyze", [], [], undefined, undefined, undefined, "medium");
    expect(runViaRuntime.mock.calls[0][0].input.context.reasoning).toBe("medium");
  });

  it("forwards the composer's quant mode through chatWithAgent", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_qm", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent(
      "forecast gold for tomorrow", [], [], undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, undefined, "on",
    );
    expect(runViaRuntime.mock.calls[0][0].input.context.quantMode).toBe("on");
  });

  it("omits quantMode when the composer is on Auto", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_qa", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("forecast gold for tomorrow");
    expect(runViaRuntime.mock.calls[0][0].input.context?.quantMode).toBeUndefined();
  });

  it("forwards the composer's choices mode through chatWithAgent", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_cm", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent(
      "analyse apple", [], [], undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, undefined, undefined, "on",
    );
    expect(runViaRuntime.mock.calls[0][0].input.context.choicesMode).toBe("on");
  });

  it("omits choicesMode when the composer is on Auto", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_ca", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("analyse apple");
    expect(runViaRuntime.mock.calls[0][0].input.context?.choicesMode).toBeUndefined();
  });

  it("forwards the composer's plan mode through chatWithAgent", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_pm", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent(
      "plan a launch", [], [], undefined, undefined, undefined,
      undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, "on",
    );
    expect(runViaRuntime.mock.calls[0][0].input.context.planMode).toBe("on");
  });

  it("omits planMode when the composer is on Auto", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_pa", status: "completed", output: "ok", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("plan a launch");
    expect(runViaRuntime.mock.calls[0][0].input.context?.planMode).toBeUndefined();
  });

  it("overrides only the model when the composer picked one", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_m", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" }, model: "gpt-4.1" });
    const ms = runViaRuntime.mock.calls[0][0].modelSettings;
    expect(ms.model).toBe("gpt-4.1");
    // Provider + key are the operator's configured ones, unchanged.
    expect(ms.provider).toBe("openai");
    expect(ms.apiKey).toBe("test-key");
  });

  it("drops a declared context window when the model was overridden", async () => {
    getLLMConfig.mockResolvedValue({
      provider: "ollama",
      baseUrl: "http://localhost:11434/v1",
      apiKey: "",
      model: "llama3.1",
      contextWindow: 8192,
    });
    runViaRuntime.mockResolvedValue({ runId: "run_mw", status: "completed", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" }, model: "qwen2.5:14b" });
    const ms = runViaRuntime.mock.calls[0][0].modelSettings;
    expect(ms.model).toBe("qwen2.5:14b");
    // The saved window belongs to (provider, model); an override invalidates it.
    expect("contextWindow" in ms).toBe(false);
  });
});

describe("chatWithAgent code profile (Phase 14)", () => {
  it("sends edit_verify + analysis for a recognised coding turn", async () => {
    resolveChatCodeProfile.mockResolvedValue({
      autonomy: "edit_verify",
      analysisEnabled: true,
      verdict: "code_change",
    });
    runViaRuntime.mockResolvedValue({
      runId: "run_code",
      status: "completed",
      output: "done",
      modelSteps: 3,
      toolCalls: 2,
      toolErrors: 0,
    });
    await chatWithAgent("build me a python module");
    const [payload] = runViaRuntime.mock.calls[0];
    expect(payload.autonomy).toBe("edit_verify");
    expect(payload.analysisEnabled).toBe(true);
  });

  it("keeps the analysis sandbox on for a code question", async () => {
    resolveChatCodeProfile.mockResolvedValue({
      autonomy: "plan_only",
      analysisEnabled: false,
      verdict: "code_question",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_q", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("what does the workspace tool do");
    const [payload] = runViaRuntime.mock.calls[0];
    expect(payload.autonomy).toBe("plan_only");
    expect(payload.analysisEnabled).toBe(true);
  });

  it("enables the analysis sandbox for an ordinary finance turn without a profile", async () => {
    resolveChatCodeProfile.mockResolvedValue(null);
    runViaRuntime.mockResolvedValue({ runId: "run_f", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("what is AAPL trading at");
    const [payload] = runViaRuntime.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.analysisEnabled).toBe(true);
  });

  it("sends analysis without an autonomy for a data task", async () => {
    resolveChatCodeProfile.mockResolvedValue({
      autonomy: null,
      analysisEnabled: true,
      verdict: "data_task",
    });
    runViaRuntime.mockResolvedValue({ runId: "run_data", status: "completed", output: "done", modelSteps: 2, toolCalls: 1, toolErrors: 0 });
    await chatWithAgent("clean this CSV file for me");
    const [payload] = runViaRuntime.mock.calls[0];
    // No profile switch: the finance surface is unchanged, the sandbox is on.
    expect("autonomy" in payload).toBe(false);
    expect(payload.analysisEnabled).toBe(true);
  });

  it("forces the app-control surface for /app without a code profile", async () => {
    await startChatRun("/app add a clock to my Command Center", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.command).toBe("app");
    expect(payload.input.context?.appControl).toBe(true);
    expect(resolveChatCodeProfile).not.toHaveBeenCalled();
  });

  it("marks a classifier app-control turn without narrowing autonomy", async () => {
    resolveChatCodeProfile.mockResolvedValue({
      autonomy: null,
      analysisEnabled: false,
      verdict: "app_control",
    });
    await startChatRun("add a clock to my Command Center", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.input.context?.appControl).toBe(true);
  });

  it("forwards the data-task analysis flag through the streaming path too", async () => {
    resolveChatCodeProfile.mockResolvedValue({
      autonomy: null,
      analysisEnabled: true,
      verdict: "data_task",
    });
    await startChatRun("clean this CSV file for me", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.analysisEnabled).toBe(true);
  });

  it("enables the analysis sandbox on an ordinary streaming turn", async () => {
    resolveChatCodeProfile.mockResolvedValue(null);
    await startChatRun("what is AAPL trading at", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.analysisEnabled).toBe(true);
  });

  it("treats a classifier failure as an ordinary turn", async () => {
    resolveChatCodeProfile.mockRejectedValue(new Error("runtime unavailable"));
    runViaRuntime.mockResolvedValue({ runId: "run_e", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("build me a python module");
    const [payload] = runViaRuntime.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect(payload.analysisEnabled).toBe(true);
  });
});

describe("approval cards", () => {
  it("the streaming chat path asks the runtime to pause for approvals", async () => {
    await startChatRun("run the tests", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect(payload.approvalMode).toBe("ask");
  });

  it("the synchronous chat path does NOT pause (no live card to resolve it)", async () => {
    resolveChatCodeProfile.mockResolvedValue(null);
    runViaRuntime.mockResolvedValue({ runId: "run_sync", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await chatWithAgent("what is AAPL trading at");
    const [payload] = runViaRuntime.mock.calls[0];
    expect("approvalMode" in payload).toBe(false);
  });

  it("startRun only pauses when the caller opts in", async () => {
    runViaRuntime.mockResolvedValue({ runId: "run_r", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" } });
    expect("approvalMode" in runViaRuntime.mock.calls[0][0]).toBe(false);

    runViaRuntime.mockClear();
    runViaRuntime.mockResolvedValue({ runId: "run_r2", status: "completed", output: "x", modelSteps: 1, toolCalls: 0, toolErrors: 0 });
    await startRun({ input: { query: "x" }, approvalMode: "ask" });
    expect(runViaRuntime.mock.calls[0][0].approvalMode).toBe("ask");
  });
});

describe("chat slash command (/eclipsesdk)", () => {
  it("forces the edit_verify profile and strips the command token", async () => {
    // Even with the classifier returning nothing, the command forces the profile.
    resolveChatCodeProfile.mockResolvedValue(null);
    await startChatRun("/eclipsesdk create a page", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect(payload.autonomy).toBe("edit_verify");
    expect(payload.analysisEnabled).toBe(true);
    expect(payload.command).toBe("eclipsesdk");
    expect(payload.input.query).toBe("create a page");
    // The classifier is never consulted for a command turn.
    expect(resolveChatCodeProfile).not.toHaveBeenCalled();
  });

  it("is case-insensitive", async () => {
    await startChatRun("/ECLIPSESDK fix the bug", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect(payload.autonomy).toBe("edit_verify");
    expect(payload.command).toBe("eclipsesdk");
    expect(payload.input.query).toBe("fix the bug");
  });

  it("sends a clarifying default query for a bare command", async () => {
    await startChatRun("/eclipsesdk", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect(payload.command).toBe("eclipsesdk");
    expect(payload.input.query.length).toBeGreaterThan(0);
  });

  it("leaves an unknown /token as ordinary chat", async () => {
    resolveChatCodeProfile.mockResolvedValue(null);
    await startChatRun("/foo do something", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("autonomy" in payload).toBe(false);
    expect("command" in payload).toBe(false);
    expect(payload.input.query).toBe("/foo do something");
    expect(resolveChatCodeProfile).toHaveBeenCalled();
  });

  it("leaves ordinary text unchanged", async () => {
    resolveChatCodeProfile.mockResolvedValue(null);
    await startChatRun("what is AAPL trading at", [], [], undefined, "session-1", undefined);
    const [payload] = startRunBackground.mock.calls[0];
    expect("command" in payload).toBe(false);
    expect(payload.input.query).toBe("what is AAPL trading at");
  });
});
