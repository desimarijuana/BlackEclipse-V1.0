import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { SkillExecutionRecord } from "@/lib/harness/skills-types";
import { ExecutionActivity, type ExecutionWithSkill } from "./execution-activity";

const RUN: ExecutionWithSkill = {
  id: "exec_1",
  runId: "run_abc123",
  skillId: "finance.market-data",
  skillName: "Market data",
  version: "1.0.0",
  manifestHash: null,
  parentRunId: null,
  executionMode: "interactive",
  status: "completed",
  actor: null,
  output: null,
  durationMs: 120,
  traceId: null,
  createdAt: "2026-11-08T10:00:00Z",
  finishedAt: "2026-11-08T10:00:00Z",
} satisfies SkillExecutionRecord & { skillName: string };

function render(focusRunId?: string) {
  return renderToStaticMarkup(
    <ExecutionActivity
      executions={[RUN]}
      loading={false}
      error={null}
      onRefresh={() => {}}
      onOpenSkill={() => {}}
      onLearn={async () => {}}
      isOperator
      focusRunId={focusRunId}
      onClearFocus={() => {}}
    />,
  );
}

describe("ExecutionActivity focus", () => {
  it("expands the focused run on arrival", () => {
    const html = render(RUN.runId);
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain(RUN.runId);
  });

  it("leaves runs collapsed without a focus", () => {
    const html = render();
    expect(html).toContain('aria-expanded="false"');
  });
});
