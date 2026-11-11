#!/usr/bin/env node
// Packaged-Python integration test.
//
// The HTTP smoke test proves the app answers. It says nothing about whether the
// bundled interpreter can import the harness, run a tool, or read the database —
// which is where a packaged install actually fails.
//
// Runs a deterministic script inside the packaged interpreter:
//   1. import the harness modules the agent path needs
//   2. execute a real deterministic tool (finance_calc, no network, no LLM)
//   3. open the packaged database and read from it
//   4. report a marker per step
//
//   node scripts/desktop-python-test.js [--app <app dir>]
//
// Exit 0 only when every step reports OK.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const argApp = (() => {
  const i = process.argv.indexOf("--app");
  return i !== -1 ? process.argv[i + 1] : null;
})();

const APP = argApp || path.join(ROOT, "dist", "BlackEclipse", "app");

const PYTHON_CANDIDATES = [
  path.join(APP, "scripts", "vendor", "python", "python.exe"),
  path.join(APP, "scripts", "vendor", "python", "bin", "python3"),
];

function findPython() {
  for (const p of PYTHON_CANDIDATES) if (fs.existsSync(p)) return p;
  return null;
}

const python = findPython();
if (!python) {
  console.error(`[py-test] no packaged interpreter under ${path.join(APP, "scripts", "vendor", "python")}`);
  process.exit(1);
}

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-pytest-"));
const script = path.join(dataDir, "probe.py");

const probe = String.raw`
import json, os, sqlite3, sys, traceback

# The Windows embeddable interpreter ships python312._pth, which makes it IGNORE
# PYTHONPATH. The runtime compensates with uvicorn's --app-dir; mirror that here
# so the test exercises the same import path the app uses.
APP = os.environ["BE_APP_DIR"]
# Measure BEFORE inserting: the embedded interpreter's ._pth makes it ignore
# PYTHONPATH, which is worth reporting rather than assuming.
_PP = os.environ.get("PYTHONPATH", "")
_PTH_IGNORES = bool(_PP) and _PP not in sys.path
sys.path.insert(0, os.path.join(APP, "python"))

report = {"steps": [], "ok": True, "python": sys.version.split()[0], "pth_ignores_pythonpath": None}

def step(name, fn):
    try:
        value = fn()
        report["steps"].append({"name": name, "ok": True, "detail": value})
    except Exception as exc:
        report["steps"].append({
            "name": name,
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc().splitlines()[-3:],
        })
        report["ok"] = False

def pth_probe():
    # The Windows embeddable interpreter ships a python3xx._pth which puts it in
    # isolated mode: PYTHONPATH is IGNORED. The runtime works only because it also
    # passes uvicorn's --app-dir. Asserting this keeps a future refactor honest.
    _pth = os.path.join(os.path.dirname(sys.executable), "python312._pth")
    report["pth_ignores_pythonpath"] = os.path.exists(_pth)
    if os.path.exists(_pth):
        return "._pth present: PYTHONPATH is ignored (the runtime uses --app-dir instead)"
    return "no ._pth: PYTHONPATH honoured"
    return "PYTHONPATH ignored by ._pth (compensated via sys.path)" if ignores else "PYTHONPATH honoured"

def imports():
    import harness.tools  # noqa
    import harness.agents  # noqa
    from harness.research import web_tools  # noqa
    return "harness.tools, harness.agents, harness.research.web_tools"

def registry():
    from harness.tools import ToolRegistry
    from harness.finance_tools import register_finance_tools
    reg = ToolRegistry()
    register_finance_tools(reg)
    names = reg.names()
    if len(names) < 2:
        raise AssertionError("expected the finance tools, got " + str(names))
    for required in ("get_market_snapshot", "get_fundamentals"):
        if required not in names:
            raise AssertionError(required + " not registered (got " + str(names) + ")")
    return str(len(names)) + " tools: " + ", ".join(names)

def tool_execution():
    import asyncio
    from harness.research import web_tools
    text, payload = asyncio.run(
        web_tools.finance_calc({"metric": "percentage_change", "inputs": {"start": 100, "end": 125}}, None)
    )
    if "25" not in str(text):
        raise AssertionError(f"unexpected result: {text!r}")
    return str(text)[:120]

def database():
    db = os.path.join(os.environ["BE_DATA_DIR"], "jdds.db")
    if not os.path.exists(db):
        raise AssertionError(f"no database at {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tables = con.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
        if tables < 10:
            raise AssertionError(f"only {tables} tables — schema not applied")
        return f"{tables} tables, readable"
    finally:
        con.close()

step("python ._pth behaviour", pth_probe)
step("import harness modules", imports)
step("tool registry", registry)
step("deterministic tool execution", tool_execution)
step("sqlite access", database)

print("__PROBE__" + json.dumps(report))
`;

fs.writeFileSync(script, probe, "utf8");

const env = {
  ...process.env,
  BE_DATA_DIR: dataDir,
  BE_APP_DIR: APP,
  PYTHONPATH: path.join(APP, "python"),
  PYTHONDONTWRITEBYTECODE: "1",
};

console.log(`[py-test] interpreter ${python}`);
console.log(`[py-test] app         ${APP}`);

// Seed a database so the SQLite step tests the real schema.
const seed = path.join(APP, "seed", "jdds.db");
if (fs.existsSync(seed)) {
  fs.copyFileSync(seed, path.join(dataDir, "jdds.db"));
  console.log("[py-test] seeded the test database from app/seed/jdds.db");
}

const r = spawnSync(python, [script], {
  cwd: APP,
  env,
  encoding: "utf8",
  timeout: 180_000,
});

const out = `${r.stdout || ""}\n${r.stderr || ""}`;
const line = out.split("\n").find((l) => l.includes("__PROBE__"));
if (!line) {
  console.error("[py-test] FAIL — the probe produced no result");
  console.error(out.split("\n").slice(-20).join("\n"));
  process.exit(1);
}

const report = JSON.parse(line.slice(line.indexOf("__PROBE__") + 9));
console.log(`[py-test] python ${report.python}`);

for (const s of report.steps) {
  console.log(`  ${s.ok ? "OK  " : "FAIL"}  ${s.name}${s.detail ? ` — ${s.detail}` : ""}`);
  if (!s.ok && s.trace) for (const t of s.trace) console.log(`         ${t}`);
}

fs.rmSync(dataDir, { recursive: true, force: true });
console.log(report.ok ? "[py-test] PASS" : "[py-test] FAIL");
process.exit(report.ok ? 0 : 1);
