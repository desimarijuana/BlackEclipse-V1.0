import { describe, it, expect } from "vitest";
import type { RunResult, RunRecord, ContextBudgetInfo } from "./types";

// Backward-compatibility guard for the additive context-budget contract.
// A run persisted BEFORE this change has no `context` field; a run that did not
// trim has none either. The TS type must accept both, and an old client that
// never reads `context` must keep compiling.

function legacyRun(): RunResult {
  // Exactly the shape written by an older runtime: no `context` key.
  return {
    runId: "run_legacy",
    status: "completed",
    output: "answer",
    modelSteps: 1,
    toolCalls: 0,
    toolErrors: 0,
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
  };
}

describe("RunResult context contract (additive)", () => {
  it("accepts a legacy run row with no context metadata", () => {
    const run = legacyRun();
    expect(run.context).toBeUndefined();
    // A consumer that ignores the field still compiles and reads the run.
    expect(run.status).toBe("completed");
  });

  it("accepts a run that carried the new context metadata", () => {
    const ctx: ContextBudgetInfo = {
      window: 32000,
      windowKnown: true,
      keptTurns: 20,
      droppedTurns: 10,
      droppedTokensEstimate: 5000,
      tighterRetry: false,
    };
    const run: RunResult = { ...legacyRun(), context: ctx };
    expect(run.context?.droppedTurns).toBe(10);
    expect(run.context?.windowKnown).toBe(true);
  });

  it("accepts an unknown-window context blob", () => {
    const ctx: ContextBudgetInfo = {
      window: null,
      windowKnown: false,
      keptTurns: 20,
      droppedTurns: 10,
      droppedTokensEstimate: 5000,
      tighterRetry: false,
    };
    const run: RunResult = { ...legacyRun(), context: ctx };
    expect(run.context?.window).toBeNull();
    expect(run.context?.windowKnown).toBe(false);
  });

  it("accepts a legacy RunRecord row (no context)", () => {
    const record: RunRecord = {
      id: "r",
      agentId: "eclipse-agent",
      userId: null,
      status: "completed",
      input: { query: "hi" },
      output: "x",
      error: null,
      modelSteps: 1,
      toolCalls: 0,
      toolErrors: 0,
      promptTokens: 0,
      completionTokens: 0,
      totalTokens: 0,
      provider: "openai",
      model: "gpt-4o",
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
      startedAt: null,
      finishedAt: null,
    };
    expect(record.context).toBeUndefined();
  });
});
