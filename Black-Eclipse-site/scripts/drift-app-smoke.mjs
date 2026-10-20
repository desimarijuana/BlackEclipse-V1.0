// Full-app drift smoke: start the real Next.js app, mock only the HTTP API,
// navigate the real shell to Skills → Journey, and exercise the drift card.
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import { chromium } from "playwright";

const PORT = 3210;
const BASE = `http://127.0.0.1:${PORT}`;
const WINDOW = (rate, n) => ({
  n, successes: Math.round(rate * n), rate, ciLow: rate - 0.1, ciHigh: rate + 0.1,
});
const SIGNAL = {
  status: "drift", scope: "global", window: 30, baselineWindow: 100,
  current: WINDOW(0.33, 30), baseline: WINDOW(0.9, 100), drop: 0.57,
  threshold: 0.1, reasons: ["scripted drift"], availableScopes: ["global", "eclipse-agent"],
};
const CANDIDATE = {
  id: "evo_drift_fixture", signature: "sig", sourceCategory: "drift",
  observedCount: 30, problemStatement: "Production success dropped for eclipse-agent.",
  targetPath: null, proposedOps: null, subjectType: "drift", scope: "eclipse-agent",
  status: "inert", refusalCode: null, activatedVersion: null, previousVersion: null,
  createdAt: "2026-10-20T00:00:00Z", updatedAt: "2026-10-20T00:00:00Z",
};

const server = spawn(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["next", "dev", "--turbopack", "-p", String(PORT)],
  {
    cwd: process.cwd(),
    shell: true,
    env: { ...process.env, HARNESS_AUTH: "off", NEXT_TELEMETRY_DISABLED: "1" },
    stdio: "ignore",
  },
);

async function waitForServer() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(BASE);
      if (res.status < 500) return;
    } catch {
      // not listening yet
    }
    await sleep(1000);
  }
  throw new Error("Next.js dev server did not start");
}

function apiBody(pathname) {
  if (pathname.includes("/api/learning/journey")) {
    return {
      success: true, nodes: [], edges: [],
      stats: { nodeCount: 0, edgeCount: 0, byKind: {}, truncated: false },
      generatedAt: "2026-10-20T00:00:00Z",
    };
  }
  if (pathname.includes("/api/evolution/drift/scopes")) {
    return { success: true, availableScopes: ["global", "eclipse-agent"],
      signals: [{ scope: "eclipse-agent", signal: SIGNAL }] };
  }
  if (pathname.includes("/api/evolution/drift/history")) {
    return { success: true, scope: "global", window: 30, baselineWindow: 100,
      threshold: 0.1, step: 30, requestedPoints: 1, computedPoints: 1, truncated: false,
      points: [{ offset: 0, at: "2026-10-20T00:00:00Z", status: "drift", drop: 0.57,
        current: SIGNAL.current, baseline: SIGNAL.baseline }] };
  }
  if (pathname.includes("/api/evolution/drift/candidate")) {
    return { success: true, created: true, reason: "drift", candidate: CANDIDATE, signal: SIGNAL };
  }
  if (pathname.includes("/api/evolution/drift")) return SIGNAL;
  if (pathname.includes("/api/evolution/candidates/") && pathname.includes("evidence")) {
    return { success: true, candidate: CANDIDATE, attempts: [], experiments: [] };
  }
  if (pathname.includes("/api/evolution/rsl")) {
    return { success: true, mode: "observe", running: true, busy: false,
      maxCandidates: 5, maxExperimentsPerDay: 3, k: 1, startedToday: 0,
      remainingToday: 3, budgetExhausted: false,
      driftWatch: { enabled: true, intervalSeconds: 300, running: true, last: {} } };
  }
  if (pathname.includes("/api/evolution/experiments")) {
    return { success: true, experiments: [] };
  }
  if (pathname.includes("/api/evolution/states/pareto")) {
    return { success: true, objectives: { success: "max", cost: "min" },
      frontier: [], dominated: {}, states: [] };
  }
  if (pathname.includes("/api/evolution/states")) {
    return { success: true, current: null, currents: [], states: [] };
  }
  if (pathname.includes("/api/evolution/surface-activations")) {
    return { success: true, activations: [] };
  }
  return { success: true };
}

let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.route("**/api/**", (route) => {
    const pathname = new URL(route.request().url()).pathname;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiBody(pathname)),
    });
  });

  await page.goto(`${BASE}/?tab=skills`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /^Journey$/ }).first().click();
  await page.getByText("Learning journey", { exact: true }).first().waitFor({ timeout: 60_000 });
  await page.getByText("Production drift").first().waitFor({ timeout: 30_000 });
  try {
    await page.getByRole("button", { name: /eclipse-agent/ }).click();
  } catch (err) {
    console.log("BODY:", (await page.locator("body").innerText()).slice(0, 2500));
    throw err;
  }
  await page.getByRole("button", { name: /Open drift candidate/i }).click();
  await page.getByText(/Candidate scope: global/).waitFor();
  await page.getByRole("button", { name: /View evidence/i }).first().click();
  await page.getByText(/inert \| eclipse-agent/).waitFor();

  const selected = await page.locator("select").first().inputValue();
  if (selected !== "eclipse-agent") {
    throw new Error(`scope selection did not propagate: ${selected}`);
  }
  if (errors.length > 0) throw new Error(`page errors: ${errors.join("; ")}`);
  console.log("drift app smoke: PASS (real shell, Skills → Journey)");
} finally {
  await browser?.close();
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    server.kill("SIGTERM");
  }
}
