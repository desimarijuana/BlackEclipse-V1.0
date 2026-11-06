import { describe, it, expect, vi, beforeEach } from "vitest";

// The chat route must fail HONESTLY when the Python runtime is unavailable:
// a 503 with a stable error code, never a fabricated answer and never a silent
// fall-back to a fake agent. This test locks that contract at the route layer
// (the rest of the suite only covers the pieces in isolation).

const chatWithAgent = vi.fn();

vi.mock("@/lib/harness/run-service", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/harness/run-service")>();
  return { ...actual, chatWithAgent: (...args: unknown[]) => chatWithAgent(...args) };
});

// Avoid touching the filesystem for session documents.
vi.mock("@/lib/chat/session-store", () => ({
  loadContextDocuments: vi.fn(async () => []),
  writeSessionFile: vi.fn(async () => undefined),
}));

import { POST } from "@/app/api/harness/chat/route";
import { HarnessRuntimeUnavailable } from "@/lib/harness/python-client";
import { HarnessError } from "@/lib/harness/errors";
import { MAX_QUERY_LENGTH } from "@/lib/harness/validation";

function post(body: unknown): Request {
  return new Request("http://localhost:3000/api/harness/chat", {
    method: "POST",
    headers: { origin: "http://localhost:3000", "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/harness/chat — honest failure", () => {
  beforeEach(() => chatWithAgent.mockReset());

  it("returns 503 when the Python runtime is unavailable", async () => {
    chatWithAgent.mockRejectedValueOnce(
      new HarnessRuntimeUnavailable("The Python agent runtime is not available. Install: npm run setup:python")
    );
    const res = await POST(post({ query: "hello" }));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toMatch(/runtime is not available/i);
    // The runtime-unavailable error carries its own stable code for the UI.
    expect(body.code).toBe("RUNTIME_UNAVAILABLE");
    // No fabricated answer.
    expect(body.content).toBeUndefined();
    expect(body.success).toBeUndefined();
  });

  it("returns 503 for a missing provider configuration (not a fake answer)", async () => {
    chatWithAgent.mockRejectedValueOnce(
      new HarnessError("PROVIDER_NOT_CONFIGURED", "No model provider is configured")
    );
    const res = await POST(post({ query: "hello" }));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.code).toBe("PROVIDER_NOT_CONFIGURED");
    expect(body.content).toBeUndefined();
  });

  it("returns 400 for invalid input", async () => {
    const res = await POST(post({ query: "" }));
    expect(res.status).toBe(400);
    expect(chatWithAgent).not.toHaveBeenCalled();
  });

  it("accepts a long message — a turn is whatever the person pasted", async () => {
    chatWithAgent.mockResolvedValueOnce({ status: "completed", output: "ok", runId: "run_x" });
    const res = await POST(post({ query: "x".repeat(50_000) }));
    expect(res.status).toBe(200);
    expect(chatWithAgent).toHaveBeenCalledTimes(1);
  });

  it("refuses an over-cap message with a stable code", async () => {
    const res = await POST(post({ query: "x".repeat(MAX_QUERY_LENGTH + 1) }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.code).toBe("INVALID_INPUT");
    expect(chatWithAgent).not.toHaveBeenCalled();
  });

  it("forwards an explicit quant mode and drops auto", async () => {
    chatWithAgent.mockResolvedValue({ status: "completed", output: "ok", runId: "run_q" });
    await POST(post({ query: "forecast gold for tomorrow", quantMode: "on" }));
    expect(chatWithAgent.mock.calls[0][12]).toBe("on");

    await POST(post({ query: "what is gold trading at", quantMode: "auto" }));
    expect(chatWithAgent.mock.calls[1][12]).toBeUndefined();
  });

  it("forwards an explicit choices mode and drops auto", async () => {
    chatWithAgent.mockResolvedValue({ status: "completed", output: "ok", runId: "run_c" });
    await POST(post({ query: "analyse apple", choicesMode: "on" }));
    expect(chatWithAgent.mock.calls[0][13]).toBe("on");

    await POST(post({ query: "analyse apple", choicesMode: "auto" }));
    expect(chatWithAgent.mock.calls[1][13]).toBeUndefined();
  });

  it("returns 502 when the run itself failed (never a fabricated success)", async () => {
    chatWithAgent.mockResolvedValueOnce({
      status: "failed", error: "upstream provider error", runId: "run_x",
    });
    const res = await POST(post({ query: "hello" }));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.success).toBe(false);
    expect(body.content).toBeUndefined();
  });
});
