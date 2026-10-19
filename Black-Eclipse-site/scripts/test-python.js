// Run the Python harness test suite with the same interpreter the runtime uses.
// Skips (exit 0) when Python or the agent stack is absent, so `npm test` stays
// usable on a machine without the runtime — the TS suite still gates the app.
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

function tryRun(cmd, args, opts = {}) {
  try {
    return spawnSync(cmd, args, { stdio: "ignore", ...opts });
  } catch {
    return { status: 1 };
  }
}

function usable(cmd) {
  if (tryRun(cmd, ["--version"]).status !== 0) return false;
  return tryRun(cmd, ["-c", "import langgraph, pytest"]).status === 0;
}

const isPath = (c) => c.includes(path.sep) || c.endsWith(".exe");
const py = candidates.find((c) => usable(isPath(c) ? c : c));
if (!py) {
  console.log("[test] Python agent stack not installed — skipping Python tests.");
  console.log("[test] Install it with: npm run setup:python");
  process.exit(0);
}

// `node scripts/test-python.js smoke` runs the OPERATOR-TRIGGERED live smoke
// checks, which contact real external providers. They are deliberately separate
// from the default offline suite: never part of `npm test`.
// The vendored interpreter ships a `python312._pth` that disables implicit
// sys.path[0] insertion, so `-m harness.*` cannot resolve the package from cwd
// alone. Set PYTHONPATH explicitly for every child (pytest and the smoke runner)
// so the vendored and system interpreters behave identically.
// Isolate the suite from the developer's real memory database. `eclipse-memory.db`
// carries installed skill versions; reusing it across runs made `test_skills_api`
// fail on a stale content hash. Tests are expected to get a temp file (see
// `harness/eclipse_memory/config.py`); this runner makes that true for the whole
// suite, not just the modules that call `setdefault` themselves.
const isolatedMemoryDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-pytest-"));
const childEnv = {
  ...process.env,
  // Both stores are per-run temp files. The harness service reads these paths at
  // import time; modules that call `setdefault` then agree with the booted
  // service instead of racing it with their own temp path.
  AGENT_MEMORY_DB_PATH: path.join(isolatedMemoryDir, "agent-memory.db"),
  ECLIPSE_MEMORY_DB_PATH: path.join(isolatedMemoryDir, "eclipse-memory.db"),
  PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
};

if (process.argv.includes("smoke")) {
  console.log("[test] Running live network smoke checks (contacts real providers)…");
  // The vendored interpreter ships a `python312._pth` that ignores PYTHONPATH and
  // cwd, so `-m harness.*` cannot resolve the package. Inject the path explicitly
  // and call the runner, which works identically for vendored and system pythons.
  const launcher = [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
    "from harness.research.smoke import main",
    "sys.exit(main())",
  ].join("; ");
  const smoke = spawnSync(py, ["-c", launcher], {
    stdio: "inherit",
    cwd: pythonDir,
    env: childEnv,
  });
  process.exit(smoke.status ?? 1);
}

const result = spawnSync(py, ["-m", "pytest", pythonDir], { stdio: "inherit", cwd: root, env: childEnv });
process.exit(result.status ?? 1);
