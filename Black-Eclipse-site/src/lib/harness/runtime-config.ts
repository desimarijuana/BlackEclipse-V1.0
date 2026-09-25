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
] as const;
