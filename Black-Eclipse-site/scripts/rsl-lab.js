// The surface lab: the loop tries to improve its own harness, measured on the
// corpus. The winner is a CANDIDATE for the operator, never a landing.
//   npm run rsl:lab -- --memory-db <path> --out report.json
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
  console.error("[rsl:lab] Python agent stack not installed. Run: npm run setup:python");
  process.exit(1);
}

// Path flags are resolved against the REPO ROOT: the python child runs with
// cwd=python/, so a relative path would land in the wrong place.
const PATH_FLAGS = new Set(["--out", "--run-db", "--memory-db"]);
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i += 1) {
  if (!PATH_FLAGS.has(args[i])) continue;
  const value = args[i + 1];
  if (!value || path.isAbsolute(value)) continue;
  args[i + 1] = path.resolve(root, value);
}

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-rsl-lab-"));
const env = {
  ...process.env,
  PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  AGENT_MEMORY_DB_PATH:
    process.env.AGENT_MEMORY_DB_PATH || path.join(tempDir, "agent-memory.db"),
  ECLIPSE_MEMORY_DB_PATH:
    process.env.ECLIPSE_MEMORY_DB_PATH || path.join(tempDir, "eclipse-memory.db"),
};

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.self_improvement.surface_lab import main",
  "sys.exit(main(sys.argv[1:]))",
].join("; ");

const result = spawnSync(py, ["-c", launcher, ...args], {
  stdio: "inherit",
  cwd: pythonDir,
  env,
});
process.exit(result.status ?? 1);
