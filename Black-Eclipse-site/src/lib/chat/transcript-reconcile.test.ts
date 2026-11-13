import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/harness", () => ({
  listRunsFromRuntime: vi.fn(),
  getRunFromRuntime: vi.fn(),
}));

vi.mock("./session-store", () => ({
  writeTranscript: vi.fn(async () => ({})),
}));

import { listRunsFromRuntime } from "@/lib/harness";
import { writeTranscript } from "./session-store";
import type { RunRecord } from "@/lib/harness/types";
import type { Message } from "@/types/chat";
import {
  indexOfStuckTurn,
  lastUserEpochMs,
  reconcileStuckTranscripts,
  resetReconcileThrottle,
  runAnswersTurn,
  withRunApplied,
} from "./transcript-reconcile";

const NOW = Date.parse("2026-11-12T12:00:00.000Z");

function run(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run_1",
    agentId: "eclipse-agent",
    userId: null,
    sessionId: "chat_1",
    status: "completed",
    input: { query: "q" },
    output: "The answer.",
    error: null,
    modelSteps: 3,
    toolCalls: 2,
    toolErrors: 0,
    promptTokens: 10,
    completionTokens: 5,
    totalTokens: 15,
    provider: "ollama",
    model: "deepseek-v4.1-flash:cloud",
    createdAt: new Date(NOW).toISOString(),
    updatedAt: new Date(NOW).toISOString(),
    startedAt: new Date(NOW).toISOString(),
    finishedAt: new Date(NOW + 30_000).toISOString(),
    ...overrides,
  } as RunRecord;
}

function user(id = String(NOW - 1_000)): Message {
  return { id, role: "user", content: "question" };
}

function placeholder(status: Message["status"] = "queued"): Message {
  return { id: "placeholder", role: "assistant", content: "", status };
}

function transcript(id: string, messages: Message[]) {
  return { id, title: "t", messages, timestamp: NOW, createdAt: NOW, updatedAt: NOW };
}

describe("indexOfStuckTurn", () => {
  it("flags an empty queued/streaming placeholder", () => {
    expect(indexOfStuckTurn([user(), placeholder("queued")])).toBe(1);
    expect(indexOfStuckTurn([user(), placeholder("streaming")])).toBe(1);
    expect(indexOfStuckTurn([user(), { id: "p", role: "assistant", content: "" }])).toBe(1);
  });

  it("never touches a finished, failed, or non-empty turn", () => {
    expect(indexOfStuckTurn([user(), placeholder("completed")])).toBeNull();
    expect(indexOfStuckTurn([user(), placeholder("error")])).toBeNull();
    expect(indexOfStuckTurn([user(), { id: "p", role: "assistant", content: "real" }])).toBeNull();
  });

  it("appends a missing assistant turn when the prompt is last", () => {
    expect(indexOfStuckTurn([user()])).toBe(1);
  });
});

describe("runAnswersTurn", () => {
  it("accepts a completed run that started after the prompt", () => {
    expect(runAnswersTurn(run(), NOW - 5_000)).toBe(true);
  });

  it("refuses a failed run, an empty answer, or an earlier turn's run", () => {
    expect(runAnswersTurn(run({ status: "failed" }), NOW - 5_000)).toBe(false);
    expect(runAnswersTurn(run({ output: "   " }), NOW - 5_000)).toBe(false);
    expect(runAnswersTurn(run({ createdAt: new Date(NOW - 3_600_000).toISOString() }), NOW - 5_000)).toBe(false);
  });
});

describe("withRunApplied", () => {
  it("fills the placeholder in place and clears a stale error", () => {
    const messages = [user(), { ...placeholder(), error: { message: "boom" } }];
    const filled = withRunApplied(messages, 1, run());
    expect(filled).toHaveLength(2);
    expect(filled[1].content).toBe("The answer.");
    expect(filled[1].status).toBe("completed");
    expect(filled[1].runId).toBe("run_1");
    expect(filled[1].error).toBeUndefined();
    expect(filled[1].durationMs).toBe(30_000);
  });

  it("appends when the answer was never even started", () => {
    const filled = withRunApplied([user()], 1, run());
    expect(filled).toHaveLength(2);
    expect(filled[1].role).toBe("assistant");
    expect(filled[1].content).toBe("The answer.");
  });
});

describe("reconcileStuckTranscripts", () => {
  beforeEach(() => {
    resetReconcileThrottle();
    vi.mocked(listRunsFromRuntime).mockReset();
    vi.mocked(writeTranscript).mockClear();
  });

  it("heals a stuck conversation from its completed run and persists it", async () => {
    vi.mocked(listRunsFromRuntime).mockResolvedValue([run()]);
    const conversations = [transcript("chat_1", [user(), placeholder()])];

    const healed = await reconcileStuckTranscripts(conversations);

    expect(healed[0].messages[1].content).toBe("The answer.");
    expect(healed[0].messages[1].status).toBe("completed");
    expect(writeTranscript).toHaveBeenCalledTimes(1);
  });

  it("uses a run stamped on the turn even when the session does not match", async () => {
    vi.mocked(listRunsFromRuntime).mockResolvedValue([]);
    const stamped = { ...placeholder(), runId: "run_stamped" };
    vi.mocked((await import("@/lib/harness")).getRunFromRuntime).mockResolvedValue(
      run({ id: "run_stamped", sessionId: "other" }),
    );

    const healed = await reconcileStuckTranscripts([transcript("chat_1", [user(), stamped])]);
    expect(healed[0].messages[1].content).toBe("The answer.");
  });

  it("leaves a conversation alone when no run proves an answer", async () => {
    vi.mocked(listRunsFromRuntime).mockResolvedValue([run({ status: "failed", output: null })]);
    const conversations = [transcript("chat_1", [user(), placeholder()])];

    const healed = await reconcileStuckTranscripts(conversations);

    expect(healed[0].messages[1].content).toBe("");
    expect(writeTranscript).not.toHaveBeenCalled();
  });

  it("is a no-op when nothing is stuck (no runtime call)", async () => {
    const healed = await reconcileStuckTranscripts([transcript("chat_1", [user(), { id: "a", role: "assistant", content: "done", status: "completed" }])]);
    expect(healed).toHaveLength(1);
    expect(listRunsFromRuntime).not.toHaveBeenCalled();
  });
});
