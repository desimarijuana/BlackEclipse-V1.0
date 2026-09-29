import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door tests: the Next.js side resolves config + forwards to Python.
// The Python client and settings vault are mocked; there is no agent loop here.

const runViaRuntime = vi.fn();
const listAgentsFromRuntime = vi.fn();
const getLLMConfig = vi.fn();

vi.mock("./python-client", () => ({
  runViaRuntime: (...a: unknown[]) => runViaRuntime(...a),
  listAgentsFromRuntime: (...a: unknown[]) => listAgentsFromRuntime(...a),
}));
vi.mock("@/lib/settings", () => ({
  getLLMConfig: (...a: unknown[]) => getLLMConfig(...a),
}));

import { startRun } from "./run-service";
import { __clearAgentPresetCache } from "./agent-presets";
import { HarnessError } from "./errors";

beforeEach(() => {
  runViaRuntime.mockReset();
  getLLMConfig.mockReset();
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
});
