// The unattended nightly session: run the corpus, compare with the recorded
// baseline and write a dated report. Exits non-zero on a CRITICAL regression,
// so CI fails when the harness got worse.
//   npm run rsl:nightly -- --promote
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
  console.error("[rsl:nightly] Python agent stack not installed. Run: npm run setup:python");
  process.exit(1);
}

// Path flags are resolved against the REPO ROOT: the python child runs with
// cwd=python/, so a relative path would land in the wrong place.
const PATH_FLAGS = new Set(["--baseline-file", "--write-baseline", "--out"]);
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i += 1) {
  if (!PATH_FLAGS.has(args[i])) continue;
  const value = args[i + 1];
  if (!value || path.isAbsolute(value)) continue;
  args[i + 1] = path.resolve(root, value);
}

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-rsl-nightly-"));
const env = {
  ...process.env,
  PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  AGENT_MEMORY_DB_PATH:
    process.env.AGENT_MEMORY_DB_PATH || path.join(tempDir, "agent-memory.db"),
  ECLIPSE_MEMORY_DB_PATH:
    process.env.ECLIPSE_MEMORY_DB_PATH || path.join(tempDir, "eclipse-memory.db"),
};

// The vendored interpreter ships a `_pth` that ignores PYTHONPATH and cwd, so
// inject the package root explicitly (same pattern as rsl-bench.js).
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.evaluation.nightly import main",
  "sys.exit(main(sys.argv[1:]))",
].join("; ");

const result = spawnSync(py, ["-c", launcher, ...args], {
  stdio: "inherit",
  cwd: pythonDir,
  env,
});
if (result.status !== 0) {
  console.error("[rsl:nightly] the nightly session FAILED (a critical regression?)");
}
process.exit(result.status ?? 1);
