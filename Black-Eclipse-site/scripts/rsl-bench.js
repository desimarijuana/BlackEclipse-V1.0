// Run the RSL three-arm ablation with the runtime's Python interpreter.
// Isolated agent-memory database by default; pass --run-db to use another one.
// Example:
//   npm run rsl:bench -- --trials 3 --surface-snapshot snapshot.json
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const root = path.join(__dirname, "..");
const pythonDir = path.join(root, "python");
const vendored = path.join(__dirname, "vendor", "python", "python.exe");

const candidates =
  process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];

function usable(cmd) {
  try {
    return spawnSync(cmd, ["-c", "import langgraph, pytest"], { stdio: "ignore" }).status === 0;
  } catch {
    return false;
  }
}

const py = candidates.find((cmd) => usable(cmd));
if (!py) {
  console.error("[rsl:bench] Python agent stack not installed. Run: npm run setup:python");
  process.exit(1);
}

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-rsl-bench-"));
const args = process.argv.slice(2);
const env = {
  ...process.env,
  PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  AGENT_MEMORY_DB_PATH:
    process.env.AGENT_MEMORY_DB_PATH || path.join(tempDir, "agent-memory.db"),
  ECLIPSE_MEMORY_DB_PATH:
    process.env.ECLIPSE_MEMORY_DB_PATH || path.join(tempDir, "eclipse-memory.db"),
};

// The vendored interpreter ships a `_pth` that ignores PYTHONPATH and cwd, so
// inject the package root explicitly (same pattern as rsl-smoke.js).
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.evaluation.ablation import main",
  "sys.exit(main(sys.argv[1:]))",
].join("; ");

const result = spawnSync(
  py,
  ["-c", launcher, ...args],
  { stdio: "inherit", cwd: pythonDir, env },
);
if (result.status !== 0) {
  console.error(`[rsl:bench] ablation exited ${result.status ?? "unknown"}`);
}
process.exit(result.status ?? 1);
