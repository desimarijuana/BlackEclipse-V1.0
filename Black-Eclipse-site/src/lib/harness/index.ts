// ─── Harness public surface (Next.js front door) ─────────────────────────────
// The agentic runtime is Python; this barrel exports the TS-side pieces only:
// validation, settings resolution, the Python client and the JDdS data bridge.

export type {
  RunStatus,
  RunInput,
  RunResult,
  RunRecord,
  RunWorkspaceRef,
  HarnessEvent,
  HarnessErrorJson,
  DataCapability,
  UsageSummary,
  UsageDay,
  UsageModel,
  UsageRecentRun,
  ResearchMetadata,
  ResearchRunInfo,
  ResearchCitation,
  ResearchClaim,
  ResearchCoverageLeg,
} from "./types";
export { HarnessError, toHarnessErrorJson, redactSecrets } from "./errors";
export type { HarnessErrorCode } from "./errors";
export { validateRunInput, assertRunInput, validateWorkspaceRef, MAX_QUERY_LENGTH } from "./validation";
export { newRunId } from "./ids";
export { startRun, chatWithAgent, startChatRun } from "./run-service";
export type { StartRunOptions } from "./run-service";
export { loadAgentPresets, getAgentPreset, DEFAULT_AGENT_ID } from "./agent-presets";
export type { AgentPreset } from "./agent-presets";
export { fetchCapability } from "./data-bridge";
export {
  runtimeHealth,
  listModelProviders,
  listAgentsFromRuntime,
  runViaRuntime,
  startRunBackground,
  getRunFromRuntime,
  listRunsFromRuntime,
  getUsageSummaryFromRuntime,
  getEventsFromRuntime,
  getRunExplanationFromRuntime,
  getRunReceiptFromRuntime,
  cancelRunInRuntime,
  HarnessRuntimeUnavailable,
} from "./python-client";
export {
  listRuntimeProviders,
  listRuntimeModels,
  discoverRuntimeModels,
  getRuntimeRouting,
  getRuntimeDecisions,
  routeModel,
  getRuntimeHealth,
  getRuntimeUsage,
} from "./model-runtime-client";
export type {
  CapabilityState,
  PricingKind,
  DiscoveryResult,
  RuntimeProviderView,
  RuntimeModelView,
  RuntimeRouteDecisionView,
  RuntimeRouteCandidateView,
  RuntimeRoutingView,
  RuntimeHealthView,
  RuntimeUsageView,
  RouteQuery,
} from "./model-runtime-client";
export { ensurePythonRuntime, HARNESS_PY_URL } from "./python-runtime";
