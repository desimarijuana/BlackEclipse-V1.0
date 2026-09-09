// Cross-platform Python resolution for the bridge fetchers.
//
// Windows ships `python` (and `py`); macOS/Linux ship `python3` (and
// sometimes `python` if python-is-python3 is installed). Spawning the wrong
// name throws ENOENT, so every bridge call must go through this resolver.

import { execFile } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

type PythonInfo = { cmd: string } | null;

const CANDIDATES = process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"];

// Vendored embedded Python downloaded by scripts/setup-embedded-python.js.
// When present it is the preferred interpreter so the yfinance/scrapling
// bridges work for new users without a system Python install.
const VENDOR_PYTHON =
  process.platform === "win32"
    ? path.join(process.cwd(), "scripts", "vendor", "python", "python.exe")
    : null;

function vendorAvailable(): boolean {
  return !!VENDOR_PYTHON && existsSync(VENDOR_PYTHON);
}

async function canRun(cmd: string, mod?: string): Promise<boolean> {
  try {
    const args = mod ? ["-c", `import ${mod}`] : ["--version"];
    await execFileAsync(cmd, args, { timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Find a usable Python interpreter, optionally one that has `mod` importable.
 * Prefers the vendored embedded Python when present, then a system interpreter.
 * Cached per module (a missing interpreter stays cached; a module check is
 * re-probed after 5 minutes like the yfinance availability cache).
 */
export async function findPython(mod?: string): Promise<PythonInfo> {
  const key = mod ?? "__interpreter__";
  const store = globalThis as unknown as {
    __pyCache?: Map<string, { value: PythonInfo; at: number }>;
  };
  if (!store.__pyCache) store.__pyCache = new Map();
  const hit = store.__pyCache.get(key);
  const ttl = mod ? 5 * 60 * 1000 : Infinity;
  if (hit && Date.now() - hit.at < ttl) return hit.value;

  // Vendored embedded Python is the primary choice on Windows.
  if (VENDOR_PYTHON && (mod ? await canRun(VENDOR_PYTHON, mod) : true)) {
    const result: PythonInfo = { cmd: VENDOR_PYTHON };
    store.__pyCache.set(key, { value: result, at: Date.now() });
    return result;
  }

  let result: PythonInfo = null;
  for (const cmd of CANDIDATES) {
    if (await canRun(cmd, mod)) {
      result = { cmd };
      break;
    }
  }
  store.__pyCache.set(key, { value: result, at: Date.now() });
  return result;
}

/** Run a Python bridge script with the resolved interpreter. */
export async function runPythonBridge(
  scriptPath: string,
  args: string[],
  opts: { timeout: number; maxBuffer?: number; mod?: string }
): Promise<{ stdout: string }> {
  const py = await findPython(opts.mod);
  if (!py) {
    throw new Error(
      `Python not found${opts.mod ? ` (with "${opts.mod}" installed)` : ""}. Install Python 3 and run: pip install yfinance scrapling`
    );
  }
  return execFileAsync(py.cmd, [scriptPath, ...args], {
    timeout: opts.timeout,
    maxBuffer: opts.maxBuffer ?? 8 * 1024 * 1024,
  });
}