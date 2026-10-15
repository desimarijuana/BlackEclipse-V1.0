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

import { spawn, execSync, type ChildProcess } from "child_process";
import { existsSync, readdirSync, statSync } from "fs";
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
  /** Last successful health verification (ms). Short-TTL cache so a burst of
   * requests (one page load fans out several API routes) shares a single probe
   * instead of each doing its own round-trip + directory scan. */
  __harnessPyHealthyAt?: number;
  /** In-flight ensure() so concurrent callers coalesce onto one probe. */
  __harnessPyEnsure?: Promise<boolean>;
}

const g = globalThis as unknown as RuntimeGlobal;

// A memory/skills tab load fans out several API routes at once; without this,
// each route re-probed `/health` and re-scanned the source directory on every
// call. A short TTL is safe: staleness is still detected within the window, and
// an actually-down runtime re-probes immediately after the TTL.
const HEALTH_TTL_MS = 5_000;

interface HealthInfo {
  ok?: boolean;
  service?: string;
  startedAtMs?: number;
}

async function getHealth(timeoutMs = 1500): Promise<HealthInfo | null> {
  try {
    const res = await fetch(`${HARNESS_PY_URL}/health`, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return null;
    return (await res.json()) as HealthInfo;
  } catch {
    return null;
  }
}

async function isHealthy(timeoutMs = 1500): Promise<boolean> {
  return (await getHealth(timeoutMs)) !== null;
}

/**
 * Newest mtime of the Python runtime source. A running runtime whose
 * `startedAtMs` predates this is serving stale code — the classic case being an
 * orphaned uvicorn from a previous `npm run dev` (spawned as a child, it
 * survives the Next restart on Windows) that still holds the port. Without this
 * check every harness code change silently does nothing until the port is
 * cleared by hand.
 */
function harnessSourceMtimeMs(): number {
  // Walk the WHOLE harness tree, not just the top level: most of the runtime
  // lives in subpackages (`code/`, `mcp/`, `terminal/`, `skills/`, …). A
  // top-level-only scan missed every edit there, so a running runtime was never
  // detected as stale and kept serving old code after a change.
  try {
    const root = path.join(process.cwd(), "python", "harness");
    let newest = 0;
    const walk = (dir: string, depth: number): void => {
      if (depth > 6) return;
      let entries;
      try {
        entries = readdirSync(dir, { withFileTypes: true });
      } catch {
        return;
      }
      for (const entry of entries) {
        if (entry.isDirectory()) {
          if (entry.name === "__pycache__" || entry.name.startsWith(".")) continue;
          walk(path.join(dir, entry.name), depth + 1);
        } else if (entry.isFile() && entry.name.endsWith(".py")) {
          const m = statSync(path.join(dir, entry.name)).mtimeMs;
          if (m > newest) newest = m;
        }
      }
    };
    walk(root, 0);
    return newest;
  } catch {
    return 0;
  }
}

/** PIDs currently LISTENING on the runtime port (empty when none / unavailable). */
function listenerPidsOnPort(): string[] {
  try {
    if (process.platform === "win32") {
      const out = execSync("netstat -ano", { encoding: "utf8" });
      const pids = new Set<string>();
      for (const line of out.split("\n")) {
        if (line.includes(`:${HARNESS_PY_PORT}`) && line.includes("LISTENING")) {
          const pid = line.trim().split(/\s+/).pop();
          if (pid && pid !== "0") pids.add(pid);
        }
      }
      return [...pids];
    }
    const out = execSync(`lsof -t -i:${HARNESS_PY_PORT}`, { encoding: "utf8" }).trim();
    return out ? out.split("\n") : [];
  } catch {
    // No listener, or netstat/lsof unavailable — nothing to report.
    return [];
  }
}

/** Kill whatever is listening on the runtime port, if it is our stale service. */
function killListenerOnPort(): void {
  for (const pid of listenerPidsOnPort()) {
    try {
      if (process.platform === "win32") {
        execSync(`taskkill /F /PID ${pid}`, { stdio: "ignore" });
      } else {
        execSync(`kill -9 ${pid}`, { stdio: "ignore" });
      }
    } catch {
      /* already gone */
    }
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
  // Fast path: a recent successful check, and no reason to suspect it changed.
  if (g.__harnessPyHealthyAt && Date.now() - g.__harnessPyHealthyAt < HEALTH_TTL_MS) {
    return true;
  }
  // Coalesce concurrent callers (a page load fires several routes at once) onto
  // a single probe so the runtime is not asked N times for the same page.
  if (g.__harnessPyEnsure) return g.__harnessPyEnsure;

  g.__harnessPyEnsure = (async () => {
    const ok = await ensurePythonRuntimeUncached();
    if (ok) g.__harnessPyHealthyAt = Date.now();
    return ok;
  })().finally(() => {
    g.__harnessPyEnsure = undefined;
  });

  return g.__harnessPyEnsure;
}

async function ensurePythonRuntimeUncached(): Promise<boolean> {
  const health = await getHealth();
  if (health) {
    // A healthy runtime that started before our source was last edited is an
    // orphan serving stale code (e.g. one left by a previous `npm run dev`).
    // Replace it so code changes actually take effect. Only do this for a
    // runtime that identifies itself as ours — never kill an unrelated service.
    const sourceMtime = harnessSourceMtimeMs();
    const startedAt = health.startedAtMs ?? 0;
    const isOurs = health.service === "harness-runtime";
    if (isOurs && sourceMtime > 0 && startedAt > 0 && startedAt < sourceMtime) {
      console.warn(
        "[harness] stale Python runtime detected (started before the latest harness code) — restarting it"
      );
      killListenerOnPort();
      await new Promise((r) => setTimeout(r, 500));
    } else {
      return true;
    }
  }
  if (g.__harnessPyStart) return g.__harnessPyStart;

  // Not healthy, and we are not mid-start. A process may be holding the runtime
  // port without answering /health — a hung/zombie runtime from a previous
  // `npm run dev` (spawned as a child, it survives the Next restart on Windows).
  // It cannot serve a request and it blocks a fresh spawn, so clear it. A second,
  // longer probe guards against a transient timeout on a genuinely healthy
  // runtime under load (only a still-silent LISTENER is cleared; a cold start with
  // nothing listening goes straight to the spawn).
  if (listenerPidsOnPort().length > 0) {
    const recheck = await getHealth(4_000);
    if (!recheck) {
      killListenerOnPort();
      await new Promise((r) => setTimeout(r, 300));
    }
  }

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

    // Autonomous runs (automations/bots, jobs, tasks, fabric) execute inside the
    // runtime with no per-run model override — so they fall back to the runtime's
    // env default (`HARNESS_JOB_MODEL`, historically "llama3.1"). Interactive chat
    // passes the operator's saved model per run, which is why chat worked while a
    // scheduled bot failed with "model not found". Publish the SAME saved model
    // config into the child env so a bot uses the operator's configured provider
    // and model. A real env var always wins; this only fills the gaps.
    const extraEnv: Record<string, string> = {};
    try {
      const { getLLMConfig } = await import("@/lib/settings");
      const cfg = await getLLMConfig();
      const provider = cfg.provider === "auto" || cfg.provider === "mock" ? "openai" : cfg.provider;
      if (provider && !process.env.HARNESS_JOB_PROVIDER) extraEnv.HARNESS_JOB_PROVIDER = provider;
      if (cfg.model && !process.env.HARNESS_JOB_MODEL) extraEnv.HARNESS_JOB_MODEL = cfg.model;
      if (cfg.baseUrl && !process.env.HARNESS_JOB_BASE_URL) extraEnv.HARNESS_JOB_BASE_URL = cfg.baseUrl;
      if (cfg.apiKey && !process.env.HARNESS_JOB_API_KEY) extraEnv.HARNESS_JOB_API_KEY = cfg.apiKey;
    } catch (err) {
      console.warn("[harness] could not resolve saved model config for the runtime:", err);
    }

    const proc = spawn(
      py.cmd,
      ["-m", "uvicorn", "harness.main:app", "--host", HARNESS_PY_HOST, "--port", String(HARNESS_PY_PORT), "--app-dir", appDir],
      { cwd: projectRoot, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, ...extraEnv, PYTHONPATH: appDir } }
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
      return false;
    }
    return true;
  })();

  try {
    return await g.__harnessPyStart;
  } finally {
    // The spawn attempt is finished (ready or not). Health is the source of
    // truth from here on: keeping the resolved promise around would let a later
    // /health miss return a stale `true` and mask a runtime that has since hung.
    g.__harnessPyStart = undefined;
  }
}

/** Stop a spawned runtime (test/teardown helper). */
export function stopPythonRuntime(): void {
  g.__harnessPyProc?.kill();
  g.__harnessPyProc = undefined;
  g.__harnessPyStart = undefined;
  g.__harnessPyHealthyAt = undefined;
  g.__harnessPyEnsure = undefined;
}

/**
 * Force the managed Python runtime to restart — the self-hosting seam (Track B).
 *
 * A change under `python/harness/**` only takes effect after a restart, and the
 * runtime cannot cleanly restart itself. The FRONT DOOR owns it: kill whatever is
 * listening on the runtime port (only our own service is spawned here), clear the
 * health cache, then spawn a fresh process and wait for `/health`. Returns true
 * only when the new runtime is healthy; false means "it did not come back", which
 * `code/selfhost.py`'s guarded landing treats as a rollback trigger.
 */
export async function restartPythonRuntime(): Promise<boolean> {
  killListenerOnPort();
  await new Promise((r) => setTimeout(r, 500));
  stopPythonRuntime();
  return ensurePythonRuntimeUncached();
}
