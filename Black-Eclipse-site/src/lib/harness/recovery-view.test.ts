import { describe, expect, it } from "vitest";
import {
  countByStatus,
  diagnosisHeadline,
  formatIncidentLine,
  statusTone,
  topKinds,
  type RecoveryIncidentView,
} from "./recovery-view";

function incident(partial: Partial<RecoveryIncidentView>): RecoveryIncidentView {
  return {
    id: "inc_1",
    signature: "sig",
    kind: "timeout",
    retryability: "retryable",
    code: "TOOL_TIMEOUT",
    subsystem: "tools",
    source: "tool",
    message: "timed out",
    taskId: "t1",
    runId: null,
    status: "resolved",
    occurrenceCount: 2,
    attempts: 1,
    decision: { action: "recover", strategy: "retry", reason: "", backoffMs: 500, exhausted: false, requiresApproval: false },
    diagnosis: null,
    firstSeenAt: "2026-10-09T00:00:00Z",
    lastSeenAt: "2026-10-09T00:00:01Z",
    ...partial,
  };
}

describe("recovery-view", () => {
  it("counts incidents by status", () => {
    const rows = [incident({ id: "a", status: "resolved" }), incident({ id: "b", status: "open" }), incident({ id: "c", status: "open" })];
    expect(countByStatus(rows)).toEqual({ resolved: 1, open: 2 });
  });

  it("ranks kinds by frequency", () => {
    const rows = [incident({ kind: "timeout" }), incident({ kind: "timeout" }), incident({ kind: "dependency" })];
    expect(topKinds(rows)).toEqual([{ kind: "timeout", count: 2 }, { kind: "dependency", count: 1 }]);
  });

  it("formats a content-light incident line", () => {
    expect(formatIncidentLine(incident({}))).toBe("timeout · TOOL_TIMEOUT · tools ×2 → retry");
  });

  it("diagnosis headline is decisive only when selected", () => {
    expect(diagnosisHeadline(null)).toBe("no diagnosis");
    expect(
      diagnosisHeadline({ kind: "timeout", selected: "x", confidence: 0.9, decisive: true, hypotheses: [], evidence: {}, missingInformation: [] }),
    ).toContain("root cause: x");
    expect(
      diagnosisHeadline({ kind: "timeout", selected: null, confidence: 0.5, decisive: false, hypotheses: [], evidence: {}, missingInformation: ["a", "b"] }),
    ).toContain("2 evidence gaps");
  });

  it("maps status to a tone", () => {
    expect(statusTone("resolved")).toContain("emerald");
    expect(statusTone("failed")).toContain("red");
    expect(statusTone("weird")).toContain("zinc");
  });
});