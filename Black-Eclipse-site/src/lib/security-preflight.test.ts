// The deploy-time checklist must accept the SAME auth vocabulary as the app
// (`src/lib/auth/config.ts`). It previously did not: `HARNESS_AUTH=required` —
// the documented production value and the one `docker-compose.yml` forces — was
// read as "not on", so a correctly hardened deployment failed its own preflight.

import { spawnSync } from "node:child_process";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const script = path.join(root, "scripts", "security-preflight.js");

function run(overrides: Record<string, string | undefined>) {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    NODE_ENV: "production",
    HOST: "0.0.0.0",
    HARNESS_AUTH: "required",
    HARNESS_AUTH_SECRET: "test-signing-secret-0123456789",
    CRON_SECRET: "test-cron-secret-0123456789",
    ...overrides,
  };
  for (const key of ["HARNESS_AUTH", "HARNESS_AUTH_SECRET", "CRON_SECRET"]) {
    if (env[key] === undefined) delete env[key];
  }
  const result = spawnSync(process.execPath, [script], { cwd: root, env, encoding: "utf8" });
  return { status: result.status, output: `${result.stdout}${result.stderr}` };
}

describe("security preflight auth vocabulary", () => {
  it.each(["required", "1", "true", "on", "enabled"])(
    "accepts HARNESS_AUTH=%s on an exposed production build",
    (value) => {
      const result = run({ HARNESS_AUTH: value });
      expect(result.output).toContain("Preflight passed");
      expect(result.status).toBe(0);
    }
  );

  it("fails closed when HARNESS_AUTH is explicitly off on an exposed build", () => {
    const result = run({ HARNESS_AUTH: "off" });
    expect(result.status).toBe(1);
    expect(result.output).toContain("HARNESS_AUTH");
  });

  it("fails closed when the signing secret is missing", () => {
    const result = run({ HARNESS_AUTH_SECRET: undefined });
    expect(result.status).toBe(1);
    expect(result.output).toContain("HARNESS_AUTH_SECRET");
  });

  it("fails closed when the operator secret is missing", () => {
    const result = run({ CRON_SECRET: undefined });
    expect(result.status).toBe(1);
    expect(result.output).toContain("CRON_SECRET");
  });
});
