// ─── Harness public surface (Next.js front door) ─────────────────────────────
// The agentic runtime is Python; this barrel exports the TS-side pieces only:
// validation, settings resolution, the Python client and the JDdS data bridge.

export type {
  RunStatus,
  RunInput,
  RunResult,
  RunRecord,
  HarnessEvent,
  HarnessErrorJson,
  DataCapability,
  UsageSummary,
  UsageDay,
  UsageModel,
  UsageRecentRun,
} from "./types";
export { HarnessError, toHarnessErrorJson, redactSecrets } from "./errors";
export type { HarnessErrorCode } from "./errors";
export { validateRunInput, assertRunInput } from "./validation";
export { newRunId } from "./ids";
export { startRun, chatWithAgent } from "./run-service";
export type { StartRunOptions } from "./run-service";
export { loadAgentPresets, getAgentPreset, DEFAULT_AGENT_ID } from "./agent-presets";
export type { AgentPreset } from "./agent-presets";
export { fetchCapability } from "./data-bridge";
export {
  runtimeHealth,
  listModelProviders,
  listAgentsFromRuntime,
  runViaRuntime,
  getRunFromRuntime,
  listRunsFromRuntime,
  getUsageSummaryFromRuntime,
  getEventsFromRuntime,
  cancelRunInRuntime,
  HarnessRuntimeUnavailable,
} from "./python-client";
export { ensurePythonRuntime, HARNESS_PY_URL } from "./python-runtime";
