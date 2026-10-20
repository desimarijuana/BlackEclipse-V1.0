import { useState } from "react";
import { createRoot } from "react-dom/client";
import { RslControlPanel } from "../../src/components/screens/skills/rsl-control-panel";
import { CandidateEvidencePanel } from "../../src/components/screens/skills/candidate-evidence-panel";

const windowBlock = (rate: number, n: number) => ({
  n, successes: Math.round(rate * n), rate, ciLow: rate - 0.1, ciHigh: rate + 0.1,
});

const driftSignal = {
  status: "drift",
  scope: "global",
  window: 30,
  baselineWindow: 100,
  current: windowBlock(0.33, 30),
  baseline: windowBlock(0.9, 100),
  drop: 0.57,
  threshold: 0.1,
  reasons: ["scripted drift"],
  availableScopes: ["global", "eclipse-agent"],
};

const evidence = {
  candidate: {
    id: "evo_drift_fixture",
    signature: "sig",
    sourceCategory: "drift",
    observedCount: 30,
    problemStatement: "Production success dropped for eclipse-agent.",
    targetPath: null,
    proposedOps: null,
    subjectType: "drift",
    scope: "eclipse-agent",
    status: "inert",
    refusalCode: null,
    activatedVersion: null,
    previousVersion: null,
    createdAt: "2026-10-20T00:00:00Z",
    updatedAt: "2026-10-20T00:00:00Z",
  },
  attempts: [],
  experiments: [],
};

function json(body: unknown) {
  return Promise.resolve({ ok: true, json: async () => body } as Response);
}

globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  if (url.includes("/api/evolution/rsl")) {
    return json({
      success: true, mode: "observe", running: true, busy: false,
      maxCandidates: 5, maxExperimentsPerDay: 3, k: 1,
      startedToday: 0, remainingToday: 3, budgetExhausted: false,
      driftWatch: { enabled: true, intervalSeconds: 300, running: true, last: {} },
    });
  }
  if (url.includes("/api/evolution/drift/scopes")) {
    return json({
      success: true,
      availableScopes: ["global", "eclipse-agent"],
      signals: [{ scope: "eclipse-agent", signal: driftSignal }],
    });
  }
  if (url.includes("/api/evolution/drift/history")) {
    return json({
      success: true, scope: "global", window: 30, baselineWindow: 100,
      threshold: 0.1, step: 30, requestedPoints: 2, truncated: false,
      points: [
        { offset: 0, at: "2026-10-20T00:00:00Z", status: "drift", drop: 0.57,
          current: driftSignal.current, baseline: driftSignal.baseline },
        { offset: 30, at: "2026-10-19T00:00:00Z", status: "stable", drop: null,
          current: driftSignal.current, baseline: driftSignal.baseline },
      ],
    });
  }
  if (url.includes("/api/evolution/drift/candidate")) {
    return json({
      success: true, created: true, reason: "drift",
      candidate: evidence.candidate, signal: driftSignal,
    });
  }
  if (url.includes("/api/evolution/drift")) return json(driftSignal);
  if (url.includes("/api/evolution/candidates/") && url.includes("evidence")) {
    return json({ success: true, ...evidence });
  }
  if (url.includes("/api/evolution/states")) {
    return json({ success: true, current: null, currents: [], states: [] });
  }
  if (url.includes("/api/evolution/surface-activations")) {
    return json({ success: true, activations: [] });
  }
  void init;
  return json({ success: true });
}) as typeof fetch;

function Harness() {
  const [scope, setScope] = useState("all");
  return (
    <div>
      <RslControlPanel scope={scope} onScopeChange={setScope} />
      <CandidateEvidencePanel scope={scope} />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
