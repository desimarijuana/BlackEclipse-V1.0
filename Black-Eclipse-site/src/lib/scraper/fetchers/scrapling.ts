// Scrapling bridge fetcher — calls the Python Scrapling service to fetch
// a quote with advanced anti-bot bypass. Used as a fallback when HTTP +
// Playwright both fail, or when the user has Python/Scrapling available.
//
// Zero-config: if Python + Scrapling are not available, this returns
// a "network_error" and the adaptive chain falls back to other strategies.

import { existsSync } from "fs";
import path from "path";
import type { FetchResult, Quote } from "../types";
import { toErrorLike } from "../types";
import { findPython, runPythonBridge } from "./python";

const SERVICE_PATH = path.join(process.cwd(), "scripts", "scrapling_service.py");

// Cache the availability check so we don't spawn Python repeatedly.
let availabilityCache: boolean | null = null;

async function isScraplingAvailable(): Promise<boolean> {
  if (availabilityCache !== null) return availabilityCache;
  availabilityCache = (await findPython("scrapling")) !== null;
  return availabilityCache;
}

export async function fetchScraplingQuote(
  symbol: string,
  market: string
): Promise<FetchResult> {
  if (!existsSync(SERVICE_PATH)) {
    return { status: "network_error", error: "scrapling service missing", source: "scrapling" };
  }

  if (!(await isScraplingAvailable())) {
    return { status: "network_error", error: "scrapling not installed", source: "scrapling" };
  }

  try {
    const { stdout } = await runPythonBridge(SERVICE_PATH, [symbol, market], {
      timeout: 45000,
      maxBuffer: 1024 * 1024,
      mod: "scrapling",
    });

    // The service prints JSON to stdout; Scrapling logs go to stderr.
    const output = stdout.trim();
    const jsonStart = output.indexOf("{");
    const jsonStr = jsonStart >= 0 ? output.slice(jsonStart) : output;
    const data = JSON.parse(jsonStr);

    if (data.error === "blocked") {
      return { status: "blocked", error: "bot-wall detected", source: "scrapling" };
    }
    if (data.error === "structure_changed") {
      return { status: "structure_changed", error: "no price found", source: "scrapling" };
    }
    if (data.error) {
      return { status: "network_error", error: data.error, source: "scrapling" };
    }

    const price = parseFloat(data.price);
    if (isNaN(price) || price <= 0) {
      return { status: "structure_changed", error: "invalid price", source: "scrapling" };
    }

    const quote: Quote = {
      symbol,
      price,
      changePct: parseFloat(data.changePct) || 0,
    };
    return { status: "ok", quote, source: "scrapling" };
  } catch (err: unknown) {
    const e = toErrorLike(err);
    const msg = e.message || "scrapling failed";
    if (/timeout/i.test(msg) || /ETIMEDOUT/i.test(msg)) {
      return { status: "timeout", error: msg, source: "scrapling" };
    }
    // The service exits non-zero on failure but still prints JSON to stdout.
    // Parse err.stdout (available in the rejection object) to classify it.
    const raw = String(e.stdout || e.stderr || "");
    const jsonStart = raw.indexOf("{");
    if (jsonStart >= 0) {
      try {
        const data = JSON.parse(raw.slice(jsonStart));
        if (data.error === "blocked") {
          return { status: "blocked", error: "bot-wall detected", source: "scrapling" };
        }
        if (data.error === "structure_changed") {
          return { status: "structure_changed", error: "no price found", source: "scrapling" };
        }
      } catch {}
    }
    return { status: "network_error", error: msg, source: "scrapling" };
  }
}
