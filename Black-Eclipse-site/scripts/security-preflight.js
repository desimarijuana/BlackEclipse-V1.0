#!/usr/bin/env node
/*
 * Security preflight — fail closed when a network-facing deployment is missing a
 * required control. Run before starting production: `npm run security:preflight`.
 *
 * It does not replace the runtime's own bind guard (`python/harness/main.py`);
 * it is the deploy-time checklist so a misconfiguration is caught in CI/ops
 * rather than at first request.
 */

const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost", ""]);
const PLACEHOLDER = "change-me-to-a-random-secret";

function truthy(v) {
  if (v === undefined || v === null) return undefined;
  // MUST stay in step with `src/lib/auth/config.ts::truthy`: `required` is the
  // documented production value and what docker-compose.yml forces, so treating
  // it as "not on" made a correctly hardened deployment fail its own preflight.
  const s = String(v).trim().toLowerCase();
  if (["1", "true", "yes", "on", "required", "enable", "enabled"].includes(s)) return true;
  if (["0", "false", "no", "off", "none", "disabled"].includes(s)) return false;
  return undefined;
}

const host = (process.env.HOST || "").trim().toLowerCase();
const publicBind = !LOOPBACK.has(host);
const production = (process.env.NODE_ENV || "").toLowerCase() === "production";
const exposed = publicBind || production;

const checks = [];
function check(name, ok, detail, required = true) {
  checks.push({ name, ok, detail, required });
}

const authSecret = process.env.HARNESS_AUTH_SECRET;
check(
  "HARNESS_AUTH_SECRET",
  !!authSecret && authSecret !== PLACEHOLDER && authSecret.length >= 16,
  "front-door session/identity signing secret (>=16 chars)",
  exposed,
);

const cronSecret = process.env.CRON_SECRET;
check(
  "CRON_SECRET",
  !!cronSecret && cronSecret !== PLACEHOLDER && cronSecret.length >= 16,
  "operator/runtime secret",
  exposed,
);

const authOn = truthy(process.env.HARNESS_AUTH) ?? exposed;
check("HARNESS_AUTH", authOn === true, "front door enforces a signed-in user", exposed);

const multiTenant = truthy(process.env.HARNESS_MULTI_TENANT) ?? authOn;
check(
  "HARNESS_MULTI_TENANT (advisory)",
  true,
  multiTenant ? "tenant identity REQUIRED — data isolation still required (see docs)" : "single-tenant mode",
  false,
);

console.log("Security preflight");
console.log(`  bind=${host || "(default)"} production=${production} exposed=${exposed} multiTenant=${multiTenant}`);
for (const c of checks) {
  const tag = c.ok ? "OK  " : c.required ? "FAIL" : "WARN";
  console.log(`  [${tag}] ${c.name} — ${c.detail}`);
}
console.log("  Manual (not verifiable here): TLS terminating reverse proxy, edge rate limiting,");
console.log("  secrets-at-rest (KMS), audit-log shipping to WORM storage, per-tenant key isolation.");

const failed = checks.filter((c) => c.required && !c.ok);
if (failed.length) {
  console.error(`\nPreflight FAILED: ${failed.map((c) => c.name).join(", ")} missing.`);
  process.exit(1);
}
console.log("\nPreflight passed.");
