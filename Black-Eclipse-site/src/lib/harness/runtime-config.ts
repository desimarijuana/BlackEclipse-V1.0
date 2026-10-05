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

/** Packages installed by scripts/setup-python.js for the runtime. */
export const PYTHON_RUNTIME_PACKAGES = [
  "fastapi",
  "uvicorn[standard]",
  "langchain",
  "langchain-core",
  "langgraph",
  "langchain-openai",
  "langchain-anthropic",
  "langchain-google-genai",
  "langchain-mistralai",
  "jsonschema",
  "mcp",
  // Optional but default: a real PTY for persistent shells. Platform-marked in
  // python/requirements.txt, so exactly one is installed.
  process.platform === "win32" ? "pywinpty" : "ptyprocess",
] as const;
