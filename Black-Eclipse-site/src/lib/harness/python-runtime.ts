// ─── Python runtime launcher ─────────────────────────────────────────────────
// The agentic runtime is the Python service in `python/harness/`. The Next.js
// process spawns it on first use (lazily, once) and talks to it over HTTP.
//
// Why spawn rather than require an operator to run it:
//   • keep the app a single `npm run dev` process tree;
//   • the interpreter is the same Python the repo already provisions for the
//     yfinance bridge (vendored embedded Python on Windows);
//   • readiness is health-checked, and a failure is reported honestly — never
//     silently degraded into a fake agent.

import { spawn, type ChildProcess } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { findPython } from "@/lib/scraper/fetchers/python";
import { PYTHON_RUNTIME_DEPS } from "./runtime-config";

// The URL is authoritative. When an operator overrides HARNESS_PY_URL, the
// spawned uvicorn must bind the SAME host/port — otherwise health checks would
// pass on one port while the server listens on another.
function parseUrl(raw: string): { host: string; port: number } | null {
  try {
    const url = new URL(raw);
    return { host: url.hostname, port: Number(url.port || "80") };
  } catch {
    return null;
  }
}

export const HARNESS_PY_URL =
  process.env.HARNESS_PY_URL ?? `http://${process.env.HARNESS_PY_HOST ?? "127.0.0.1"}:${process.env.HARNESS_PY_PORT ?? 8765}`;
const parsed = parseUrl(HARNESS_PY_URL);
export const HARNESS_PY_HOST = parsed?.host ?? "127.0.0.1";
export const HARNESS_PY_PORT = parsed?.port ?? 8765;

interface RuntimeGlobal {
  __harnessPyProc?: ChildProcess;
  __harnessPyStart?: Promise<boolean>;
}

const g = globalThis as unknown as RuntimeGlobal;

async function isHealthy(timeoutMs = 1500): Promise<boolean> {
  try {
    const res = await fetch(`${HARNESS_PY_URL}/health`, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function waitForHealth(deadlineMs: number): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < deadlineMs) {
    if (await isHealthy()) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/**
 * Ensure the Python runtime is up. Returns true when healthy; false when it
 * could not be started (missing interpreter or dependencies). Callers must
 * treat `false` as "agent runtime unavailable", not fall back to a fake agent.
 */
export async function ensurePythonRuntime(): Promise<boolean> {
  if (await isHealthy()) return true;
  if (g.__harnessPyStart) return g.__harnessPyStart;

  g.__harnessPyStart = (async () => {
    const projectRoot = process.cwd();
    const appDir = path.join(projectRoot, "python");
    if (!existsSync(path.join(appDir, "harness", "main.py"))) {
      console.error("[harness] python/harness/main.py not found — runtime unavailable");
      return false;
    }

    // Require the agent stack to be importable before spawning, so a missing
    // dependency is a clear message rather than a crash loop.
    const py = await findPython(PYTHON_RUNTIME_DEPS);
    if (!py) {
      console.error(
        `[harness] Python with agent dependencies not found. Run: npm run setup:python`
      );
      return false;
    }

    const proc = spawn(
      py.cmd,
      ["-m", "uvicorn", "harness.main:app", "--host", HARNESS_PY_HOST, "--port", String(HARNESS_PY_PORT), "--app-dir", appDir],
      { cwd: projectRoot, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONPATH: appDir } }
    );
    g.__harnessPyProc = proc;

    proc.stdout?.on("data", (d) => process.stdout.write(`[harness-py] ${d}`));
    proc.stderr?.on("data", (d) => process.stderr.write(`[harness-py] ${d}`));
    proc.on("exit", (code) => {
      if (code !== 0 && code !== null) console.error(`[harness-py] exited with code ${code}`);
      g.__harnessPyProc = undefined;
      g.__harnessPyStart = undefined;
    });

    const ready = await waitForHealth(30_000);
    if (!ready) {
      console.error("[harness] Python runtime did not become healthy within 30s");
      proc.kill();
      g.__harnessPyStart = undefined;
      return false;
    }
    return true;
  })();

  return g.__harnessPyStart;
}

/** Stop a spawned runtime (test/teardown helper). */
export function stopPythonRuntime(): void {
  g.__harnessPyProc?.kill();
  g.__harnessPyProc = undefined;
  g.__harnessPyStart = undefined;
}
