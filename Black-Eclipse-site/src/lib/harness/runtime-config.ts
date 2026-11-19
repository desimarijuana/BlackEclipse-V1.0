// Shared constants for the Python runtime so the launcher and doctor agree on
// what "installed" means.

/**
 * The importable probe for "is the agent stack installed". Must be a real
 * installed package (not the local `harness` package, which is only importable
 * with PYTHONPATH set). `langgraph` is the runtime marker.
 */
export const PYTHON_RUNTIME_DEPS = "langgraph";

/** A second probe for a package added after the initial runtime (Phase 5 MCP). */
export const PYTHON_MCP_DEPS = "mcp";

/**
 * A third probe for the JSON Schema validator. It arrives transitively via
 * `mcp`, but skill contract enforcement depends on it directly, so a repair
 * flow must be able to restore it even if a future `mcp` stops pulling it in.
 */
export const PYTHON_SCHEMA_DEPS = "jsonschema";

/**
 * An OPTIONAL probe: the real pseudo-terminal for the terminal subsystem
 * (`pywinpty` on Windows, `ptyprocess` elsewhere). Its absence is not a runtime
 * failure — the session layer falls back to a piped shell and reports
 * `pty: false` — so a repair is best-effort, never a hard dependency.
 */
export const PYTHON_PTY_DEPS = process.platform === "win32" ? "winpty" : "ptyprocess";

/**
 * The chart engine's drawing libraries. `matplotlib` draws the PNG; `plotly`
 * draws the live, zoomable figure. A runtime with `langgraph` but without these
 * is a runtime that cannot draw a single chart, so they get their own probes
 * rather than being implied by the agent-stack marker.
 */
export const PYTHON_CHART_DEPS = ["matplotlib", "plotly"] as const;

/**
 * EVERY third-party module `python/harness/charts/*.py` imports.
 *
 * This is the contract the regression test enforces (see
 * `runtime-config.test.ts`): the chart engine cannot draw unless each of these
 * is importable by the SAME interpreter `findPython()` selected. Keep it in
 * sync with the charts package — the test fails the build when it drifts, so a
 * missing chart dependency can never be a silent 503 again.
 */
export const PYTHON_CHART_PACKAGES = [
  "matplotlib",
  "numpy",
  "plotly",
  "pydantic",
] as const;

/** Packages installed by scripts/setup-python.js for the runtime. */
export const PYTHON_RUNTIME_PACKAGES = [
  "fastapi",
  "uvicorn[standard]",
  "pydantic",
  "langchain",
  "langchain-core",
  "langgraph",
  "langchain-openai",
  "langchain-anthropic",
  "langchain-google-genai",
  "langchain-mistralai",
  "jsonschema",
  "mcp",
  // The chart engine (and the report/figure renderers) draw with these. They
  // used to be installed only as a side effect of the analysis sandbox stack,
  // so a machine that already had `langgraph` never got them — every chart was
  // a 503 with no mention of matplotlib. Enumerate them here so every install
  // and repair path covers them.
  "matplotlib",
  "numpy",
  "plotly",
  // Optional but default: a real PTY for persistent shells. Platform-marked in
  // python/requirements.txt, so exactly one is installed.
  process.platform === "win32" ? "pywinpty" : "ptyprocess",
] as const;

/**
 * What "the chart engine can draw" means, agreed on by the launcher, the
 * charts route and the doctor. `python` is the interpreter that was probed, so
 * an operator can see WHICH python lacks matplotlib.
 */
export interface ChartEngineReadiness {
  ready: boolean;
  python: string | null;
  missing: string[];
}

/**
 * Combine an interpreter path with the modules it reported importable. Pure, so
 * the shape of the decision is testable without spawning Python.
 */
export function chartEngineReadiness(
  python: string | null,
  available: readonly string[],
): ChartEngineReadiness {
  const present = new Set(available);
  const missing = PYTHON_CHART_PACKAGES.filter((name) => !present.has(name));
  return { ready: Boolean(python) && missing.length === 0, python, missing };
}

/**
 * The one-line repair instruction shown to an operator. Kept here so the route,
 * the UI and the doctor never disagree about the command.
 */
export const PYTHON_CHART_REPAIR_HINT = "Run `npm run setup:python`";
