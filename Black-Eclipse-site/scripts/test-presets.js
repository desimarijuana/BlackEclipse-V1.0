// Opt-in release-tag precondition: prove every shipped `stdio` preset package
// can actually be launched.
//
// WHY: a preset is a promise that clicking it works. The default (offline) suite
// can only assert a preset's SHAPE; it cannot see that `sec-edgar-mcp` has no
// `bin` and no server code. This check resolves each `stdio` preset package's
// `bin` via `npm view <pkg> bin` and fails if it is empty. Like `test:smoke` it
// hits the network, so it is NEVER part of `npm test` or CI — a human runs it
// before a release tag.
//
// It reads the presets from Python (the single source of truth) rather than
// duplicating the package list here.
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

function tryRun(cmd, args, opts = {}) {
  try {
    return spawnSync(cmd, args, { encoding: "utf8", ...opts });
  } catch {
    return { status: 1 };
  }
}

const isPath = (c) => c.includes(path.sep) || c.endsWith(".exe");
const usable = (cmd) =>
  tryRun(cmd, ["--version"]).status === 0 &&
  tryRun(cmd, ["-c", "import langgraph, pytest"]).status === 0;
const py = candidates.find((c) => usable(isPath(c) ? c : c));
if (!py) {
  console.log("[presets] Python agent stack not installed — skipping preset checks.");
  console.log("[presets] Install it with: npm run setup:python");
  process.exit(0);
}

// Emit `id<TAB>package` for every stdio preset. The package is the FIRST
// non-flag argument (a later non-flag argument may be a path, e.g. filesystem's
// trailing "."). The pure Python shape test already asserts one exists.
const listLauncher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.mcp.presets import INTEGRATIONS",
  "for s in INTEGRATIONS:",
  "    if s.transport == 'stdio':",
  "        pkg = next((a for a in s.args if not a.startswith('-')), '')",
  "        print(f'{s.id}\\t{pkg}')",
].join("\n");

const listed = spawnSync(py, ["-c", listLauncher], { encoding: "utf8", cwd: pythonDir });
if (listed.status !== 0) {
  console.error(listed.stderr || "[presets] could not read the preset list");
  process.exit(1);
}

const rows = listed.stdout
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter(Boolean)
  .map((line) => {
    const [id, pkg] = line.split("\t");
    return { id, pkg };
  });

// `npm` on Windows is `npm.cmd`; spawnSync resolves it with shell:true.
const npm = (args) => spawnSync("npm", args, { encoding: "utf8", shell: process.platform === "win32" });

let failures = 0;
console.log("[presets] Resolving `bin` for every stdio preset package (network)…");
for (const { id, pkg } of rows) {
  if (!pkg) {
    console.log(`  FAIL ${id}: no package argument`);
    failures += 1;
    continue;
  }
  const res = npm(["view", pkg, "bin", "--json"]);
  const out = (res.stdout || "").trim();
  const missing = res.status !== 0 && /E404|not found/i.test(res.stderr || "");
  if (missing) {
    console.log(`  FAIL ${id} (${pkg}): package not found on npm`);
    failures += 1;
    continue;
  }
  if (res.status !== 0) {
    console.log(`  FAIL ${id} (${pkg}): npm view failed — ${(res.stderr || "").trim().split("\n")[0]}`);
    failures += 1;
    continue;
  }
  // `bin` is empty (no output / "{}") when the package has no executable.
  const hasBin = out && out !== "{}" && out !== "null";
  if (!hasBin) {
    console.log(`  FAIL ${id} (${pkg}): package declares no \`bin\` — it cannot be launched`);
    failures += 1;
  } else {
    console.log(`  ok   ${id} (${pkg})`);
  }
}

if (failures) {
  console.error(`[presets] ${failures} preset package(s) cannot be launched.`);
  process.exit(1);
}
console.log("[presets] All stdio preset packages resolve a `bin`.");
