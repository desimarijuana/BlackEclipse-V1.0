#!/usr/bin/env node
/*
 * The LIVE evaluation lane.
 *
 * Round 3 / W8 (ADR-H296). Runs the live tier with a REAL model and records
 * the result. It NEVER fabricates: with no provider configured it says so and
 * exits 0, because "not measured" is a legitimate state and a guessed number
 * is not.
 *
 * Usage:
 *   node scripts/run-live-evals.js --model <provider>/<model> [--base-url <url>]
 *   node scripts/run-live-evals.js --suite <name> [--limit <n>]
 */

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

// These scripts live in `<site>/scripts/`, so `..` IS the site root.
const site = path.resolve(__dirname, "..");
const pythonDir = path.join(site, "python");

function interpreter() {
  const vendored = path.join(site, "scripts", "vendor", "python", "python.exe");
  if (fs.existsSync(vendored)) return vendored;
  return process.platform === "win32" ? "python" : "python3";
}

const driver = path.join(os.tmpdir(), `eclipse-live-evals-${process.pid}.py`);
fs.writeFileSync(
  driver,
  [
    "import asyncio, sys",
    `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
    "from harness.evaluation.live_gate import run_live_gate",
    "args = sys.argv[1:]",
    "def opt(flag, default=''):",
    "    return args[args.index(flag) + 1] if flag in args else default",
    "suite, reason = asyncio.run(run_live_gate(",
    "    model=opt('--model'), base_url=opt('--base-url'), suite=opt('--suite'),",
    "    task_limit=int(opt('--limit', '12') or 12),",
    "))",
    "if suite is None:",
    "    print('[eval:live] NOT MEASURED - ' + reason)",
    "    raise SystemExit(0)",
    "print('[eval:live] run', suite.run_id, 'gate', 'PASS' if suite.passed else 'FAIL')",
    "for k, v in suite.aggregates.items():",
    "    print('  %-24s %s' % (k, 'UNKNOWN' if v is None else round(v, 4)))",
    "raise SystemExit(0 if suite.passed else 1)",
    "",
  ].join("\n"),
  "utf8",
);

try {
  const result = spawnSync(interpreter(), [driver, ...process.argv.slice(2)], {
    stdio: "inherit",
    cwd: site,
  });
  process.exit(result.status ?? 1);
} finally {
  try { fs.unlinkSync(driver); } catch (_) { /* best effort */ }
}
