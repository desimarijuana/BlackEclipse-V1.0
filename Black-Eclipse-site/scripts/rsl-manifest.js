// Build, verify or audit the committed evaluation-corpus manifest.
// Examples:
//   npm run rsl:manifest
//   npm run rsl:manifest -- --verify
//   npm run rsl:manifest -- --audit --json
const { spawnSync } = require("child_process");
const fs = require("fs");
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
  console.error("[rsl:manifest] Python agent stack not installed. Run: npm run setup:python");
  process.exit(1);
}

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.evaluation.corpus import main",
  "sys.exit(main(sys.argv[1:]))",
].join("; ");

const result = spawnSync(py, ["-c", launcher, ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: pythonDir,
  env: {
    ...process.env,
    PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  },
});
process.exit(result.status ?? 1);
